from odoo import api, fields, models


class ApprovalCountersign(models.Model):
    _name = 'approval.countersign'
    _description = '加签记录'
    _order = 'create_date'
    _rec_name = 'display_name'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        ondelete='cascade', index=True,
    )
    node_id = fields.Many2one(
        'approval.node', string='所属节点', required=True,
        ondelete='restrict',
    )
    from_user_id = fields.Many2one(
        'res.users', string='加签人', required=True,
    )
    to_user_id = fields.Many2one(
        'res.users', string='被加签人', required=True,
    )
    position = fields.Selection([
        ('before', '前加签'),
        ('after', '后加签'),
    ], string='加签位置', required=True, default='after',
       help='前加签：在加签人之前审批；后加签：在加签人之后审批',
    )
    comment = fields.Text(string='加签原因')
    record_id = fields.Many2one(
        'approval.record', string='关联审批记录',
        ondelete='set null',
    )
    new_record_id = fields.Many2one(
        'approval.record', string='加签审批记录',
        ondelete='set null',
        help='为加签人创建的审批记录',
    )
    state = fields.Selection([
        ('pending', '待处理'),
        ('done', '已完成'),
        ('cancelled', '已取消'),
    ], string='状态', default='pending', index=True,
    )
    display_name = fields.Char(
        string='显示名称', compute='_compute_display_name',
    )

    @api.depends('from_user_id', 'to_user_id', 'position', 'state')
    def _compute_display_name(self):
        for cs in self:
            pos = '前加签' if cs.position == 'before' else '后加签'
            cs.display_name = f'[{pos}] {cs.from_user_id.name} → {cs.to_user_id.name}'
