from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseContract(models.Model):
    _name = 'hc.purchase.contract'
    _description = '采购合同'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char('合同编号', readonly=True, copy=False, default='新建')
    partner_id = fields.Many2one(
        'res.partner', '供应商', required=True,
        ondelete='restrict', index=True,
    )
    bid_comparison_id = fields.Many2one(
        'hc.bid.comparison', '关联比价单', readonly=True,
        ondelete='restrict', index=True,
    )
    rfq_id = fields.Many2one(
        'purchase.order', '关联采购订单',
        related='bid_comparison_id.rfq_id', store=True, readonly=True,
    )
    purchase_order_ids = fields.One2many(
        'purchase.order', 'hc_contract_id', '关联采购订单',
        readonly=True,
    )
    purchase_order_count = fields.Integer(
        '采购订单数', compute='_compute_purchase_order_count',
    )

    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已驳回'),
        ('active', '执行中'),
        ('closed', '已关闭'),
    ], '状态', default='draft', tracking=True)

    contract_type = fields.Selection([
        ('single', '单次合同'),
        ('framework', '框架合同'),
    ], '合同类型', default='single', required=True, tracking=True,
       help='单次合同：针对本次采购订单；框架合同：月结供应商长期有效')
    is_framework = fields.Boolean(
        '框架合同', compute='_compute_is_framework', store=True,
        help='框架合同启用后，合同物料可自动带入后续采购订单',
    )

    contract_file = fields.Binary('合同文件', attachment=True)
    contract_file_name = fields.Char('文件名')
    contract_date = fields.Date('签订日期', default=fields.Date.today, tracking=True)
    start_date = fields.Date('生效日期', tracking=True)
    end_date = fields.Date('到期日期', tracking=True)
    amount = fields.Monetary(
        '合同金额', currency_field='currency_id', tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency', '货币', related='company_id.currency_id',
    )
    payment_terms = fields.Char(
        '结算方式', help='如：月结30天、月结60天、款到发货等',
    )
    description = fields.Html('备注')
    company_id = fields.Many2one(
        'res.company', '公司', required=True,
        default=lambda self: self.env.company,
    )
    department_id = fields.Many2one(
        'hr.department', '需求部门',
        related='bid_comparison_id.rfq_id.department_id', store=True,
    )
    department_id = fields.Many2one(
        'hr.department', '需求部门',
        related='bid_comparison_id.rfq_id.department_id', store=True,
    )

    line_ids = fields.One2many(
        'hc.purchase.contract.line', 'contract_id', '合同明细',
        copy=True,
    )

    # 审批相关
    approval_request_id = fields.Many2one(
        'approval.request', '审批请求', readonly=True, copy=False,
        ondelete='set null',
    )
    approval_category_code = fields.Char(
        '审批类型编码', default='purchase_contract', required=True,
    )
    # 审批流程选择
    flow_id = fields.Many2one(
        'approval.flow', '审批流程',
        domain="[('category_id.code', '=', approval_category_code), ('active', '=', True)]",
        help='选择审批流程。不选则使用默认流程。',
    )
    approval_state = fields.Char(
        '审批状态', default='draft', readonly=True, copy=False,
    )

    @api.depends('contract_type')
    def _compute_is_framework(self):
        for contract in self:
            contract.is_framework = contract.contract_type == 'framework'

    @api.depends('purchase_order_ids')
    def _compute_purchase_order_count(self):
        for contract in self:
            contract.purchase_order_count = len(contract.purchase_order_ids)

    def action_view_purchase_orders(self):
        """打开关联的采购订单（避免重复创建）"""
        self.ensure_one()
        # 优先用 One2many 关联的订单
        if self.purchase_order_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': _('采购订单'),
                'res_model': 'purchase.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.purchase_order_ids.ids)],
                'target': 'current',
            }
        # 如果是单次合同但还没关联，回退到比价单的 rfq_id
        if self.rfq_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('关联采购订单'),
                'res_model': 'purchase.order',
                'res_id': self.rfq_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        raise UserError(_('该合同尚未关联任何采购订单。'))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """供应商变动时，若存在框架合同则提示"""
        if self.partner_id:
            framework = self.search([
                ('partner_id', '=', self.partner_id.id),
                ('contract_type', '=', 'framework'),
                ('state', '=', 'active'),
                ('id', '!=', self.id),
            ], limit=1)
            if framework:
                return {
                    'warning': {
                        'title': _('提示'),
                        'message': _(
                            '供应商 %s 已存在生效中的框架合同 %s，'
                            '新采购可直接引用框架合同物料。'
                        ) % (self.partner_id.name, framework.name),
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '新建') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hc.purchase.contract'
                ) or '新建'
        return super().create(vals_list)

    def write(self, vals):
        """提交/批准后禁止编辑，但允许状态按钮触发的纯状态变更"""
        for contract in self:
            if contract.state in ('submitted', 'approved', 'active'):
                if not self.env.context.get('_approval_syncing'):
                    # 激活/关闭按钮仅修改 state，允许
                    if set(vals.keys()) != {'state'}:
                        raise UserError(_(
                            '合同 "%s" 已提交审批，不允许编辑。请撤回审批后重试。'
                        ) % contract.name)
        res = super().write(vals)
        if 'approval_state' in vals:
            state_map = {
                'approved': 'active',  # 审批通过直接激活
                'rejected': 'rejected',
                'cancelled': 'draft',
            }
            new_state = state_map.get(vals['approval_state'])
            if new_state:
                for contract in self:
                    if contract.state != new_state:
                        contract.state = new_state
                        if new_state == 'active':
                            contract._link_related_purchase_orders()
        return res

    def _link_related_purchase_orders(self):
        """合同激活时，自动关联相关的未绑定采购订单（不限PO状态）"""
        self.ensure_one()
        if not self.bid_comparison_id:
            return
        bid = self.bid_comparison_id
        rfq = bid.rfq_id
        origins = list(set([
            rfq.name,
            rfq.origin or rfq.name,
            bid.name,
        ]))
        # 请购单名称（RFQ来源）
        if rfq.hc_requisition_id:
            origins.append(rfq.hc_requisition_id.name)
        origins = [o for o in origins if o]
        if not origins:
            return

        domain = ['|'] * (len(origins) - 1) + [
            ('origin', 'ilike', o) for o in origins
        ]
        pos = self.env['purchase.order'].search(domain)
        pos = pos.filtered(lambda p: not p.hc_contract_id)
        if pos:
            pos.write({'hc_contract_id': self.id})
            self.message_post(
                body=_('已自动绑定采购订单：%s')
                % ', '.join(pos.mapped('name'))
            )

    def unlink(self):
        for contract in self:
            if contract.state != 'draft':
                raise UserError(_('只能删除草稿状态的合同。'))
        return super().unlink()

    # ---- 审批流程 ----

    def action_submit_approval(self):
        """提交合同审批"""
        self.ensure_one()
        if self.state not in ('draft', 'rejected'):
            raise UserError(_('当前状态不允许提交审批。'))
        if not self.contract_file:
            raise UserError(_('请先上传合同文件后再提交审批。'))
        if not self.line_ids:
            raise UserError(_('请先添加合同明细行。'))

        category = self.env['approval.category'].search([
            ('code', '=', self.approval_category_code),
        ], limit=1)
        if not category:
            raise UserError(_(
                '未找到审批类型编码 "%s"，请联系管理员配置。'
            ) % self.approval_category_code)

        flow = self.flow_id
        if not flow:
            flow = self.env['approval.flow'].search([
                ('category_id', '=', category.id),
                ('active', '=', True),
            ], limit=1)
        if not flow:
            raise UserError(_('审批类型 "%s" 下没有可用的审批流程。') % category.name)

        if self.approval_request_id:
            self.approval_request_id = False

        request = self.env['approval.request'].create({
            'name': _('采购合同审批: %s') % self.name,
            'category_id': category.id,
            'flow_id': flow.id,
            'model_name': self._name,
            'res_id': self.id,
            'res_name': self.name,
            'amount': self.amount or sum(
                self.line_ids.mapped('subtotal') or [0]
            ),
            'request_user_id': self.env.user.id,
            'description': self._build_approval_description(),
        })
        request.action_submit()
        self.approval_request_id = request.id
        self.state = 'submitted'

        self.message_post(
            body=_('合同已提交审批。合同类型：%s，金额：%.2f')
            % (self.get_contract_type_display(), self.amount or 0)
        )

    def _build_approval_description(self):
        """生成合同审批说明"""
        self.ensure_one()
        lines = []
        lines.append('【采购合同】%s' % self.name)
        lines.append('供应商：%s' % (self.partner_id.name or ''))
        lines.append('合同类型：%s' % self.get_contract_type_display())
        if self.company_id:
            lines.append('需求公司：%s' % (self.company_id.name or ''))
        if self.department_id:
            lines.append('需求部门：%s' % (self.department_id.name or ''))
        if self.company_id:
            lines.append('需求公司：%s' % (self.company_id.name or ''))
        if self.department_id:
            lines.append('需求部门：%s' % (self.department_id.name or ''))
        if self.amount:
            lines.append('合同金额：%.2f' % self.amount)
        if self.payment_terms:
            lines.append('结算方式：%s' % self.payment_terms)
        if self.start_date:
            lines.append('生效日期：%s' % self.start_date)
        if self.end_date:
            lines.append('到期日期：%s' % self.end_date)

        lines.append('')
        lines.append('【合同物料明细】')
        for line in self.line_ids:
            parts = ['物料：%s' % (line.product_id.display_name or '')]
            parts.append('数量：%g %s' % (line.quantity, line.product_uom_id.name or ''))
            parts.append('单价：%.2f' % (line.price_unit or 0))
            if line.subtotal:
                parts.append('小计：%.2f' % line.subtotal)
            if line.description:
                parts.append('备注：%s' % line.description)
            lines.append(' | '.join(parts))

        # 合同文件下载链接
        if self.contract_file:
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url'
            )
            download_url = (
                '%s/web/content/hc.purchase.contract/%s/contract_file/%s'
                '?download=true'
            ) % (base_url, self.id, self.contract_file_name or 'contract.pdf')
            lines.append('')
            lines.append('【合同文件】点击以下链接预览/下载合同：')
            lines.append(download_url)

        if self.description:
            lines.append('')
            lines.append('备注：%s' % self.description)

        return '\n'.join(lines)

    def action_approve(self):
        """审批通过/已批准 → 激活合同"""
        self.ensure_one()
        if self.state not in ('approved', 'active'):
            raise UserError(_('合同审批未通过，无法激活。'))
        if self.state != 'active':
            self.state = 'active'
            self._link_related_purchase_orders()
            self.message_post(body=_('合同已生效。'))

    def action_close(self):
        """关闭合同"""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_('只有生效中的合同才能关闭。'))
        self.state = 'closed'
        self.message_post(body=_('合同已关闭。'))

    def button_cancel(self):
        """撤回审批"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只能撤回审批中的合同。'))
        if self.approval_request_id:
            if self.approval_request_id.state == 'submitted':
                self.approval_request_id.action_cancel()
        self.approval_request_id = False
        self.approval_state = 'draft'
        self.state = 'draft'
        self.message_post(body=_('合同审批已撤回，可重新编辑提交。'))

    def button_draft(self):
        """驳回后退回草稿"""
        self.ensure_one()
        if self.state != 'rejected':
            raise UserError(_('只有驳回的合同才能退回草稿。'))
        self.state = 'draft'
        self.approval_request_id = False
        self.message_post(body=_('已退回草稿，可重新编辑提交。'))

    def action_view_contract_file(self):
        """在线查看合同文件"""
        self.ensure_one()
        if not self.contract_file:
            raise UserError(_('未上传合同文件。'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/contract_file/%s?download=true'
                   % (self._name, self.id, self.contract_file_name),
            'target': 'new',
        }

    def action_create_po_from_framework(self):
        """从框架合同创建采购订单，自动带入合同物料"""
        self.ensure_one()
        if not self.is_framework:
            raise UserError(_('只有框架合同才能创建采购订单。'))
        if self.state != 'active':
            raise UserError(_('只有生效中的框架合同才能创建采购订单。'))

        po_lines = []
        for line in self.line_ids:
            po_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'product_qty': line.quantity,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit,
            }))

        picking_type = self.env['purchase.order']._get_default_picking_type(self.company_id)

        po = self.env['purchase.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'date_order': fields.Datetime.now(),
            'origin': self.name,
            'order_line': po_lines,
            'picking_type_id': picking_type.id,
            'hc_contract_id': self.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('采购订单'),
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
        }

    def get_contract_type_display(self):
        """获取合同类型的中文显示"""
        type_map = {
            'single': '单次合同',
            'framework': '框架合同',
        }
        return type_map.get(self.contract_type, '')


class PurchaseContractLine(models.Model):
    _name = 'hc.purchase.contract.line'
    _description = '合同明细行'

    contract_id = fields.Many2one(
        'hc.purchase.contract', '合同',
        required=True, ondelete='cascade',
    )
    sequence = fields.Integer('序号', default=10)
    product_id = fields.Many2one(
        'product.product', '物料', required=True,
        ondelete='restrict',
    )
    product_uom_id = fields.Many2one(
        'uom.uom', '单位', required=True,
        ondelete='restrict',
    )
    quantity = fields.Float('数量', default=1.0, required=True)
    price_unit = fields.Float('单价', required=True)
    currency_id = fields.Many2one(
        'res.currency', '货币',
        related='contract_id.currency_id',
    )
    subtotal = fields.Monetary(
        '小计', compute='_compute_subtotal', store=True,
        currency_field='currency_id',
    )
    description = fields.Text('备注')

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.product_uom_id:
                self.product_uom_id = self.product_id.uom_id.id
            if not self.price_unit:
                self.price_unit = self.product_id.standard_price
