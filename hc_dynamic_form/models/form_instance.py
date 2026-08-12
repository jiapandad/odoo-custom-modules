from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FormInstance(models.Model):
    _name = 'hc.form.instance'
    _inherit = ['approval.mixin', 'mail.thread']
    _description = '动态表单实例'
    _order = 'create_date desc'

    name = fields.Char('标题', compute='_compute_name', store=True)
    template_id = fields.Many2one('hc.form.template', '表单模板', required=True, readonly=True)
    applicant_id = fields.Many2one('res.users', '申请人', default=lambda self: self.env.user, readonly=True)
    apply_date = fields.Datetime('申请时间', default=fields.Datetime.now, readonly=True)
    state = fields.Selection(
        [('draft', '草稿'), ('done', '已提交'), ('cancelled', '已取消')],
        '表单状态', default='draft', tracking=True,
    )
    form_data = fields.Json('表单数据', default={})
    dynamic_form_html = fields.Html('预览', compute='_compute_dynamic_form_html', sanitize=False)
    approval_category_code = fields.Char(related='template_id.approval_category_code', store=True)
    field_value_ids = fields.One2many('hc.form.instance.field', 'instance_id', '字段值')

    @api.depends('template_id.name', 'applicant_id.name')
    def _compute_name(self):
        for inst in self:
            tpl = inst.template_id.name or '未命名模板'
            user = inst.applicant_id.name or '未知用户'
            inst.name = '[%s] %s' % (tpl, user)

    @api.depends('template_id', 'form_data')
    def _compute_dynamic_form_html(self):
        for inst in self:
            tpl = inst.template_id
            if not tpl or not tpl.field_ids:
                inst.dynamic_form_html = ''
                continue
            data = inst.form_data or {}
            if not isinstance(data, dict) or not data:
                inst.dynamic_form_html = ''
                continue
            rows = ['<div style="width:100%;padding:8px 0;box-sizing:border-box">']
            rows.append(
                '<div style="font-size:16px;font-weight:bold;color:#444;'
                'padding:12px 0 8px;border-bottom:2px solid #714b67;margin-bottom:12px">'
                f'{tpl.name}</div>'
            )
            rows.append(
                '<table style="width:100%;border-collapse:collapse;font-size:14px;table-layout:fixed">'
            )
            for fd in tpl.field_ids.sorted('sequence'):
                val = data.get(fd.field_key)
                display = self._format_value(fd, val)
                rows.append(
                    f'<tr><td style="padding:8px 12px;width:120px;color:#666;background:#f9fafb;'
                    f'border-bottom:1px solid #eee">{fd.name}'
                    f'{chr(39) if not fd.required else ""}'
                    f'</td>'
                    f'<td style="padding:8px 12px;color:#333;border-bottom:1px solid #eee">{display}</td></tr>'
                )
            rows.append('</table></div>')
            inst.dynamic_form_html = ''.join(rows)

    def _get_approval_name(self): return self.name

    def _get_approval_amount(self):
        total = 0.0
        for fv in self.field_value_ids:
            if fv.field_type == 'float' and fv.value_float:
                total += fv.value_float
        return total

    def _check_required_fields(self):
        missing = []
        for fv in self.field_value_ids.filtered('required'):
            v = fv._get_display_value()
            if not v or (isinstance(v, str) and not v.strip()):
                missing.append(fv.field_name or fv.field_key)
        return missing

    def _format_value(self, fd, value):
        if value is None or value == '':
            return '<span class="text-muted">—</span>'
        import re
        ftype = fd.field_type
        if ftype == 'boolean': return '是' if value else '否'
        if ftype == 'user':
            try:
                u = self.env['res.users'].browse(int(value)).sudo()
                return u.display_name if u.exists() else str(value)
            except: return str(value)
        if ftype == 'company':
            try:
                c = self.env['res.company'].browse(int(value)).sudo()
                return c.name if c.exists() else str(value)
            except: return str(value)
        if ftype == 'department':
            try:
                d = self.env['hr.department'].browse(int(value)).sudo()
                return d.name if d.exists() else str(value)
            except: return str(value)
        return re.sub(r'<[^>]+>', '', str(value))

    # ═══ 字段值自动创建 ═══
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._auto_create_field_values()
        return records

    def write(self, vals):
        result = super().write(vals)
        if 'template_id' in vals:
            for rec in self:
                rec.field_value_ids.unlink()
                rec._auto_create_field_values()
        return result

    def _auto_create_field_values(self):
        if not self.template_id or not self.template_id.field_ids:
            return
        existing = {fv.field_key: fv for fv in self.field_value_ids}
        data = self.form_data or {} if isinstance(self.form_data, dict) else {}
        for fd in self.template_id.field_ids.sorted('sequence'):
            if fd.field_key in existing:
                continue
            # 优先用 form_data 中的值；否则用模板的 default_value；最后为空
            if isinstance(data, dict) and data.get(fd.field_key):
                val = data.get(fd.field_key)
            else:
                val = fd.default_value or None
            fv = {
                'instance_id': self.id,
                'template_field_id': fd.id,
                'field_key': fd.field_key,
                'field_name': fd.name,
                'field_type': fd.field_type,
                'required': fd.required,
                'sequence': fd.sequence,
            }
            if fd.field_type in ('text', 'html'):
                fv['value_text'] = str(val) if val else ''
            elif fd.field_type == 'integer':
                fv['value_integer'] = int(val) if val else None
            elif fd.field_type == 'float':
                fv['value_float'] = float(val) if val else None
            elif fd.field_type == 'date':
                fv['value_date'] = val
            elif fd.field_type == 'selection':
                fv['value_selection'] = val or False
                fv['value_char'] = str(val) if val else ''
            elif fd.field_type == 'user':
                fv['value_user_id'] = int(val) if val and str(val).isdigit() else None
                fv['value_char'] = str(val) if val else ''
            elif fd.field_type == 'company':
                fv['value_company_id'] = int(val) if val and str(val).isdigit() else None
                fv['value_char'] = str(val) if val else ''
            elif fd.field_type == 'department':
                fv['value_department_id'] = int(val) if val and str(val).isdigit() else None
                fv['value_char'] = str(val) if val else ''
            else:
                fv['value_char'] = str(val) if val else ''
            self.env['hc.form.instance.field'].create(fv)

    def _sync_field_values_to_form_data(self):
        """把 field_value_ids 同步到 form_data（保存显示名称而非 ID）"""
        data = {}
        for fv in self.field_value_ids:
            v = fv._get_display_value()
            data[fv.field_key] = v
        self.form_data = data

    def _format_form_data_as_text(self):
        """格式化为审批单的 description（纯文本，可靠显示）"""
        tpl = self.template_id
        data = self.form_data or {}
        if not tpl or not tpl.field_ids:
            return '（无数据）'
        lines = [f'{tpl.name}']
        for fd in tpl.field_ids.sorted('sequence'):
            v = data.get(fd.field_key, '')
            if v is None:
                v = ''
            import re
            display = re.sub(r'<[^>]+>', '', str(v)) if v else '—'
            lines.append(f'{fd.name}：{display}')
        return '\n'.join(lines)

    # ═══ 按钮 ═══
    def action_fill_defaults(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态可以填充默认值。'))
        for fv in self.field_value_ids:
            if fv.field_type == 'user' and fv.template_field_id:
                fv.value_user_id = self.env.user
                fv.value_char = str(self.env.user.id)
            elif fv.field_type == 'company' and fv.template_field_id:
                fv.value_company_id = self.env.company
                fv.value_char = str(self.env.company.id)
            elif fv.field_type == 'department' and fv.template_field_id:
                fv.value_department_id = self.env.user.employee_id.department_id
                fv.value_char = str(self.env.user.employee_id.department_id.id) if self.env.user.employee_id.department_id else ''
            elif fv.template_field_id and fv.template_field_id.default_value:
                v = fv.template_field_id.default_value
                if fv.field_type == 'text':
                    fv.value_text = v
                elif fv.field_type == 'integer':
                    fv.value_integer = int(v) if v else None
                elif fv.field_type == 'float':
                    fv.value_float = float(v) if v else None
                elif fv.field_type == 'date':
                    fv.value_date = v
                else:
                    fv.value_char = v
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_submit_form(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的表单才能提交。'))
        self._sync_field_values_to_form_data()
        missing = self._check_required_fields()
        if missing:
            raise UserError(_('请填写以下必填字段：\n%s') % '\n'.join('· ' + m for m in missing))
        # 预生成表单摘要，作为审批 description（让邮件通知能带上）
        summary = self._format_form_data_as_text()
        self = self.with_context(_approval_description=summary)
        self.state = 'done'
        self.action_submit_approval()
        self.message_post(body=_('表单已提交，等待审批。'))

    def action_submit_approval(self):
        """重写：创建审批请求时带上 description（让 _notify_users 能取到）"""
        self.ensure_one()
        if self.approval_state not in ('none', 'pending', 'rejected', 'cancelled'):
            raise UserError(_('当前状态不允许提交审批。'))

        category = self.env['approval.category'].search([
            ('code', '=', self.approval_category_code),
        ], limit=1)
        if not category:
            raise UserError(_(
                '未找到审批类型编码 "%s" 对应的审批类型，请联系管理员配置。'
            ) % self.approval_category_code)

        amount = self._get_approval_amount()
        flow = self.env['approval.flow']._get_flow_for_category(
            self.approval_category_code, amount,
        )
        if not flow:
            raise UserError(_(
                '未找到审批类型 "%s" 对应的审批流程，请联系管理员配置。'
            ) % category.name)

        description = self.env.context.get('_approval_description') or self._format_form_data_as_text()
        request = self.env['approval.request'].sudo().create({
            'name': self._get_approval_name(),
            'category_id': category.id,
            'flow_id': flow.id,
            'model_name': self._name,
            'res_id': self.id,
            'res_name': self.display_name,
            'amount': amount,
            'request_user_id': self.env.user.id,
            'description': description,
        })

        self.approval_request_id = request.id
        request.action_submit()
        return request

    def action_cancel_form(self):
        self.ensure_one(); self.state = 'cancelled'
        if self.approval_request_id:
            self.approval_request_id = False; self.approval_state = 'none'

    def action_draft_form(self):
        self.ensure_one(); self.state = 'draft'
        self.approval_state = 'none'; self.approval_request_id = False

    def _on_approval_submitted(self):
        super()._on_approval_submitted()
        if self.approval_request_id:
            self.approval_request_id.sudo().write({'description': self._format_form_data_as_text()})

    def _on_approval_approved(self): self.message_post(body=_('审批已通过。'))
    def _on_approval_rejected(self): self.message_post(body=_('审批已驳回。'))
