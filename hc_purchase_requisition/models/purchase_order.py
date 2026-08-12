from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    department_id = fields.Many2one(
        'hr.department', '需求部门',
        copy=False, index=True,
        help='采购订单对应的需求部门，由请购单或手动指定。',
    )
    hc_requisition_id = fields.Many2one(
        'hc.purchase.requisition', '来源请购单',
        readonly=True, copy=False,
        help='由请购单生成的询价单',
    )
    hc_requisition_applicant_id = fields.Many2one(
        'hr.employee', '申请人',
        compute='_compute_from_hc_requisition', store=True, readonly=True,
    )
    hc_requisition_department_id = fields.Many2one(
        'hr.department', '来源需求部门',
        compute='_compute_from_hc_requisition', store=True, readonly=True,
    )
    hc_requisition_applicant_user_id = fields.Many2one(
        'res.users', '申请人账号',
        compute='_compute_from_hc_requisition', store=True, readonly=True,
    )

    @staticmethod
    def _get_default_picking_type(company):
        picking_type = company.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id.company_id', '=', company.id),
        ], limit=1)
        if not picking_type:
            picking_type = company.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
            ], limit=1)
        if not picking_type:
            from odoo.exceptions import UserError
            raise UserError(
                '系统中没有配置任何收货仓库，请先在库存管理中创建仓库。'
            )
        return picking_type

    @api.depends('hc_requisition_id')
    def _compute_from_hc_requisition(self):
        for po in self:
            req = po.hc_requisition_id
            if req:
                po.hc_requisition_applicant_id = req.applicant_id
                po.hc_requisition_department_id = req.department_id
                po.hc_requisition_applicant_user_id = req.applicant_user_id
            else:
                po.hc_requisition_applicant_id = False
                po.hc_requisition_department_id = False
                po.hc_requisition_applicant_user_id = False

    @api.onchange('project_id')
    def _onchange_project_id_check(self):
        if self.hc_requisition_id and self._origin and self._origin.project_id:
            if self.project_id != self._origin.project_id:
                from odoo.exceptions import UserError
                from odoo import _
                raise UserError(_('此采购订单由请购单生成，关联项目不允许修改。'))