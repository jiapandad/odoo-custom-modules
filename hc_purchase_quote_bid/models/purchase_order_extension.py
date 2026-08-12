from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    supplier_quote_ids = fields.One2many(
        'hc.supplier.quote', 'rfq_id', '供应商报价',
    )
    quote_count = fields.Integer(
        '报价数', compute='_compute_quote_count', store=True,
    )
    bid_comparison_ids = fields.One2many(
        'hc.bid.comparison', 'rfq_id', '比价单',
    )
    bid_comparison_id = fields.Many2one(
        'hc.bid.comparison', '来源比价单',
        readonly=True, copy=False, index=True,
        help='该采购订单由比价定标自动生成（多供应商拆分）',
    )
    bid_count = fields.Integer(
        '比价次数', compute='_compute_bid_count', store=True,
    )
    is_awarded = fields.Boolean(
        '已定标', compute='_compute_is_awarded', store=True,
    )
    bid_summary = fields.Text(
        '比价摘要', compute='_compute_bid_summary',
    )
    has_approved_bid_comparison = fields.Boolean(
        '存在已批准比价单', compute='_compute_has_approved_bid_comparison', store=True,
    )
    hc_requisition_id = fields.Many2one(
        'hc.purchase.requisition', '来源请购单',
        compute='_compute_hc_requisition',
        help='通过 origin 自动关联到请购单',
    )
    has_requisition = fields.Boolean(
        '有请购单', compute='_compute_hc_requisition',
    )
    related_quote_id = fields.Many2one(
        'hc.supplier.quote', '来源报价单',
        compute='_compute_related_quote',
        help='比价定标拆分后，该供应商对应的报价单',
    )
    has_related_quote = fields.Boolean(
        '有关联报价单', compute='_compute_related_quote',
    )

    @api.depends('bid_comparison_id', 'partner_id')
    def _compute_related_quote(self):
        for po in self:
            po.related_quote_id = False
            po.has_related_quote = False
            if po.bid_comparison_id and po.bid_comparison_id.rfq_id:
                quote = self.env['hc.supplier.quote'].search([
                    ('rfq_id', '=', po.bid_comparison_id.rfq_id.id),
                    ('partner_id', '=', po.partner_id.id),
                ], limit=1)
                if quote:
                    po.related_quote_id = quote.id
                    po.has_related_quote = True

    @api.depends('origin')
    def _compute_hc_requisition(self):
        import re
        for po in self:
            po.hc_requisition_id = False
            po.has_requisition = False
            req = False

            # 1. 优先通过 origin 查找（直接来自请购单）
            if po.origin:
                origin = po.origin.strip()
                req = self.env['hc.purchase.requisition'].search([
                    ('name', '=', origin)
                ], limit=1)
                if not req:
                    m = re.search(r'QG/\d{4}/\d{4}', origin)
                    if m:
                        req = self.env['hc.purchase.requisition'].search([
                            ('name', '=', m.group(0))
                        ], limit=1)

            # 2. 通过 hc_contract_id 间接查找（从框架合同下子 PO）
            if not req and hasattr(po, 'hc_contract_id') and po.hc_contract_id and po.hc_contract_id.rfq_id:
                rfq = po.hc_contract_id.rfq_id
                if rfq.origin:
                    req = self.env['hc.purchase.requisition'].search([
                        ('name', '=', rfq.origin)
                    ], limit=1)

            if req:
                po.hc_requisition_id = req
                po.has_requisition = True

    def action_view_requisition(self):
        """打开来源请购单"""
        self.ensure_one()
        if not self.hc_requisition_id:
            raise UserError(_('未找到关联的请购单。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '请购单',
            'res_model': 'hc.purchase.requisition',
            'res_id': self.hc_requisition_id.id,
            'view_mode': 'form',
        }

    def action_view_related_bid(self):
        """打开来源比价单"""
        self.ensure_one()
        if not self.bid_comparison_id:
            raise UserError(_('未找到关联的比价单。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '比价单',
            'res_model': 'hc.bid.comparison',
            'res_id': self.bid_comparison_id.id,
            'view_mode': 'form',
        }

    def action_view_related_quote(self):
        """打开来源报价单"""
        self.ensure_one()
        if not self.related_quote_id:
            raise UserError(_('未找到关联的供应商报价单。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '供应商报价',
            'res_model': 'hc.supplier.quote',
            'res_id': self.related_quote_id.id,
            'view_mode': 'form',
        }

    @api.depends('bid_comparison_ids.state')
    def _compute_has_approved_bid_comparison(self):
        for po in self:
            po.has_approved_bid_comparison = bool(
                po.bid_comparison_ids.filtered(lambda b: b.state == 'approved')
            )

    @api.depends('supplier_quote_ids')
    def _compute_quote_count(self):
        for po in self:
            po.quote_count = len(po.supplier_quote_ids)

    @api.depends('bid_comparison_ids')
    def _compute_bid_count(self):
        for po in self:
            po.bid_count = len(po.bid_comparison_ids)

    @api.depends('bid_comparison_ids.state')
    def _compute_is_awarded(self):
        for po in self:
            po.is_awarded = any(
                b.state == 'approved' for b in po.bid_comparison_ids
            )

    @api.depends('supplier_quote_ids', 'bid_comparison_ids')
    def _compute_bid_summary(self):
        """生成比价摘要，用于审批说明。紧凑排版，兼顾桌面端和移动端。"""
        for po in self:
            lines = []
            lines.append('【采购订单】%s' % (po.name or ''))

            # 采购物料
            lines.append('【物料】')
            for line in po.order_line:
                uom = line.product_uom_id.name or ''
                lines.append('· %s | 数量：%g%s' % (
                    line.product_id.display_name or '',
                    line.product_qty,
                    uom,
                ))

            # 推荐供应商：已提交审批或已批准的都显示
            award_bid = po.bid_comparison_ids.filtered(
                lambda b: b.state in ('approved', 'submitted')
            )[:1]
            if award_bid:
                winners = ', '.join(award_bid.winner_partner_ids.mapped('name'))
                lines.append('【推荐供应商】%s' % (winners or ''))
                if award_bid.recommend_reason:
                    lines.append('推荐理由：%s' % award_bid.recommend_reason)

            # 供应商报价对比
            if po.supplier_quote_ids:
                lines.append('【报价对比】')
                for idx, quote in enumerate(po.supplier_quote_ids, 1):
                    partner = quote.partner_id.name or '供应商%s' % idx
                    for quote_line in quote.line_ids:
                        parts = ['%d. %s' % (idx, partner)]
                        parts.append('物料：%s' % (quote_line.product_id.display_name or ''))
                        if quote_line.brand:
                            parts.append('品牌：%s' % quote_line.brand)
                        if quote_line.unit_price:
                            parts.append('单价：%s' % quote_line.unit_price)
                        if quote_line.tax_rate:
                            parts.append('税率：%s%%' % quote_line.tax_rate)
                        if quote_line.delivery_date:
                            parts.append('交货：%s' % quote_line.delivery_date)
                        if quote_line.warranty_months:
                            parts.append('质保：%s月' % quote_line.warranty_months)
                        lines.append(' | '.join(parts))

            po.bid_summary = '\n'.join(lines)

    def _prepare_approval_request(self):
        """扩展审批请求内容，加入比价摘要"""
        res = super()._prepare_approval_request()
        if self.bid_summary:
            original_desc = res.get('description', '') or ''
            res['description'] = '\n'.join([
                original_desc,
                self.bid_summary,
            ]).strip()
        return res

    def action_add_quote(self):
        """打开供应商报价录入表单"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '录入供应商报价',
            'res_model': 'hc.supplier.quote',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_rfq_id': self.id},
        }

    def action_view_quotes(self):
        """查看所有供应商报价"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '供应商报价',
            'res_model': 'hc.supplier.quote',
            'view_mode': 'list,form',
            'domain': [('rfq_id', '=', self.id)],
        }

    def button_cancel(self):
        """取消时清除审批关联，重置报价和比价单，允许二次发起"""
        for order in self:
            if order.bid_comparison_id:
                # 比价定标拆分的PO不允许取消
                raise UserError(_(
                    '采购订单 %s 由比价定标自动生成，不允许取消。请通过原比价单管理。'
                ) % order.name)
            if order.approval_request_id:
                if order.approval_state == 'submitted':
                    order.approval_request_id.action_cancel()
                order.approval_request_id = False
                order.approval_state = 'draft'

            # 重置供应商报价为可编辑状态
            order.supplier_quote_ids.filtered(
                lambda q: q.state in ('submitted', 'accepted', 'rejected')
            ).with_context(_bid_award_sync=True).write({'state': 'draft'})

            # 重置比价单为草稿
            order.bid_comparison_ids.filtered(
                lambda b: b.state in ('submitted', 'approved', 'rejected', 'compared')
            ).write({'state': 'draft'})

        return super(PurchaseOrder, self).button_cancel()

    def button_draft(self):
        """退回草稿时清除审批关联，重置报价和比价单，允许二次发起"""
        for order in self:
            if order.bid_comparison_id:
                raise UserError(_(
                    '采购订单 %s 由比价定标自动生成，不允许退回草稿。请通过原比价单管理。'
                ) % order.name)
            if order.approval_request_id:
                order.approval_request_id = False
                order.approval_state = 'draft'

            # 重置供应商报价为可编辑状态
            order.supplier_quote_ids.filtered(
                lambda q: q.state in ('submitted', 'accepted', 'rejected')
            ).with_context(_bid_award_sync=True).write({'state': 'draft'})

            # 重置比价单为草稿
            order.bid_comparison_ids.filtered(
                lambda b: b.state in ('submitted', 'approved', 'rejected', 'compared')
            ).write({'state': 'draft'})

        return super(PurchaseOrder, self).button_draft()

    def unlink(self):
        for po in self:
            if po.bid_comparison_id:
                raise UserError(_(
                    '采购订单 %s 由比价定标自动生成，不允许删除。请通过原比价单管理。'
                ) % po.name)
            if po.bid_comparison_ids or po.supplier_quote_ids:
                if po.state not in ('draft', 'cancel'):
                    raise UserError(_(
                        '采购订单 "%s" 已存在报价/比价记录，不允许删除。'
                    ) % po.name)
        return super(PurchaseOrder, self).unlink()

    def action_submit_approval(self):
        """提交审批：若比价单已批准，则自动通过，不再重复提交"""
        for order in self:
            approved_bid = order.bid_comparison_ids.filtered(
                lambda b: b.state == 'approved'
            )[:1]
            if approved_bid:
                # 已存在已批准的比价单，直接标记采购订单审批通过
                order.approval_state = 'approved'
                order.message_post(
                    body=_('采购订单 %s 已基于比价定标结果（%s）自动通过审批。')
                    % (order.name, approved_bid.name)
                )
                return True
        return super(PurchaseOrder, self).action_submit_approval()

    def button_confirm(self):
        """确认订单：比价单已批准则自动通过，否则引导用户先完成比价审批"""
        for order in self:
            # 比价定标自动拆分生成的 PO，审批状态已为 approved，跳过比价检查
            if order.bid_comparison_id:
                continue
            if order.bid_comparison_ids:
                if order.has_approved_bid_comparison:
                    approved_bid = order.bid_comparison_ids.filtered(
                        lambda b: b.state == 'approved'
                    )[:1]
                    if approved_bid and approved_bid.approval_request_id:
                        order.approval_request_id = approved_bid.approval_request_id.id
                        order.approval_state = 'approved'
                else:
                    # 存在比价单但未批准，引导用户去审批
                    pending = order.bid_comparison_ids.filtered(
                        lambda b: b.state == 'submitted'
                    )
                    if pending:
                        raise UserError(_(
                            '该采购订单有 %d 份比价单正在等待审批，'
                            '请先完成比价定标审批后再确认订单。'
                        ) % len(pending))
                    raise UserError(_(
                        '该采购订单存在比价单，请先完成比价定标流程后再确认订单。'
                    ))
        return super().button_confirm()

    def action_view_bid_comparisons(self):
        """查看比价单；若只有一份草稿/已比价的比价单，自动刷新矩阵以纳入最新报价"""
        self.ensure_one()
        if len(self.bid_comparison_ids) == 1:
            bid = self.bid_comparison_ids[0]
            if bid.state in ('draft', 'compared'):
                bid.action_generate_comparison()
            return {
                'type': 'ir.actions.act_window',
                'name': '比价单',
                'res_model': 'hc.bid.comparison',
                'res_id': bid.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': '比价单',
            'res_model': 'hc.bid.comparison',
            'view_mode': 'list,form',
            'domain': [('rfq_id', '=', self.id)],
        }

    def action_create_bid_comparison(self):
        """创建比价单"""
        self.ensure_one()
        quotes = self.supplier_quote_ids.filtered(
            lambda q: q.state == 'submitted'
        )
        if not quotes:
            raise UserError(_('请先录入供应商报价。'))

        bid = self.env['hc.bid.comparison'].create({
            'rfq_id': self.id,
        })
        bid.action_generate_comparison()
        return {
            'type': 'ir.actions.act_window',
            'name': '比价单',
            'res_model': 'hc.bid.comparison',
            'res_id': bid.id,
            'view_mode': 'form',
        }
