from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalFlow(models.Model):
    _name = 'approval.flow'
    _description = '审批流程'
    _order = 'sequence, id'

    name = fields.Char(string='流程名称', required=True)
    category_id = fields.Many2one(
        'approval.category', string='审批类型', required=True,
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='排序', default=10)
    is_default = fields.Boolean(
        string='默认流程',
        help='该审批类型下的默认流程',
    )
    description = fields.Text(string='流程说明')
    active = fields.Boolean(string='启用', default=True)

    node_ids = fields.One2many(
        'approval.node', 'flow_id', string='审批节点',
    )
    request_ids = fields.One2many(
        'approval.request', 'flow_id', string='审批请求',
    )

    condition_type = fields.Selection([
        ('always', '无条件'),
        ('amount', '按金额'),
    ], string='触发条件类型', default='always',
       help='定义此流程在什么条件下被触发使用',
    )
    condition_amount_min = fields.Monetary(
        string='金额下限', currency_field='currency_id',
        help='金额大于等于此值时触发此流程',
    )
    condition_amount_max = fields.Monetary(
        string='金额上限', currency_field='currency_id',
        help='金额小于此值时触发此流程',
    )
    currency_id = fields.Many2one(
        'res.currency', string='币种',
        default=lambda self: self.env.company.currency_id,
    )

    node_count = fields.Integer(
        string='节点数', compute='_compute_node_count',
    )

    @api.depends('node_ids')
    def _compute_node_count(self):
        for flow in self:
            flow.node_count = len(flow.node_ids)

    @api.model
    def _get_flow_for_category(self, category_code, amount=0.0):
        category = self.env['approval.category'].search([
            ('code', '=', category_code),
        ], limit=1)
        if not category:
            return self.browse()

        flows = self.search([
            ('category_id', '=', category.id),
            ('active', '=', True),
        ], order='sequence')

        for flow in flows:
            if flow.condition_type == 'always':
                return flow
            elif flow.condition_type == 'amount':
                min_ok = not flow.condition_amount_min or amount >= flow.condition_amount_min
                max_ok = not flow.condition_amount_max or amount < flow.condition_amount_max
                if min_ok and max_ok:
                    return flow

        return flows[0] if flows else self.browse()

    @api.constrains('is_default', 'category_id')
    def _check_unique_default(self):
        for flow in self:
            if flow.is_default:
                existing = self.search([
                    ('category_id', '=', flow.category_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', flow.id),
                ])
                if existing:
                    raise ValidationError(_(
                        '审批类型 "%s" 下已存在默认流程 "%s"，'
                        '每个审批类型只能有一个默认流程。'
                    ) % (flow.category_id.name, existing[0].name))