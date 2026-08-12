from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    approval_request_id = fields.Many2one(
        'approval.request', string='审批申请',
        readonly=True, copy=False,
    )
    approval_state = fields.Char(
        string='审批状态', default='draft',
    )
    approval_category_id = fields.Many2one(
        'approval.category', string='审批类型',
        domain=[('model_name', '=', 'purchase.order')],
        default=lambda self: self._get_default_approval_category(),
    )

    @api.model
    def _get_default_approval_category(self):
        category = self.env['approval.category'].search(
            [('model_name', '=', 'purchase.order')], limit=1
        )
        return category.id if category else False

    def _prepare_approval_request(self):
        self.ensure_one()
        flow = self.env['approval.flow'].search(
            [('category_id', '=', self.approval_category_id.id), ('active', '=', True)],
            limit=1
        )
        if not flow:
            raise UserError(_('审批类型 "%s" 下没有可用的审批流程，请先配置。') % self.approval_category_id.name)
        return {
            'name': _('采购审批: %s') % self.name,
            'category_id': self.approval_category_id.id,
            'flow_id': flow.id,
            'model_name': 'purchase.order',
            'res_id': self.id,
            'res_name': self.name,
            'amount': self.amount_total,
            'request_user_id': self.env.user.id,
            'request_date': fields.Datetime.now(),
        }

    def action_submit_approval(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的采购订单才能提交审批。'))
        if self.approval_request_id:
            raise UserError(_('该采购订单已提交审批。'))
        if not self.approval_category_id:
            raise UserError(_('请先选择审批类型。'))

        approval_request = self.env['approval.request'].create(
            self._prepare_approval_request()
        )
        self.approval_request_id = approval_request.id
        approval_request.action_submit()

    def action_view_approval(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('审批申请'),
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def button_confirm(self):
        for order in self:
            if not order.approval_category_id:
                continue
            # 已审批通过的（如比价定标自动生成、手动审批通过等），跳过审批检查
            if order.approval_state == 'approved':
                continue
            if not order.approval_request_id:
                approval_request = self.env['approval.request'].create(
                    order._prepare_approval_request()
                )
                order.approval_request_id = approval_request.id
                approval_request.action_submit()
                raise UserError(_(
                    '采购订单 %s 的审批已自动提交，请等待审批通过后再确认订单。'
                ) % order.name)
            if order.approval_state != 'approved':
                raise UserError(_(
                    '采购订单 %s 尚未通过审批，无法确认。'
                    '请等待审批完成后再操作。',
                    order.name
                ))
        return super().button_confirm()

    def button_cancel(self):
        for order in self:
            if order.approval_request_id:
                if order.approval_state == 'draft':
                    order.approval_request_id.action_cancel()
                elif order.approval_state == 'submitted':
                    order.approval_request_id.action_reject()
        return super().button_cancel()

    def button_draft(self):
        for order in self:
            if order.approval_request_id:
                if order.approval_state in ('approved', 'rejected'):
                    raise UserError(_(
                        '采购订单 %s 的审批已完成，无法重置为草稿。',
                        order.name
                    ))
                if order.approval_state == 'submitted':
                    order.approval_request_id.action_cancel()
                order.approval_request_id = False
                order.approval_state = 'draft'
        return super().button_draft()
