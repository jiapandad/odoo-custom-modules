from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BidComparison(models.Model):
    _name = 'hc.bid.comparison'
    _description = '比价单'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char('比价单号', readonly=True, copy=False, default='新建')
    rfq_id = fields.Many2one(
        'purchase.order', '关联询价单',
        required=True, ondelete='cascade', index=True,
    )

    state = fields.Selection([
        ('draft', '草稿'),
        ('compared', '已比价'),
        ('submitted', '待审批'),
        ('approved', '已定标'),
        ('rejected', '已驳回'),
    ], '状态', default='draft', tracking=True)

    line_ids = fields.One2many(
        'hc.bid.comparison.line', 'comparison_id', '比价明细',
    )
    winner_partner_ids = fields.Many2many(
        'res.partner', compute='_compute_winner_partners', store=True,
        string='中标供应商',
    )
    recommend_reason = fields.Text('推荐说明')
    company_id = fields.Many2one(
        'res.company', '公司',
        related='rfq_id.company_id', store=True,
    )
    department_id = fields.Many2one(
        'hr.department', '需求部门',
        related='rfq_id.department_id', store=True,
    )

    # 审批
    approval_request_id = fields.Many2one(
        'approval.request', '审批请求', readonly=True, copy=False,
        ondelete='set null',
    )
    approval_category_code = fields.Char(
        '审批类型编码', default='bid_award', required=True,
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

    @api.depends('line_ids.is_winner')
    def _compute_winner_partners(self):
        for bid in self:
            winner_lines = bid.line_ids.filtered('is_winner')
            bid.winner_partner_ids = winner_lines.mapped('partner_id')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '新建') == '新建':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'hc.bid.comparison'
                ) or '新建'
        return super().create(vals_list)

    def write(self, vals):
        for bid in self:
            if bid.state in ('submitted', 'approved'):
                if not self.env.context.get('_approval_syncing'):
                    raise UserError(_(
                        '比价单 "%s" 已提交审批，不允许编辑。请撤回审批后重试。'
                    ) % bid.name)
        res = super().write(vals)
        if 'approval_state' in vals:
            state_map = {
                'approved': 'approved',
                'rejected': 'rejected',
                'cancelled': 'draft',
            }
            new_state = state_map.get(vals['approval_state'])
            if new_state:
                for bid in self:
                    if bid.state != new_state:
                        bid.state = new_state
            # 审批通过时自动同步中标价到RFQ行
            if vals.get('approval_state') == 'approved':
                for bid in self:
                    if bid.state != 'approved' or not bid.rfq_id:
                        continue
                    winners = bid.line_ids.filtered('is_winner')
                    if not winners:
                        continue
                    # 单个供应商中标：直接更新RFQ供应商+价格
                    unique_partners = winners.mapped('partner_id')
                    if len(unique_partners) == 1:
                        rfq = bid.rfq_id
                        rfq.partner_id = unique_partners[0].id
                        for wl in winners:
                            if wl.unit_price:
                                rfq_line = rfq.order_line.filtered(lambda l: l.product_id == wl.product_id)
                                if rfq_line:
                                    rfq_line.price_unit = wl.unit_price
                    else:
                        # 多供应商中标：走完整定标流程（创建多个PO）
                        if bid.rfq_id.state in ('draft', 'sent'):
                            bid.with_context(_approval_syncing=True, _bid_award_sync=True).action_confirm_award()
                        else:
                            # RFQ已确认：仅同步价格
                            for wl in winners:
                                if wl.unit_price:
                                    rfq_line = bid.rfq_id.order_line.filtered(lambda l: l.product_id == wl.product_id)
                                    if rfq_line:
                                        rfq_line.price_unit = wl.unit_price
        return res

    def button_cancel(self):
        for bid in self:
            if bid.state != 'submitted':
                raise UserError(_('只能撤回审批中的比价单。'))
            if bid.approval_request_id:
                if bid.approval_request_id.state == 'submitted':
                    bid.approval_request_id.action_cancel()
            bid.approval_request_id = False
            bid.approval_state = 'draft'
            bid.state = 'draft'
            quotes = self.env['hc.supplier.quote'].search([
                ('rfq_id', '=', bid.rfq_id.id),
                ('state', '!=', 'draft'),
            ])
            quotes.with_context(_bid_award_sync=True).write({'state': 'draft'})
            bid.message_post(body=_('比价定标审批已撤回，报价单已重置，可重新编辑。'))

    def button_draft(self):
        for bid in self:
            if bid.state != 'rejected':
                raise UserError(_('只有驳回的比价单才能退回草稿。'))
            bid.state = 'draft'
            bid.approval_request_id = False
            bid.message_post(body=_('已退回草稿，可重新编辑提交。'))

    def unlink(self):
        for bid in self:
            if bid.state != 'draft':
                raise UserError(_('只能删除草稿状态的比价单。'))
        return super().unlink()

    def action_generate_comparison(self):
        self.ensure_one()
        quotes = self.env['hc.supplier.quote'].search([
            ('rfq_id', '=', self.rfq_id.id),
            ('state', '=', 'submitted'),
        ])
        if not quotes:
            raise UserError(_('该询价单下没有已录入的供应商报价。'))

        self.line_ids.unlink()
        for rfq_line in self.rfq_id.order_line:
            col_index = 0
            for quote in quotes:
                quote_line = quote.line_ids.filtered(
                    lambda l: l.product_id == rfq_line.product_id
                )
                if quote_line:
                    self.env['hc.bid.comparison.line'].create({
                        'comparison_id': self.id,
                        'product_id': rfq_line.product_id.id,
                        'product_uom_id': quote_line.product_uom_id.id,
                        'quantity': rfq_line.product_qty,
                        'partner_id': quote.partner_id.id,
                        'brand': quote_line.brand,
                        'tax_rate': quote_line.tax_rate,
                        'unit_price': quote_line.unit_price,
                        'delivery_date': quote_line.delivery_date,
                        'warranty_months': quote_line.warranty_months,
                        'total_amount': quote_line.total_amount,
                        'col_index': col_index,
                    })
                    col_index += 1

        self.state = 'compared'
        self.message_post(body=_('已生成比价矩阵，共 %s 个报价。') % len(quotes))

    def action_recommend(self):
        self.ensure_one()
        if self.state != 'compared':
            raise UserError(_('请先生成比价矩阵。'))

        winner_lines = self.line_ids.filtered('is_winner')
        if not winner_lines:
            raise UserError(_('请在比价矩阵中标记中标行（勾选"中标"列）。'))
        if not self.recommend_reason:
            raise UserError(_('请填写推荐说明。'))

        category = self.env['approval.category'].search([
            ('code', '=', self.approval_category_code),
        ], limit=1)
        if not category:
            raise UserError(_(
                '未找到审批类型编码 "%s"，请联系管理员在 approval_cn 中配置。'
            ) % self.approval_category_code)

        flow = self.flow_id
        if not flow:
            flow = self.env['approval.flow'].search([
                ('category_id', '=', category.id),
                ('active', '=', True),
            ], limit=1)
        if not flow:
            raise UserError(_('审批类型 "%s" 下没有可用的审批流程，请先配置。') % category.name)

        request = self.env['approval.request'].create({
            'name': _('比价定标审批: %s') % self.name,
            'category_id': category.id,
            'flow_id': flow.id,
            'model_name': self._name,
            'res_id': self.id,
            'res_name': self.name,
            'amount': sum(winner_lines.mapped('total_amount') or [0]),
            'request_user_id': self.env.user.id,
            'description': self._build_approval_description(),
        })
        request.action_submit()
        self.approval_request_id = request.id

        self.state = 'submitted'
        winners = ', '.join(self.winner_partner_ids.mapped('name'))
        self.message_post(
            body=_('推荐供应商: %s，推荐说明：%s')
            % (winners, self.recommend_reason)
        )

    def _build_approval_description(self):
        self.ensure_one()
        lines = []

        lines.append('[比价单]%s' % (self.name or ''))
        lines.append('采购订单：%s' % (self.rfq_id.name or ''))
        if self.company_id:
            lines.append('需求公司：%s' % (self.company_id.name or ''))
        if self.department_id:
            lines.append('需求部门：%s' % (self.department_id.name or ''))

        winner_lines = self.line_ids.filtered('is_winner')
        if winner_lines:
            by_supplier = {}
            for wl in winner_lines:
                p = wl.partner_id
                if p not in by_supplier:
                    by_supplier[p] = []
                by_supplier[p].append(wl)

            lines.append('')
            lines.append('[中标推荐]共%d家供应商' % len(by_supplier))
            for idx, (partner, wls) in enumerate(by_supplier.items(), 1):
                lines.append('%d. %s' % (idx, partner.name or ''))
                for wl in wls:
                    product = wl.product_id.display_name if wl.product_id else '未知'
                    parts = ['物料：%s' % product]
                    parts.append('单价：%.2f' % (wl.unit_price or 0))
                    parts.append('数量：%g' % (wl.quantity or 0))
                    if wl.total_amount:
                        parts.append('总价：%.2f' % wl.total_amount)
                    if wl.delivery_date:
                        parts.append('交货：%s' % wl.delivery_date)
                    lines.append('   %s' % ' | '.join(parts))

            total = sum(wl.total_amount or 0 for wl in winner_lines)
            lines.append('中标总价：%.2f' % total)

        if self.recommend_reason:
            lines.append('')
            lines.append('推荐说明：%s' % self.recommend_reason)

        lines.append('')
        lines.append('[比价矩阵]')
        products = {}
        for line in self.line_ids:
            key = line.product_id.id if line.product_id else 0
            if key not in products:
                products[key] = []
            products[key].append(line)

        for p_id, p_lines in products.items():
            product_name = p_lines[0].product_id.display_name if p_lines[0].product_id else '未知物料'
            qty = p_lines[0].quantity
            lines.append('')
            lines.append('--- %s（数量：%g）---' % (product_name, qty))
            for line in p_lines:
                winner_mark = ' [√中标]' if line.is_winner else ''
                parts = ['供应商：%s%s' % (line.partner_id.name or '未知', winner_mark)]
                if line.brand:
                    parts.append('品牌：%s' % line.brand)
                if line.unit_price:
                    parts.append('含税单价：%.2f' % line.unit_price)
                if line.tax_rate:
                    parts.append('税率：%g%%' % line.tax_rate)
                if line.total_amount:
                    parts.append('总价：%.2f' % line.total_amount)
                if line.delivery_date:
                    parts.append('交货：%s' % line.delivery_date)
                if line.warranty_months:
                    parts.append('质保：%s月' % line.warranty_months)
                lines.append(' | '.join(parts))

        return '\n'.join(lines)

    def action_submit_approval(self):
        self.ensure_one()
        if self.state not in ('compared', 'rejected'):
            raise UserError(_('当前状态不允许提交审批。'))

        category = self.env['approval.category'].search([
            ('code', '=', self.approval_category_code),
        ], limit=1)
        if not category:
            raise UserError(_(
                '未找到审批类型编码 "%s"，请联系管理员在 approval_cn 中配置。'
            ) % self.approval_category_code)

        flow = self.flow_id
        if not flow:
            flow = self.env['approval.flow'].search([
                ('category_id', '=', category.id),
                ('active', '=', True),
            ], limit=1)
        if not flow:
            raise UserError(_('审批类型 "%s" 下没有可用的审批流程，请先配置。') % category.name)

        if self.approval_request_id:
            self.approval_request_id = False

        request = self.env['approval.request'].create({
            'name': _('比价定标审批: %s') % self.name,
            'category_id': category.id,
            'flow_id': flow.id,
            'model_name': self._name,
            'res_id': self.id,
            'res_name': self.name,
            'amount': sum(self.line_ids.mapped('total_amount')) or 0.0,
            'request_user_id': self.env.user.id,
            'description': self._build_approval_description(),
        })
        request.action_submit()
        self.approval_request_id = request.id
        self.state = 'submitted'

    def action_confirm_award(self):
        """定标确认：按供应商拆分创建采购订单，并自动确认"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('定标审批未通过。'))

        winner_lines = self.line_ids.filtered('is_winner')
        if not winner_lines:
            raise UserError(_('没有标记中标的行。'))

        by_supplier = {}
        for wl in winner_lines:
            by_supplier.setdefault(wl.partner_id, []).append(wl)

        created_pos = []
        for partner, wls in by_supplier.items():
            po_lines = []
            for wl in wls:
                po_lines.append((0, 0, {
                    'product_id': wl.product_id.id,
                    'name': wl.product_id.display_name,
                    'product_qty': wl.quantity,
                    'product_uom_id': wl.product_id.uom_id.id,
                    'price_unit': wl.unit_price or 0.0,
                    'date_planned': wl.delivery_date or fields.Date.today(),
                }))

            picking_type = self.env['purchase.order']._get_default_picking_type(self.rfq_id.company_id)

            po = self.env['purchase.order'].create({
                'partner_id': partner.id,
                'company_id': self.rfq_id.company_id.id,
                'department_id': self.rfq_id.department_id.id if hasattr(self.rfq_id, 'department_id') and self.rfq_id.department_id else False,
                'date_order': fields.Datetime.now(),
                'origin': '%s / %s' % (self.rfq_id.origin or self.rfq_id.name, self.name),
                'order_line': po_lines,
                'picking_type_id': picking_type.id,
                'hc_requisition_id': self.rfq_id.hc_requisition_id.id if hasattr(self.rfq_id, 'hc_requisition_id') else False,
                'bid_comparison_id': self.id,
                'approval_state': 'approved',
            })
            created_pos.append(po)
            po.message_post(
                body=_('该采购订单由比价定标（%s）自动生成，供应商：%s，已自动通过审批。')
                % (self.name, partner.name)
            )

        # 更新报价状态
        for line in self.line_ids:
            quote = self.env['hc.supplier.quote'].search([
                ('rfq_id', '=', self.rfq_id.id),
                ('partner_id', '=', line.partner_id.id),
            ], limit=1)
            if quote:
                if line.is_winner:
                    quote.with_context(_bid_award_sync=True).state = 'accepted'
                else:
                    quote.with_context(_bid_award_sync=True).state = 'rejected'

        # 取消原RFQ
        self.rfq_id.button_cancel()
        self.rfq_id.message_post(
            body=_('比价定标完成，已拆分为 %d 个采购订单') % len(created_pos)
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('中标采购订单'),
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', [p.id for p in created_pos])],
        }

    def action_view_approval(self):
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError(_('此比价单还没有关联审批请求。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '审批请求',
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
        }


class BidComparisonLine(models.Model):
    _name = 'hc.bid.comparison.line'
    _description = '比价明细行'

    comparison_id = fields.Many2one(
        'hc.bid.comparison', '比价单',
        required=True, ondelete='cascade',
    )
    product_id = fields.Many2one('product.product', '物料')
    product_uom_id = fields.Many2one('uom.uom', '单位')
    quantity = fields.Float('数量')
    partner_id = fields.Many2one('res.partner', '供应商')
    brand = fields.Char('品牌')
    tax_rate = fields.Float('税率(%)')
    unit_price = fields.Float('含税单价')
    delivery_date = fields.Date('交货期')
    warranty_months = fields.Integer('质保期(月)')
    total_amount = fields.Float('含税总价')
    col_index = fields.Integer('列索引', default=0)

    is_winner = fields.Boolean('中标', default=False)
    winner_comment = fields.Char('中标备注')
