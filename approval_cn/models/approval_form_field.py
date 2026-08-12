from odoo import api, fields, models


class ApprovalFormField(models.Model):
    _name = 'approval.form.field'
    _description = '审批表单字段'
    _order = 'sequence, id'

    node_id = fields.Many2one(
        'approval.node', string='审批节点', required=True,
        ondelete='cascade',
    )
    name = fields.Char(string='字段标签', required=True)
    sequence = fields.Integer(string='排序', default=10)
    field_type = fields.Selection([
        ('char', '文本'),
        ('text', '多行文本'),
        ('integer', '整数'),
        ('float', '小数'),
        ('boolean', '是/否'),
        ('date', '日期'),
        ('selection', '下拉选择'),
    ], string='字段类型', required=True, default='char',
    )
    required = fields.Boolean(string='必填', default=False)
    selection_options = fields.Text(
        string='选项（每行一个）',
        help='当字段类型为"下拉选择"时，每行一个选项',
    )
    default_value = fields.Char(string='默认值')
    placeholder = fields.Char(string='占位提示')
    active = fields.Boolean(string='启用', default=True)