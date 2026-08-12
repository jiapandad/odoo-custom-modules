from odoo import api, fields, models


class ApprovalRecord(models.Model):
    _name = 'approval.record'
    _description = '审批记录'
    _order = 'create_date'
    _rec_name = 'display_name'

    request_id = fields.Many2one(
        'approval.request', string='审批请求', required=True,
        ondelete='cascade', index=True,
    )
    node_id = fields.Many2one(
        'approval.node', string='审批节点', required=True,
        ondelete='restrict',
    )
    approver_id = fields.Many2one(
        'res.users', string='审批人/办理人', required=True,
        index=True,
    )
    record_type = fields.Selection([
        ('approver', '审批'),
        ('handler', '办理'),
    ], string='记录类型', default='approver', required=True,
    )
    state = fields.Selection([
        ('pending', '待处理'),
        ('approved', '已通过'),
        ('rejected', '已驳回'),
        ('cancelled', '已取消'),
        ('waiting', '等待中'),
    ], string='状态', default='pending', index=True,
    )
    comment = fields.Text(string='处理意见')
    approved_date = fields.Datetime(string='处理时间')
    last_reminder_date = fields.Datetime(string='最近提醒时间')
    delegate_from_id = fields.Many2one(
        'res.users', string='委托来源',
        help='此记录是因为谁的委托而创建的',
    )
    countersign_id = fields.Many2one(
        'approval.countersign', string='加签记录',
        ondelete='set null',
    )
    display_name = fields.Char(
        string='显示名称', compute='_compute_display_name',
    )

    @api.depends('node_id', 'approver_id', 'state', 'record_type')
    def _compute_display_name(self):
        for record in self:
            node_name = record.node_id.name or ''
            approver = record.approver_id.name or ''
            type_label = '审批' if record.record_type == 'approver' else '办理'
            state_label = dict(self._fields['state'].selection).get(
                record.state, ''
            )
            record.display_name = f'[{type_label}] {node_name} - {approver} - {state_label}'