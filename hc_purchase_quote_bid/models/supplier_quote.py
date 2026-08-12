from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SupplierQuote(models.Model):
    _name = 'hc.supplier.quote'
    _description = '供应商报价单（采购员录入）'
    _order = 'create_date desc'

    name = fields.Char('报价编号', compute='_compute_name', store=True)
    rfq_id = fields.Many2one(
        'purchase.order', '对应询价单',
        required=True, ondelete='cascade', index=True,
        domain="[('state', 'in', ('draft', 'sent'))]",
    )
    partner_id = fields.Many2one(
        'res.partner', '供应商',
        required=True,
        domain="[('supplier_rank', '>', 0)]",
    )
    entered_by = fields.Many2one(
        'res.users', '录入人',
        default=lambda self: self.env.user,
    )
    quote_date = fields.Date('报价日期', default=fields.Date.today)
    quote_source = fields.Selection([
        ('email', '邮件'),
        ('wechat', '微信'),
        ('phone', '电话'),
        ('fax', '传真'),
        ('other', '其他'),
    ], '报价来源', default='email')

    state = fields.Selection([
        ('draft', '录入中'),
        ('submitted', '已录入'),
        ('accepted', '中标'),
        ('rejected', '未中标'),
    ], '状态', default='draft')

    line_ids = fields.One2many(
        'hc.supplier.quote.line', 'quote_id', '报价明细',
    )
    attachment_ids = fields.Many2many(
        'ir.attachment', string='供应商报价附件',
        help='供应商邮件截图或盖章报价单扫描件',
    )
    invoice_type = fields.Selection([
        ('vat_special', '增值税专用发票'),
        ('vat_normal', '增值税普通发票'),
        ('e_vat_special', '电子增值税专用发票'),
    ], '发票类型')
    has_certificate = fields.Boolean('具备三证')
    has_stamped_quote = fields.Boolean('已盖章报价单')
    note = fields.Text('供应商说明')
    company_id = fields.Many2one(
        'res.company', '公司',
        related='rfq_id.company_id', store=True,
    )
    currency_id = fields.Many2one(
        'res.currency', '币种',
        related='rfq_id.currency_id',
    )
    total_amount = fields.Monetary(
        '报价总额', compute='_compute_total', store=True,
        currency_field='currency_id',
    )

    # === 询价单产品摘要（只读，方便录入时参考） ===
    rfq_product_summary = fields.Html(
        '询价单产品', compute='_compute_rfq_product_summary',
        sanitize=False,
    )

    @api.depends('rfq_id.order_line', 'rfq_id.order_line.product_id',
                  'rfq_id.order_line.product_qty', 'rfq_id.order_line.product_uom_id')
    def _compute_rfq_product_summary(self):
        for quote in self:
            if not quote.rfq_id:
                quote.rfq_product_summary = ''
                continue
            rows = []
            for i, line in enumerate(quote.rfq_id.order_line, 1):
                name = line.product_id.display_name if line.product_id else '/'
                qty = line.product_qty
                uom = (line.product_uom_id or line.product_id.uom_id).name or ''
                rows.append(
                    f'<tr>'
                    f'<td style="padding:6px 12px;width:50px">{i}</td>'
                    f'<td style="padding:6px 12px">{name}</td>'
                    f'<td style="padding:6px 12px;width:80px;text-align:right">{qty:g}</td>'
                    f'<td style="padding:6px 12px;width:60px">{uom}</td>'
                    f'</tr>'
                )
            quote.rfq_product_summary = (
                '<table style="width:100%;border-collapse:collapse;border:1px solid #ddd">'
                '<thead><tr style="background:#f5f5f5">'
                '<th style="padding:6px 12px;width:50px;text-align:left">序号</th>'
                '<th style="padding:6px 12px;text-align:left">产品</th>'
                '<th style="padding:6px 12px;width:80px;text-align:right">数量</th>'
                '<th style="padding:6px 12px;width:60px;text-align:left">单位</th>'
                '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
            )

    @api.depends('rfq_id.name', 'partner_id.name')
    def _compute_name(self):
        for q in self:
            rfq_name = q.rfq_id.name or ''
            partner_name = q.partner_id.name or ''
            q.name = f'{rfq_name} / {partner_name}'

    @api.depends('line_ids.total_amount')
    def _compute_total(self):
        for q in self:
            q.total_amount = sum(line.total_amount for line in q.line_ids)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        rfq_id = defaults.get('rfq_id') or self.env.context.get('default_rfq_id')
        if rfq_id and 'line_ids' in fields_list:
            defaults['line_ids'] = self._prepare_quote_lines_from_rfq(rfq_id)
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('rfq_id') and not vals.get('line_ids'):
                vals['line_ids'] = self._prepare_quote_lines_from_rfq(vals['rfq_id'])
        return super().create(vals_list)

    def _prepare_quote_lines_from_rfq(self, rfq_id):
        """从询价单生成报价行的初始值，在 create 中直接注入，确保表单首次渲染即显示"""
        line_vals = []
        rfq = self.env['purchase.order'].browse(rfq_id)
        if rfq.exists():
            for po_line in rfq.order_line:
                line_vals.append((0, 0, {
                    'rfq_line_id': po_line.id,
                    'product_id': po_line.product_id.id,
                    'product_uom_id': (po_line.product_uom_id or po_line.product_id.uom_id).id,
                    'quantity': po_line.product_qty,
                }))
        return line_vals

    def action_submit(self):
        for record in self:
            if not record.line_ids:
                raise UserError(_('请先录入报价明细。'))
            record.state = 'submitted'

    def write(self, vals):
        """提交后禁止编辑"""
        for quote in self:
            if quote.state in ('submitted', 'accepted', 'rejected'):
                if not self.env.context.get('_bid_award_sync'):
                    raise UserError(_(
                        '供应商报价 "%s" 已提交，不允许编辑。请先撤回相关比价单。'
                    ) % quote.name)
        return super().write(vals)

    def button_reset_draft(self):
        """重置为草稿"""
        for quote in self:
            if quote.state == 'draft':
                continue
            quote.state = 'draft'

    def unlink(self):
        for quote in self:
            if quote.state != 'draft':
                raise UserError(_('只能删除草稿状态的供应商报价。'))
        return super().unlink()


class SupplierQuoteLine(models.Model):
    _name = 'hc.supplier.quote.line'
    _description = '供应商报价明细行'

    quote_id = fields.Many2one(
        'hc.supplier.quote', '报价单',
        required=True, ondelete='cascade',
    )
    rfq_line_id = fields.Many2one(
        'purchase.order.line', '询价行',
        domain="[('order_id', '=', parent.rfq_id)]",
    )
    product_id = fields.Many2one(
        'product.product', '物料', required=True,
    )
    product_uom_id = fields.Many2one(
        'uom.uom', '单位',
        required=True,
        ondelete='restrict',
    )
    brand = fields.Char('品牌')
    tax_rate = fields.Float('税率(%)', default=13)
    unit_price = fields.Float('含税单价')
    quantity = fields.Float('数量', default=1.0)
    delivery_date = fields.Date('交货期')
    warranty_months = fields.Integer('质保期(月)')
    total_amount = fields.Float(
        '含税总价', compute='_compute_total_amount', store=True,
    )
    note = fields.Char('备注')

    @api.depends('unit_price', 'quantity')
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = line.unit_price * line.quantity

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id
