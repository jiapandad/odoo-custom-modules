from odoo import api, fields, models


class FormInstanceField(models.Model):
    _name = 'hc.form.instance.field'
    _description = '表单实例字段值'
    _order = 'sequence, id'

    instance_id = fields.Many2one('hc.form.instance', '表单实例', required=True, ondelete='cascade')
    template_field_id = fields.Many2one('hc.form.template.field', '模板字段', ondelete='set null')
    sequence = fields.Integer('排序', default=10)
    field_key = fields.Char('字段键', required=True)
    field_name = fields.Char('字段名', required=True)
    field_type = fields.Selection([
        ('char', '单行文本'), ('text', '多行文本'), ('integer', '整数'), ('float', '小数/金额'),
        ('date', '日期'), ('datetime', '日期时间'), ('boolean', '是/否'), ('selection', '下拉单选'),
        ('many2one', '关联记录'), ('image', '图片上传'), ('binary', '附件上传'),
        ('html', '富文本'), ('user', '用户选择'), ('company', '公司选择'), ('department', '部门选择'),
    ], '字段类型', required=True)
    required = fields.Boolean('必填', default=False)
    value_char = fields.Char('值')
    value_text = fields.Text('多行值')
    value_date = fields.Date('日期值')
    value_integer = fields.Integer('整数值')
    value_float = fields.Float('数值')
    value_selection = fields.Selection(selection='_get_selection_options', string='值(下拉)')
    # 不同类型的 Many2one 字段（按 field_type 选用）
    value_user_id = fields.Many2one('res.users', '用户值')
    value_company_id = fields.Many2one('res.company', '公司值')
    value_department_id = fields.Many2one('hr.department', '部门值')
    # 附件：使用 Odoo 原生 ir.attachment（多对多支持多个文件）
    value_attachment_ids = fields.Many2many(
        'ir.attachment', 'hc_form_instance_field_attachment_rel',
        'field_id', 'attachment_id',
        string='附件',
        help='使用 Odoo 原生附件功能',
    )
    # 填写说明（来自模板的 field_hint）
    value_hint = fields.Text('填写说明', compute='_compute_value_hint')
    available_options = fields.Char('可选值', compute='_compute_value_hint')
    attachment_count = fields.Integer('附件数', compute='_compute_attachment_count')

    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.value_attachment_ids)

    @api.depends('template_field_id', 'field_type')
    def _compute_value_hint(self):
        for rec in self:
            tf = rec.template_field_id
            hint_parts = []
            if tf and tf.field_hint:
                hint_parts.append(tf.field_hint)
            # 单行/多行类型显示占位提示
            if rec.field_type == 'char' and tf and tf.placeholder and not hint_parts:
                hint_parts.append(f'提示：{tf.placeholder}')
            rec.value_hint = '\n'.join(hint_parts) if hint_parts else ''
            # 可选值（对所有类型都有用）
            if tf and tf.selection_options:
                rec.available_options = tf.selection_options.replace('\n', ' / ')
            elif rec.field_type in ('user', 'company', 'department'):
                rec.available_options = ''
            else:
                rec.available_options = ''

    def _get_selection_options(self):
        """返回当前记录模板字段的 selection_options 拆分的列表"""
        if not self:
            return []
        result = []
        for rec in self:
            opts = rec.template_field_id.selection_options or ''
            for opt in opts.split('\n'):
                opt = opt.strip()
                if opt and (opt, opt) not in result:
                    result.append((opt, opt))
        return result

    def _get_display_value(self):
        self.ensure_one()
        if self.field_type in ('binary', 'attachment', 'image'):
            count = len(self.value_attachment_ids)
            return f'{count} 个附件' if count else ''
        # 数字类型：优先 char（用户输入位置）再回退到类型字段
        if self.field_type == 'integer':
            return self.value_char if self.value_char else (str(self.value_integer) if self.value_integer else '')
        if self.field_type == 'float':
            return self.value_char if self.value_char else (str(self.value_float) if self.value_float else '')
        if self.field_type == 'date':
            return self.value_char if self.value_char else (str(self.value_date) if self.value_date else '')
        if self.field_type == 'datetime':
            return self.value_char
        mapping = {
            'char': self.value_char,
            'text': self.value_text or self.value_char,
            'boolean': self.value_char,
            'selection': self.value_selection or self.value_char,
            'user': self.value_user_id.display_name if self.value_user_id else (self.value_char or ''),
            'company': self.value_company_id.display_name if self.value_company_id else (self.value_char or ''),
            'department': self.value_department_id.display_name if self.value_department_id else (self.value_char or ''),
            'many2one': self.value_char,
            'html': self.value_text or self.value_char,
        }
        return mapping.get(self.field_type, self.value_char) or ''

    def _set_display_value(self, val):
        self.ensure_one()
        if self.field_type == 'user':
            if val and str(val).isdigit():
                self.value_user_id = int(val)
            self.value_char = str(val) if val else None
        elif self.field_type == 'company':
            if val and str(val).isdigit():
                self.value_company_id = int(val)
            self.value_char = str(val) if val else None
        elif self.field_type == 'department':
            if val and str(val).isdigit():
                self.value_department_id = int(val)
            self.value_char = str(val) if val else None
        elif self.field_type == 'selection':
            self.value_selection = val or False
            self.value_char = val or ''
        elif self.field_type in ('text', 'html'):
            self.value_text = val
        elif self.field_type == 'integer':
            self.value_integer = int(val) if val else None
        elif self.field_type == 'float':
            self.value_float = float(val) if val else None
        elif self.field_type == 'date':
            self.value_date = val
        else:
            self.value_char = val or None
