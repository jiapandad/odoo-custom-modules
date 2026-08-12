from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalCategory(models.Model):
    _name = 'approval.category'
    _description = '审批类型'
    _order = 'sequence, id'

    name = fields.Char(string='审批类型名称', required=True)
    code = fields.Char(string='类型编码', required=True)
    model_name = fields.Char(
        string='关联模型',
        required=True,
        help='审批关联的业务模型技术名称，如 purchase.order',
    )
    description = fields.Text(string='描述')
    active = fields.Boolean(string='启用', default=True)
    sequence = fields.Integer(string='排序', default=10)
    flow_ids = fields.One2many(
        'approval.flow', 'category_id', string='审批流程',
    )
    request_ids = fields.One2many(
        'approval.request', 'category_id', string='审批请求',
    )
    request_count = fields.Integer(
        string='请求数量', compute='_compute_request_count',
    )

    @api.depends('request_ids')
    def _compute_request_count(self):
        for category in self:
            category.request_count = len(category.request_ids)

    _sql_constraints = [
        ('code_unique', 'unique(code)', '审批类型编码必须唯一！'),
    ]

    def action_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '审批请求',
            'res_model': 'approval.request',
            'view_mode': 'list,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }

    @api.constrains('model_name')
    def _check_model_name(self):
        for category in self:
            if category.model_name not in self.env:
                raise ValidationError(_(
                    '模型 "%s" 不存在，请输入有效的模型技术名称。'
                ) % category.model_name)