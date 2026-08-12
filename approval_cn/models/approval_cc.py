from odoo import api, fields, models


class ApprovalCc(models.Model):
    _name = 'approval.cc'
    _description = '抄送记录'
    _order = 'create_date'
    _rec_name = 'display_name'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        ondelete='cascade', index=True,
    )
    node_id = fields.Many2one(
        'approval.node', string='抄送节点',
    )
    user_id = fields.Many2one(
        'res.users', string='抄送人', required=True, index=True,
    )
    state = fields.Selection([
        ('unread', '未读'),
        ('read', '已读'),
    ], string='状态', default='unread',
    )
    read_date = fields.Datetime(string='阅读时间')
    display_name = fields.Char(
        string='显示名称', compute='_compute_display_name',
    )

    @api.depends('node_id', 'user_id', 'state')
    def _compute_display_name(self):
        for record in self:
            node_name = record.node_id.name or ''
            user_name = record.user_id.name or ''
            record.display_name = f'抄送：{node_name} → {user_name}'

    def action_mark_read(self):
        self.write({
            'state': 'read',
            'read_date': fields.Datetime.now(),
        })