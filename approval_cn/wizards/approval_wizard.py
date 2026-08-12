from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalRejectWizard(models.TransientModel):
    _name = 'approval.reject.wizard'
    _description = '驳回审批向导'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        readonly=True,
    )
    reason = fields.Text(string='驳回原因', required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.request_id:
            raise UserError(_('审批请求不存在。'))
        self.request_id.action_reject(reason=self.reason)
        return {'type': 'ir.actions.act_window_close'}


class ApprovalTransferWizard(models.TransientModel):
    _name = 'approval.transfer.wizard'
    _description = '转交审批向导'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        readonly=True,
    )
    target_user_id = fields.Many2one(
        'res.users', string='转交给', required=True,
        domain="[('id', '!=', uid), ('share', '=', False)]",
    )

    def action_confirm_transfer(self):
        self.ensure_one()
        if not self.request_id:
            raise UserError(_('审批请求不存在。'))
        if not self.target_user_id:
            raise UserError(_('请选择转交目标用户。'))
        self.request_id.action_transfer(self.target_user_id.id)
        return {'type': 'ir.actions.act_window_close'}


class ApprovalCommentWizard(models.TransientModel):
    _name = 'approval.comment.wizard'
    _description = '审批意见向导'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        readonly=True,
    )
    comment = fields.Text(string='审批意见')

    def action_confirm_approve(self):
        self.ensure_one()
        if not self.request_id:
            raise UserError(_('审批请求不存在。'))
        self.request_id.action_approve(comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}