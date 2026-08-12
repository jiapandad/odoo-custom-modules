from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PurchaseRequisition(models.Model):
    _name = 'hc.purchase.requisition'
    _description = '请购单'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'name'
    _rec_names_search = ['name', 'description']

    # ── 基本信息 ──

    name = fields.Char(
        '请购单号',
        copy=False,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company', '需求组织',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    department_id = fields.Many2one(
        'hr.department', '需求部门',
        required=False,
        domain="[('company_id', '=', company_id)]",
    )
    project_id = fields.Many2one(
        'project.project', '关联项目',
        domain="[('company_id', '=', company_id)]",
        help='请购单关联的项目，生成采购订单时会自动带入分析账户',
    )
    applicant_id = fields.Many2one(
        'hr.employee', '申请人',
        required=False,
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env.user.employee_id,
    )
    applicant_user_id = fields.Many2one(
        'res.users', '申请人账号',
        related='applicant_id.user_id',
        store=True,
    )
    requisition_type = fields.Selection([
        ('engineering', '工程物料需求'),
        ('production', '生产物料需求'),
        ('mro', 'MRO 备品备件'),
        ('office', '办公用品'),
        ('consumables', '消耗品'),
        ('other', '其他'),
    ], '请购类型', required=True, default='engineering')

    date_required = fields.Date(
        '最晚需求日期',
        help='所有物料需求日期中最早的日期',
        compute='_compute_date_required',
        store=True,
    )
    description = fields.Text('申请说明')

    # ── 状态与审批 ──
    # state 由 approval_request_id 的状态自动派生，同时也允许直接写入（草稿/取消等场景）

    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '审批中'),
        ('approved', '已审批'),
        ('rejected', '已驳回'),
        ('cancelled', '已取消'),
    ], '状态', compute='_compute_state', store=True, tracking=True, copy=False, index=True)

    approval_request_id = fields.Many2one(
        'approval.request', '审批请求',
        readonly=True, copy=False, ondelete='set null',
        help='关联的审批请求记录',
    )
    approval_state = fields.Selection(
        related='approval_request_id.state',
        string='审批状态', readonly=True,
    )

    # 审批类型编码 — approval_cn 通过此编码匹配审批类型和流程
    approval_category_code = fields.Char(
        '审批类型编码', default='purchase_requisition',
        required=True,
    )
    # 审批流程选择：不同组织/公司可配置不同审批流程
    flow_id = fields.Many2one(
        'approval.flow', '审批流程',
        domain="[('category_id.code', '=', approval_category_code), ('active', '=', True)]",
        help='选择审批流程。不选则使用默认流程。不同公司可配置不同流程，由管理员在审批流程中设置。',
    )

    # ── 明细行 ──

    line_ids = fields.One2many(
        'hc.purchase.requisition.line', 'requisition_id',
        '请购明细', copy=True,
    )
    line_count = fields.Integer(
        '物料项数',
        compute='_compute_line_count',
        store=True,
    )

    # ── 金额 ──

    estimated_amount = fields.Monetary(
        '预估金额',
        compute='_compute_estimated_amount',
        store=True,
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', '币种',
        related='company_id.currency_id',
    )

    # ── 采购追踪 ──

    rfq_id = fields.Many2one(
        'purchase.order', '生成询价单',
        readonly=True, copy=False,
        help='审批通过后生成的采购询价单',
    )
    rfq_count = fields.Integer(
        '询价单数', compute='_compute_rfq_count',
    )

    # ================================================================
    #  计算字段
    # ================================================================

    @api.depends('approval_request_id', 'approval_request_id.state')
    def _compute_state(self):
        for req in self:
            if req.approval_request_id:
                req.state = req.approval_request_id.state
            elif not req.state or req.state == 'none':
                req.state = 'draft'

    @api.depends('line_ids.date_required')
    def _compute_date_required(self):
        for req in self:
            dates = req.line_ids.mapped('date_required')
            req.date_required = min(dates) if dates else False

    @api.depends('line_ids')
    def _compute_line_count(self):
        for req in self:
            req.line_count = len(req.line_ids)

    @api.depends('line_ids.estimated_unit_price', 'line_ids.quantity')
    def _compute_estimated_amount(self):
        for req in self:
            req.estimated_amount = sum(
                line.estimated_unit_price * line.quantity
                for line in req.line_ids
                if line.estimated_unit_price and line.quantity
            )

    # ================================================================
    #  CRUD
    # ================================================================

    @api.model_create_multi
    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "flow_id" in fields_list and not defaults.get("flow_id"):
            last_flow = self.env["ir.default"].get(
                "hc.purchase.requisition", "flow_id",
                user_id=self.env.uid, company_id=self.env.company.id
            )
            if last_flow:
                flow = self.env["approval.flow"].browse(last_flow)
                if flow.exists() and flow.active:
                    defaults["flow_id"] = last_flow
        return defaults

    def write(self, vals):
        result = super().write(vals)
        if "flow_id" in vals and vals["flow_id"]:
            self.env["ir.default"].set(
                "hc.purchase.requisition", "flow_id",
                vals["flow_id"],
                user_id=self.env.uid, company_id=self.env.company.id
            )
        return result

    def create(self, vals_list):

        """请购单号：YYYYMMDD + 4位流水号，每日重置"""
        for vals in vals_list:
            vals['name'] = self._generate_requisition_name()
        return super().create(vals_list)

    def _generate_requisition_name(self):
        """生成请购单号，格式 YYYYMMDDNNNN"""
        today_str = fields.Date.today().strftime('%Y%m%d')
        # 先尝试通过 ir.sequence + date_range 获取（支持每日重置）
        seq_name = self.env['ir.sequence'].next_by_code(
            'hc.purchase.requisition'
        )
        if seq_name:
            return seq_name

        # 如果 sequence 未配置或 date_range 未创建，手动生成
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [int('hc_pur_req_name', 36) % 2147483647]
        )
        self.env.cr.execute("""
            SELECT name FROM hc_purchase_requisition
            WHERE name LIKE %s
            ORDER BY name DESC
            LIMIT 1
        """, [today_str + '%'])
        row = self.env.cr.fetchone()
        if row and row[0] and len(row[0]) == 12 and row[0].startswith(today_str):
            seq = int(row[0][8:]) + 1
        else:
            seq = 1
        return '%s%04d' % (today_str, seq)



        # 提交审批后不允许修改关键字段（审批系统回写除外）
        protected_fields = {'line_ids', 'company_id', 'department_id', 'requisition_type'}
        for record in self:
            if record.state in ('submitted', 'approved'):
                if not self.env.context.get('_approval_syncing'):
                    if protected_fields & set(vals.keys()):
                        raise UserError(_(
                            '请购单 "%s" 已提交审批，不能修改关键字段。如需变更，请撤回后重新提交。'
                        ) % record.name)

        res = super().write(vals)

        # 审批通过后自动生成采购询价单
        if not self.env.context.get('_req_skip_auto_rfq'):
            for record in self:
                if record.state == 'approved' and not record.rfq_id:
                    try:
                        record.with_context(_req_skip_auto_rfq=True).action_create_rfq()
                    except Exception:
                        # RFQ 生成失败不阻断审批，用户可后续手动点击按钮
                        _logger.exception(
                            '请购单 %s 自动生成询价单失败', record.name
                        )

        return res

    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('只能删除草稿状态的请购单。'))
        return super().unlink()

    # ================================================================
    #  状态流转
    # ================================================================

    def action_submit(self):
        """提交审批"""
        for record in self:
            if record.state != 'draft':
                raise UserError(_('请购单 "%s" 不是草稿状态，无法提交。') % record.name)
            if not record.line_ids:
                raise UserError(_('请购单 "%s" 没有添加任何物料，请先添加需求明细。') % record.name)

            # 检查明细行必填字段
            for line in record.line_ids:
                if not line.product_uom_id:
                    raise UserError(_(
                        '请购单 "%s" 第 %s 行 "%s" 未选择单位，请选择单位后再提交。'
                    ) % (record.name, line.sequence, line.product_id.display_name))

            # 通过 approval_cn 发起审批
            category = self.env['approval.category'].search([
                ('code', '=', record.approval_category_code),
            ], limit=1)
            if not category:
                raise UserError(_(
                    '未找到审批类型编码 "%s"，请联系管理员在 approval_cn 中配置。'
                ) % record.approval_category_code)

            # 获取审批流程：优先使用用户选择的流程，否则使用默认流程
            flow = record.flow_id
            if not flow:
                flow = self.env['approval.flow']._get_flow_for_category(
                    record.approval_category_code,
                    record.estimated_amount,
                )
            if not flow:
                raise UserError(_(
                    '未找到对应的审批流程，请联系管理员配置。'
                ))

            request = self.env['approval.request'].create({
                'name': record.name,
                'category_id': category.id,
                'flow_id': flow.id,
                'model_name': record._name,
                'res_id': record.id,
                'res_name': record.display_name,
                'amount': record.estimated_amount,
                'request_user_id': record.env.user.id,
                'description': record._build_requisition_summary(),
            })

            request.action_submit()
            # 设置 approval_request_id 后 state 会自动计算为 'submitted'
            record.write({'approval_request_id': request.id})

    def _build_requisition_summary(self):
        """生成请购单详情摘要，用于审批说明。紧凑排版，兼顾桌面端和移动端。"""
        self.ensure_one()
        lines = []
        selection = dict(self._fields['requisition_type'].selection)

        # 头部：单号、类型、最晚日期、金额（单行，便于移动端阅读）
        lines.append('【请购单】%s' % (self.name or ''))
        lines.append(
            '需求组织：%s | 需求部门：%s | 申请人：%s' % (
                self.company_id.name or '',
                self.department_id.name or '',
                self.applicant_id.name or '',
            )
        )
        lines.append(
            '类型：%s | 最晚：%s | 金额：%.2f %s' % (
                selection.get(self.requisition_type, ''),
                self.date_required or '-',
                self.estimated_amount or 0.0,
                self.currency_id.name or '',
            )
        )

        # 申请说明
        if self.description:
            lines.append('说明：%s' % self.description)

        # 请购明细
        lines.append('')
        lines.append('【明细】共%d项' % len(self.line_ids))
        for idx, line in enumerate(self.line_ids, 1):
            product = line.product_id.display_name if line.product_id else '未指定'
            uom = line.product_uom_id.name or ''

            # 第一行：核心信息，尽量保持单行
            parts = ['%d. %s' % (idx, product)]
            parts.append('数量：%g%s' % (line.quantity, uom))
            if line.estimated_unit_price:
                parts.append('单价：%.2f' % line.estimated_unit_price)
            if line.date_required:
                parts.append('需求：%s' % line.date_required)
            lines.append(' | '.join(parts))

            # 第二行：扩展属性（按需显示，避免主行过长）
            extras = []
            if line.specification:
                extras.append('规格：%s' % line.specification)
            if line.material_type:
                extras.append('材质：%s' % line.material_type)
            if line.usage:
                extras.append('用途：%s' % line.usage)
            if line.standard:
                extras.append('标准：%s' % line.standard)
            if line.note:
                extras.append('备注：%s' % line.note)
            if extras:
                lines.append('扩展：%s' % ' | '.join(extras))

        return '\n'.join(lines)

    def action_draft(self):
        """退回草稿"""
        for record in self:
            if record.state not in ('rejected',):
                raise UserError(_('只有已驳回的请购单才能退回草稿。'))
            record.approval_request_id = False

    def action_cancel(self):
        """取消"""
        for record in self:
            if record.state == 'submitted' and record.approval_request_id:
                record.approval_request_id.action_cancel()
                # 取消后清除关联，state 会自动变为 draft
                record.approval_request_id = False
            else:
                record.approval_request_id = False

    def _get_rfq_placeholder_partner(self):
        """获取RFQ占位供应商（待供应商），不存在则创建。"""
        partner = self.env['res.partner'].search([('name', '=', '待供应商')], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': '待供应商',
                'company_id': False,
                'is_company': True,
                'supplier_rank': 1,
            })
        return partner

    def action_create_rfq(self):
        """审批通过后：生成采购询价单（RFQ）"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('只有已审批的请购单才能生成询价单。'))
        if self.rfq_id:
            raise UserError(_('该请购单已生成过询价单 %s。') % self.rfq_id.name)

        # 切换到请购单所属公司上下文，避免跨公司访问错误
        self = self.with_company(self.company_id)

        picking_type = self.env['purchase.order']._get_default_picking_type(self.company_id)

        po = self.env['purchase.order'].create({
            'partner_id': self._get_rfq_placeholder_partner().id,
            'company_id': self.company_id.id,
            'department_id': self.department_id.id,
            'date_order': fields.Datetime.now(),
            'origin': self.name,
            'picking_type_id': picking_type.id,
            'project_id': self.project_id.id,
            'hc_requisition_id': self.id,
            'order_line': [(0, 0, {
                'product_id': line.product_id.id,
                'name': self._format_rfq_line_name(line),
                'product_qty': line.quantity,
                'product_uom_id': (line.product_uom_id or line.product_id.uom_id).id,
                'price_unit': line.estimated_unit_price or 0.0,
                'date_planned': line.date_required,
            }) for line in self.line_ids],
        })

        self.write({'rfq_id': po.id})
        self.message_post(
            body=_('已生成采购询价单 <a href="#" data-oe-model="purchase.order" '
                   'data-oe-id="%s">%s</a>，请采购员补充供应商信息并发起询价。')
            % (po.id, po.name)
        )
        return {
            'type': 'ir.actions.act_window',
            'name': '采购询价单',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }

    @staticmethod
    def _format_rfq_line_name(line):
        """格式化询价单物料描述"""
        parts = [line.product_id.display_name]
        if line.material_type:
            parts.append('种类材质：%s' % line.material_type)
        if line.specification:
            parts.append('规格型号：%s' % line.specification)
        if line.usage:
            parts.append('用途：%s' % line.usage)
        if line.standard:
            parts.append('执行标准：%s' % line.standard)
        return '\n'.join(parts)

    @api.depends('rfq_id')
    def _compute_rfq_count(self):
        for record in self:
            record.rfq_count = 1 if record.rfq_id else 0

    def action_view_approval(self):
        """跳转到审批请求"""
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError(_('此请购单还没有关联审批请求。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '审批请求',
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
        }

    def action_view_rfq(self):
        """跳转到关联的采购询价单"""
        self.ensure_one()
        if not self.rfq_id:
            raise UserError(_('此请购单还没有生成询价单。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '采购询价单',
            'res_model': 'purchase.order',
            'res_id': self.rfq_id.id,
            'view_mode': 'form',
        }
