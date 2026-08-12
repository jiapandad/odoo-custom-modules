from odoo import api, fields, models

# 字段类型 → 默认字段键
FIELD_TYPE_DEFAULT_KEY = {
    'user': 'applicant',
    'company': 'company',
    'department': 'department',
    'char': 'field_char',
    'text': 'field_text',
    'integer': 'field_int',
    'float': 'field_amount',
    'date': 'field_date',
    'datetime': 'field_datetime',
    'boolean': 'field_bool',
    'selection': 'field_select',
    'many2one': 'field_related',
    'image': 'field_image',
    'binary': 'field_attachment',
    'html': 'field_html',
}


class FormTemplateField(models.Model):
    _name = 'hc.form.template.field'
    _description = '表单字段定义'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'hc.form.template', '模板', required=True, ondelete='cascade',
    )
    name = fields.Char('字段标签', required=True)
    field_key = fields.Char('字段键', required=True, help='自动从标签生成，可手动调整')
    sequence = fields.Integer('排序', default=10)
    field_type = fields.Selection([
        ('char', '单行文本'),
        ('text', '多行文本'),
        ('integer', '整数'),
        ('float', '小数/金额'),
        ('date', '日期'),
        ('datetime', '日期时间'),
        ('boolean', '是/否'),
        ('many2one', '关联记录'),
        ('image', '图片上传'),
        ('binary', '附件上传'),
        ('html', '富文本'),
        ('user', '用户选择'),
        ('company', '公司选择'),
        ('department', '部门选择'),
    ], '字段类型', required=True, default='char')

    required = fields.Boolean('必填', default=False)
    selection_options = fields.Text('选项（每行一个）')
    default_value = fields.Char('默认值')
    placeholder = fields.Char('占位提示')
    help_text = fields.Char('帮助文本')
    field_hint = fields.Text('填写说明',
        help='详细说明：填写要求、示例、可选值、注意事项等')
    related_model = fields.Char('关联模型',
        help='many2one 类型时填写，如 res.partner')
    width = fields.Selection([
        ('12', '整行'),
        ('6', '半行'),
        ('4', '1/3 行'),
    ], '宽度', default='12')
    is_system = fields.Boolean('系统字段', readonly=True,
        help='用户/公司/部门等共享字段，标记后会自动处理')

    @api.onchange('name')
    def _onchange_name(self):
        """标签变化时自动生成字段键（如果用户没手动改过）"""
        if self.name and not self.field_key:
            self.field_key = self._auto_key(self.name)

    @api.onchange('field_type')
    def _onchange_field_type(self):
        if self.field_type not in ('selection',):
            self.selection_options = False
        # 系统字段标记
        self.is_system = self.field_type in ('user', 'company', 'department')

    def _auto_key(self, label):
        """把中文标签转拼音式 key；已存在则加后缀"""
        import re
        # 简单规则：中文→拼音首字母
        first_pinyin = {
            '公': 'gong', '司': 'si', '用': 'yong', '户': 'hu', '部': 'bu', '门': 'men',
            '申': 'shen', '请': 'qing', '付': 'fu', '款': 'kuan', '报': 'bao', '销': 'xiao',
            '时': 'shi', '间': 'jian', '日': 'ri', '期': 'qi', '金': 'jin', '额': 'e',
            '数': 'shu', '量': 'liang', '单': 'dan', '价': 'jia', '名': 'ming', '称': 'cheng',
            '备': 'bei', '注': 'zhu', '说': 'shuo', '明': 'ming', '类': 'lei', '型': 'xing',
            '状': 'zhuang', '态': 'tai', '审': 'shen', '批': 'pi', '人': 'ren', '附': 'fu',
            '件': 'jian', '项': 'xiang', '目': 'mu', '图': 'tu', '片': 'pian',
        }
        key = ''.join(first_pinyin.get(c, c.lower() if c.isascii() else '') for c in label)
        key = re.sub(r'[^a-z0-9_]', '', key) or 'field'
        # 同一模板内去重
        if self.template_id:
            existing = self.template_id.field_ids.filtered(
                lambda f: f.field_key == key and f.id != self.id
            )
            if existing:
                i = 2
                while self.template_id.field_ids.filtered(
                    lambda f: f.field_key == f'{key}_{i}' and f.id != self.id
                ):
                    i += 1
                key = f'{key}_{i}'
        return key

    @api.model_create_multi
    def create(self, vals_list):
        # 创建时若 field_key 为空，自动生成
        for vals in vals_list:
            if not vals.get('field_key') and vals.get('name'):
                tmp = self.new(vals)
                vals['field_key'] = tmp._auto_key(vals['name'])
        return super().create(vals_list)
