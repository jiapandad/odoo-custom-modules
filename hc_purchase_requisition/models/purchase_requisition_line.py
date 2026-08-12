from odoo import api, fields, models


class PurchaseRequisitionLine(models.Model):
    _name = 'hc.purchase.requisition.line'
    _description = '请购单明细行'
    _order = 'sequence, id'

    requisition_id = fields.Many2one(
        'hc.purchase.requisition', '请购单',
        required=True, ondelete='cascade', index=True,
    )
    sequence = fields.Integer('序号', default=10)

    # ── 物料信息 ──

    product_id = fields.Many2one(
        'product.product', '物料',
        required=True,
        domain="[('type', 'in', ('product', 'consu'))]",
    )
    material_type = fields.Char('种类材质')
    specification = fields.Char('规格型号')
    product_uom_id = fields.Many2one(
        'uom.uom', string='单位',
        required=True,
        ondelete='restrict',
    )

    # ── 需求信息 ──

    quantity = fields.Float(
        '请购数量', required=True, default=1.0,
        digits='Product Unit of Measure',
    )
    usage = fields.Char('用途')
    standard = fields.Char('执行标准')
    date_required = fields.Date('需求日期', required=True)
    note = fields.Text('备注')

    # ── 参考价格 ──

    estimated_unit_price = fields.Float(
        '预估单价', digits='Product Price',
    )
    estimated_subtotal = fields.Float(
        '预估小计',
        compute='_compute_estimated_subtotal',
        store=True,
        digits='Product Price',
    )

    # ── 采购完成状态 ──

    purchase_state = fields.Selection([
        ('pending', '待采购'),
        ('in_progress', '采购中'),
        ('partial', '部分到货'),
        ('done', '已完成'),
    ], '采购状态', default='pending', copy=False)

    # ── 关联信息 ──

    company_id = fields.Many2one(
        'res.company', '需求组织',
        related='requisition_id.company_id', store=True,
    )
    department_id = fields.Many2one(
        'hr.department', '需求部门',
        related='requisition_id.department_id', store=True,
    )

    @api.depends('quantity', 'estimated_unit_price')
    def _compute_estimated_subtotal(self):
        for line in self:
            line.estimated_subtotal = line.quantity * line.estimated_unit_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            # 种类材质不自动填充，由用户手动填写
            # 单位也不再自动填充，需手动选择
            pass
