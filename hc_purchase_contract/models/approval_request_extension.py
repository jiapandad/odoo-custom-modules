from odoo import models, _
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    def action_view_source_contract(self):
        """从审批请求跳转到关联的采购合同"""
        self.ensure_one()
        if self.model_name != 'hc.purchase.contract' or not self.res_id:
            return
        contract = self.env['hc.purchase.contract'].browse(self.res_id)
        if not contract.exists():
            raise UserError(_('关联的采购合同不存在或已被删除。'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('采购合同'),
            'res_model': 'hc.purchase.contract',
            'res_id': contract.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_download_contract_file(self):
        """从审批请求直接下载合同文件"""
        self.ensure_one()
        if self.model_name != 'hc.purchase.contract' or not self.res_id:
            return
        contract = self.env['hc.purchase.contract'].browse(self.res_id)
        if not contract.exists():
            raise UserError(_('关联的采购合同不存在或已被删除。'))
        if not contract.contract_file:
            raise UserError(_('该合同未上传合同文件。'))

        base_url = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url'
        )
        return {
            'type': 'ir.actions.act_url',
            'url': '%s/web/content/hc.purchase.contract/%s/contract_file/%s'
                   '?download=true'
                   % (base_url, contract.id,
                      contract.contract_file_name or 'contract.pdf'),
            'target': 'new',
        }
