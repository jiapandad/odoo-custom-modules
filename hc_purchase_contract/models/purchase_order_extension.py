from odoo import api, fields, models, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    hc_contract_id = fields.Many2one(
        'hc.purchase.contract', '采购合同',
        ondelete='set null', index=True,
        help='关联的采购合同（框架合同或单次合同）',
    )
    contract_name = fields.Char(
        '合同编号', related='hc_contract_id.name', store=True,
    )
    contract_state = fields.Selection(
        '合同状态', related='hc_contract_id.state', store=True,
    )
    contract_button_label = fields.Char(
        '合同按钮标签', compute='_compute_contract_button_label',
    )

    @api.depends('hc_contract_id', 'contract_name')
    def _compute_contract_button_label(self):
        for po in self:
            po.contract_button_label = po.contract_name or '未关联'

    def action_open_contract(self):
        """从PO打开采购合同：有则查看，无则查看同供应商合同列表"""
        self.ensure_one()
        if self.hc_contract_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('采购合同'),
                'res_model': 'hc.purchase.contract',
                'res_id': self.hc_contract_id.id,
                'view_mode': 'form',
            }

        # 未关联合同时，打开同供应商的合同列表，便于选择或新建
        domain = []
        if self.partner_id:
            domain = [('partner_id', '=', self.partner_id.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('采购合同'),
            'res_model': 'hc.purchase.contract',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_partner_id': self.partner_id.id if self.partner_id else False,
                'search_default_partner_id': self.partner_id.id if self.partner_id else False,
            },
        }
