from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval

import logging

_logger = logging.getLogger(__name__)


class ApprovalConditionLine(models.Model):
    _name = 'approval.condition.line'
    _description = '条件分支规则'
    _order = 'sequence, id'

    node_id = fields.Many2one(
        'approval.node', string='条件节点', required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='规则名称', required=True)
    sequence = fields.Integer(string='优先级', default=10)

    next_node_ids = fields.Many2many(
        'approval.node', 'approval_condition_next_node_rel',
        'condition_id', 'node_id', string='目标节点',
        domain="[('flow_id', '=', parent.flow_id), ('id', '!=', parent.id)]",
        help='条件满足时流转到此节点（支持多个实现并行）',
    )

    condition_type = fields.Selection([
        ('amount_range', '金额范围'),
        ('amount_above', '金额大于'),
        ('amount_below', '金额小于'),
        ('department', '申请部门'),
        ('expression', '自定义表达式'),
        ('always', '无条件'),
    ], string='条件类型', required=True, default='always',
    )

    condition_amount_min = fields.Monetary(
        string='金额下限', currency_field='currency_id',
    )
    condition_amount_max = fields.Monetary(
        string='金额上限', currency_field='currency_id',
    )
    condition_amount = fields.Monetary(
        string='金额阈值', currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency', string='币种',
        related='node_id.flow_id.currency_id',
    )

    condition_department_id = fields.Many2one(
        'hr.department', string='申请部门',
        help='申请人的部门等于此部门时匹配',
    )

    condition_expression = fields.Char(
        string='自定义表达式',
        help='Python 表达式，可使用变量：amount, department_id, user_id',
    )

    active = fields.Boolean(string='启用', default=True)

    def evaluate(self, request=None):
        self.ensure_one()
        if self.condition_type == 'always':
            return True
        elif self.condition_type == 'amount_range':
            amount = request.amount if request else 0
            min_ok = not self.condition_amount_min or amount >= self.condition_amount_min
            max_ok = not self.condition_amount_max or amount <= self.condition_amount_max
            return min_ok and max_ok
        elif self.condition_type == 'amount_above':
            amount = request.amount if request else 0
            return amount > self.condition_amount
        elif self.condition_type == 'amount_below':
            amount = request.amount if request else 0
            return amount < self.condition_amount
        elif self.condition_type == 'department':
            if request and request.request_user_id.department_id:
                return request.request_user_id.department_id == self.condition_department_id
            return False
        elif self.condition_type == 'expression':
            if not self.condition_expression:
                return False
            try:
                eval_context = {
                    'amount': request.amount if request else 0,
                    'department_id': request.request_user_id.department_id.id if request and request.request_user_id.department_id else False,
                    'user_id': request.request_user_id.id if request else self.env.user.id,
                }
                return safe_eval(self.condition_expression, eval_context)
            except Exception:
                _logger.exception('条件表达式求值失败: %s', self.condition_expression)
                return False
        return False