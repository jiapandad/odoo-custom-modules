from odoo import api, fields, models


class FormTemplate(models.Model):
    _name = 'hc.form.template'
    _description = '动态表单模板'

    name = fields.Char('模板名称', required=True)
    code = fields.Char('编码', required=True)
    description = fields.Html('表单说明')
    category_id = fields.Many2one(
        'approval.category', '审批类型',
        help='选择该表单走哪个审批类型。保存模板时如未指定，系统会自动创建一个。',
    )
    approval_category_code = fields.Char(
        related='category_id.code', store=True,
    )
    active = fields.Boolean('启用', default=True)
    field_ids = fields.One2many(
        'hc.form.template.field', 'template_id', '字段列表',
    )
    instance_count = fields.Integer(
        '实例数', compute='_compute_instance_count',
    )

    @api.depends('field_ids')
    def _compute_instance_count(self):
        for tpl in self:
            tpl.instance_count = self.env['hc.form.instance'].search_count([
                ('template_id', '=', tpl.id),
            ])

    def action_view_instances(self):
        """查看该模板的所有实例"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '表单实例',
            'res_model': 'hc.form.instance',
            'view_mode': 'list,form',
            'domain': [('template_id', '=', self.id)],
        }

    @api.model
    def create(self, vals_list):
        """创建时若没有审批类型，自动新建一个（用模板 name 作 code）"""
        for vals in vals_list:
            if not vals.get('category_id') and vals.get('name'):
                vals['category_id'] = self._auto_create_category(
                    name=vals['name'],
                    code=vals.get('code', ''),
                ).id
        return super().create(vals_list)

    def _auto_create_category(self, name, code=''):
        """根据模板自动创建审批类型 + 流程 + 节点"""
        Category = self.env['approval.category']
        Flow = self.env['approval.flow']
        Node = self.env['approval.node']

        # 自动生成 code（如果 code 为空或重复）
        if not code:
            import re
            code = re.sub(r'[^a-z0-9_]', '_', name.lower()) or 'auto_type'
        # 防止重复
        existing = Category.search([('code', '=', code)], limit=1)
        if existing:
            return existing
        # 创建
        category = Category.create({
            'name': name,
            'code': code,
            'model_name': 'hc.form.instance',
            'description': '由动态表单模板自动创建',
        })
        flow = Flow.create({
            'name': f'{name}默认流程',
            'category_id': category.id,
            'is_default': True,
            'active': True,
        })
        # 默认 2 个节点（第一个用户、第二个审批管理员）
        users = self.env['res.users'].search([], limit=2)
        for i, approver in enumerate(users, 1):
            Node.create({
                'flow_id': flow.id,
                'name': f'第{i}级审批',
                'sequence': i * 10,
                'node_type': 'approver',
                'approver_ids': [(6, 0, [approver.id])],
            })
        return category

    def action_new_instance(self):
        """基于此模板创建新表单实例"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '新建 %s' % self.name,
            'res_model': 'hc.form.instance',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_template_id': self.id,
                'form_view_ref': 'hc_dynamic_form.view_form_instance_form',
            },
        }

    def action_quick_new(self):
        """快速发起：取第一个启用的模板直接进入新建表单"""
        self.ensure_one()
        target = self.search([('active', '=', True)], limit=1)
        if not target:
            raise UserError(_('没有启用的模板。'))
        return target.action_new_instance()

    def action_quick_setup(self):
        """一键配置审批：从当前模板的 name/code 自动打开向导，预填了内容"""
        self.ensure_one()
        # 准备中文→英文编码映射
        code = self.code or ''
        if not code and self.name:
            import re
            pinyin_map = {
                '用': 'yong', '车': 'che', '申': 'shen', '请': 'qing',
                '付': 'fu', '款': 'kuan', '报': 'bao', '销': 'xiao',
            }
            code = ''.join(pinyin_map.get(c, c.lower()) for c in self.name if c in pinyin_map) or 'default_code'
        return {
            'type': 'ir.actions.act_window',
            'name': '一键配置审批',
            'res_model': 'hc.approval.setup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_name': self.name,
                'default_code': code,
                'default_description': '由动态表单模板自动创建',
            },
        }
