from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalNode(models.Model):
    _name = 'approval.node'
    _description = '审批节点'
    _order = 'sequence, id'
    _rec_name = 'display_name'

    flow_id = fields.Many2one(
        'approval.flow', string='审批流程', required=True,
        ondelete='cascade', index=True,
    )
    name = fields.Char(string='节点名称', required=True)
    display_name = fields.Char(
        string='显示名称', compute='_compute_display_name', store=True,
    )
    sequence = fields.Integer(string='排序', default=10)

    # ── 节点类型 ──
    node_type = fields.Selection([
        ('approver', '审批人'),
        ('cc', '抄送人'),
        ('condition', '条件分支'),
        ('handler', '办理人'),
    ], string='节点类型', default='approver', required=True,
    )

    # ── 图结构：父子关系替代线性顺序 ──
    parent_ids = fields.Many2many(
        'approval.node', 'approval_node_child_rel',
        'child_id', 'parent_id', string='前置节点',
        help='此节点之前需要完成的节点',
    )
    child_ids = fields.Many2many(
        'approval.node', 'approval_node_child_rel',
        'parent_id', 'child_id', string='后置节点',
        help='此节点完成后流转到的节点',
    )

    # ── 审批人配置（node_type = approver） ──
    sign_type = fields.Selection([
        ('countersign', '会签'),
        ('or_sign', '或签'),
    ], string='签署方式', default='or_sign',
       help='会签：所有审批人都必须通过\n或签：任一审批人通过即算通过',
    )

    approver_type = fields.Selection([
        ('specific_user', '指定用户'),
        ('specific_group', '指定用户组'),
        ('department_manager', '部门经理'),
        ('direct_manager', '直属上级'),
        ('requester', '发起人自选'),
        ('dynamic', '动态指定'),
    ], string='审批人类型', default='specific_user',
    )

    approver_ids = fields.Many2many(
        'res.users', 'approval_node_user_rel',
        'node_id', 'user_id', string='指定审批人',
    )
    approver_group_ids = fields.Many2many(
        'res.groups', 'approval_node_group_rel',
        'node_id', 'group_id', string='指定用户组',
    )
    approver_count = fields.Integer(
        string='审批人数', compute='_compute_approver_count',
    )

    # ── 办理人配置（node_type = handler） ──
    handler_type = fields.Selection([
        ('specific_user', '指定用户'),
        ('specific_group', '指定用户组'),
        ('direct_manager', '直属上级'),
        ('requester', '发起人自选'),
    ], string='办理人类型', default='specific_user',
    )
    handler_ids = fields.Many2many(
        'res.users', 'approval_node_handler_rel',
        'node_id', 'user_id', string='指定办理人',
    )
    handler_group_ids = fields.Many2many(
        'res.groups', 'approval_node_handler_group_rel',
        'node_id', 'group_id', string='办理用户组',
    )

    # ── 抄送人配置（node_type = cc） ──
    cc_type = fields.Selection([
        ('specific_user', '指定用户'),
        ('specific_group', '指定用户组'),
        ('direct_manager', '直属上级'),
        ('requester', '发起人自选'),
    ], string='抄送人类型', default='specific_user',
    )
    cc_ids = fields.Many2many(
        'res.users', 'approval_node_cc_rel',
        'node_id', 'user_id', string='指定抄送人',
    )
    cc_group_ids = fields.Many2many(
        'res.groups', 'approval_node_cc_group_rel',
        'node_id', 'group_id', string='抄送用户组',
    )

    # ── 条件分支配置（node_type = condition） ──
    condition_lines = fields.One2many(
        'approval.condition.line', 'node_id', string='条件规则',
    )
    default_child_id = fields.Many2one(
        'approval.node', string='默认分支',
        help='当所有条件都不匹配时，走此默认分支',
    )

    # ── 通用配置 ──
    required = fields.Boolean(string='必须处理', default=True)
    timeout_hours = fields.Integer(
        string='超时提醒（小时）', default=0,
        help='超过此时间未处理将发送提醒，0表示不提醒',
    )
    can_edit = fields.Boolean(
        string='允许编辑', default=False,
        help='此节点处理时允许修改业务单据',
    )
    active = fields.Boolean(string='启用', default=True)

    # ── 审批表单字段（自定义审批时需要填写的字段） ──
    form_field_ids = fields.One2many(
        'approval.form.field', 'node_id', string='审批表单字段',
        help='此节点审批人需要填写的额外字段',
    )

    @api.depends('name', 'node_type', 'sequence')
    def _compute_display_name(self):
        for node in self:
            type_label = dict(self._fields['node_type'].selection).get(
                node.node_type, ''
            )
            node.display_name = f'[{type_label}] {node.name}'

    @api.depends('approver_ids')
    def _compute_approver_count(self):
        for node in self:
            node.approver_count = len(node.approver_ids)

    # ── 审批人解析 ────────────────────────────────────────────

    def get_approvers(self, request=None):
        self.ensure_one()
        if self.node_type == 'approver':
            return self._resolve_approver_users(request)
        return self.env['res.users'].browse()

    def _resolve_approver_users(self, request=None):
        if self.approver_type == 'specific_user':
            return self.approver_ids
        elif self.approver_type == 'specific_group':
            return self.approver_group_ids.mapped('users')
        elif self.approver_type == 'direct_manager':
            if request and request.request_user_id.employee_id and request.request_user_id.employee_id.parent_id:
                return request.request_user_id.employee_id.parent_id.user_id
            return self.env['res.users'].browse()
        elif self.approver_type == 'department_manager':
            if request and request.request_user_id.employee_id and request.request_user_id.employee_id.department_id:
                dept = request.request_user_id.employee_id.department_id
                if dept.manager_id:
                    return dept.manager_id
            return self.env['res.users'].browse()
        elif self.approver_type == 'requester':
            if request:
                return request.request_user_id
            return self.env.user
        elif self.approver_type == 'dynamic':
            return self.env['res.users'].browse()
        return self.env['res.users'].browse()

    def get_handlers(self, request=None):
        self.ensure_one()
        if self.handler_type == 'specific_user':
            return self.handler_ids
        elif self.handler_type == 'specific_group':
            return self.handler_group_ids.mapped('users')
        elif self.handler_type == 'direct_manager':
            if request and request.request_user_id.parent_id:
                return request.request_user_id.parent_id
        elif self.handler_type == 'requester':
            if request:
                return request.request_user_id
        return self.env['res.users'].browse()

    def get_cc_users(self, request=None):
        self.ensure_one()
        if self.cc_type == 'specific_user':
            return self.cc_ids
        elif self.cc_type == 'specific_group':
            return self.cc_group_ids.mapped('users')
        elif self.cc_type == 'direct_manager':
            if request and request.request_user_id.parent_id:
                return request.request_user_id.parent_id
        elif self.cc_type == 'requester':
            if request:
                return request.request_user_id
        return self.env['res.users'].browse()

    # ── 条件求值（支持多路并行） ──────────────────────────────

    def evaluate_condition(self, request=None):
        self.ensure_one()
        if self.node_type != 'condition':
            return self.env['approval.node'].browse()

        for line in self.condition_lines.filtered('active').sorted('sequence'):
            if line.evaluate(request):
                return line.next_node_ids.filtered('active')

        if self.default_child_id and self.default_child_id.active:
            return self.default_child_id
        return self.env['approval.node'].browse()

    @api.constrains('parent_ids', 'child_ids')
    def _check_cycle(self):
        for node in self:
            if not isinstance(node.id, int) or node.id < 0:
                continue
            visited = set()
            stack = [node]
            while stack:
                current = stack.pop()
                if current.id in visited:
                    continue
                visited.add(current.id)
                for child in current.child_ids:
                    if not isinstance(child.id, int) or child.id < 0:
                        continue
                    if child == node:
                        raise ValidationError(_(
                            '检测到循环依赖：节点 "%s" 的路径中存在环回，'
                            '请检查流程连接。'
                        ) % node.name)
                    if child.id not in visited:
                        stack.append(child)
            for parent in node.parent_ids:
                if not isinstance(parent.id, int) or parent.id < 0:
                    continue
                p_visited = {node.id}
                p_stack = [parent]
                while p_stack:
                    current = p_stack.pop()
                    if current.id in p_visited:
                        continue
                    p_visited.add(current.id)
                    if current == node:
                        raise ValidationError(_(
                            '检测到循环依赖：节点 "%s" 被其下游节点的父节点引用，'
                            '请检查流程连接。'
                        ) % node.name)
                    for child in current.child_ids:
                        if not isinstance(child.id, int) or child.id < 0:
                            continue
                        if child.id not in p_visited:
                            p_stack.append(child)

    @api.constrains('node_type', 'condition_lines', 'default_child_id')
    def _check_condition_rules(self):
        for node in self:
            if node.node_type == 'condition':
                has_active_rules = bool(
                    node.condition_lines.filtered('active')
                )
                if not has_active_rules and not node.default_child_id:
                    raise ValidationError(_(
                        '条件分支节点 "%s" 必须配置至少一条启用的条件规则'
                        '或设置默认分支。'
                    ) % node.name)