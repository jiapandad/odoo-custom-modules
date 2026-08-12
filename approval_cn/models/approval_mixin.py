from odoo import fields, models, _
from odoo.exceptions import UserError


class ApprovalMixin(models.AbstractModel):
    _name = 'approval.mixin'
    _description = '审批混入类'

    approval_state = fields.Selection([
        ('none', '无需审批'),
        ('pending', '待提交审批'),
        ('submitted', '审批中'),
        ('approved', '审批通过'),
        ('rejected', '审批驳回'),
        ('cancelled', '已撤回'),
    ], string='审批状态', default='none', tracking=True, copy=False,
    )
    approval_request_id = fields.Many2one(
        'approval.request', string='审批请求',
        readonly=True, copy=False,
    )
    approval_request_ids = fields.One2many(
        'approval.request', 'res_id',
        domain="[('model_name', '=', model_name)]",
        string='审批历史', readonly=True,
    )
    approval_category_code = fields.Char(
        string='审批类型编码',
        help='关联的审批类型编码，用于自动匹配审批流程',
    )

    def _get_approval_amount(self):
        return 0.0

    def _get_approval_name(self):
        return self.display_name or ''

    def _get_approval_attachments(self):
        return self.env['ir.attachment'].browse()

    # ── 回调钩子（子类可覆写） ──

    def _on_approval_approved(self):
        pass

    def _on_approval_rejected(self):
        pass

    def _on_approval_cancelled(self):
        pass

    def _on_approval_submitted(self):
        pass

    # ── 审批操作 ──

    def action_submit_approval(self):
        self.ensure_one()
        if self.approval_state not in ('none', 'pending', 'rejected', 'cancelled'):
            raise UserError(_('当前状态不允许提交审批。'))

        category = self.env['approval.category'].search([
            ('code', '=', self.approval_category_code),
        ], limit=1)
        if not category:
            raise UserError(_(
                '未找到审批类型编码 "%s" 对应的审批类型，请联系管理员配置。'
            ) % self.approval_category_code)

        amount = self._get_approval_amount()
        flow = self.env['approval.flow']._get_flow_for_category(
            self.approval_category_code, amount,
        )
        if not flow:
            raise UserError(_(
                '未找到审批类型 "%s" 对应的审批流程，请联系管理员配置。'
            ) % category.name)

        request = self.env['approval.request'].create({
            'name': self._get_approval_name(),
            'category_id': category.id,
            'flow_id': flow.id,
            'model_name': self._name,
            'res_id': self.id,
            'res_name': self.display_name,
            'amount': amount,
            'request_user_id': self.env.user.id,
        })

        attachments = self._get_approval_attachments()
        if attachments:
            attachments.copy({
                'res_model': 'approval.request',
                'res_id': request.id,
            })

        self.write({
            'approval_state': 'submitted',
            'approval_request_id': request.id,
        })

        request.action_submit()
        self._on_approval_submitted()
        return request

    def action_view_approval_request(self):
        self.ensure_one()
        if not self.approval_request_id:
            raise UserError(_('此记录没有关联的审批请求。'))
        return {
            'type': 'ir.actions.act_window',
            'name': '审批请求',
            'res_model': 'approval.request',
            'res_id': self.approval_request_id.id,
            'view_mode': 'form',
        }

    def action_view_approval_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '审批历史',
            'res_model': 'approval.request',
            'view_mode': 'list,form',
            'domain': [('model_name', '=', self._name), ('res_id', '=', self.id)],
        }

    def write(self, vals):
        res = super().write(vals)
        if 'approval_state' in vals:
            for record in self:
                if self.env.context.get('_approval_syncing'):
                    continue
                new_state = vals['approval_state']
                if new_state == 'approved':
                    record._on_approval_approved()
                elif new_state == 'rejected':
                    record._on_approval_rejected()
                elif new_state == 'cancelled':
                    record._on_approval_cancelled()
        return res