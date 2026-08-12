from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class ApprovalRequest(models.Model):
    _name = 'approval.request'
    _description = '审批请求'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ── 基础信息 ──
    name = fields.Char(string='请求标题', required=True)
    display_name = fields.Char(
        string='显示名称', compute='_compute_display_name', store=True,
    )
    category_id = fields.Many2one(
        'approval.category', string='审批类型', required=True,
        ondelete='restrict', index=True,
    )
    flow_id = fields.Many2one(
        'approval.flow', string='审批流程', required=True,
        ondelete='restrict', index=True,
    )

    # ── 关联业务单据 ──
    model_name = fields.Char(string='业务模型')
    res_id = fields.Integer(string='业务记录ID', default=0)
    res_name = fields.Char(string='业务单据名称')
    res_reference = fields.Char(
        string='业务单据', compute='_compute_res_reference',
    )

    # ── 金额 ──
    amount = fields.Monetary(string='金额', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='币种',
        default=lambda self: self.env.company.currency_id,
    )

    # ── 状态管理 ──
    state = fields.Selection([
        ('draft', '草稿'),
        ('submitted', '审批中'),
        ('approved', '审批通过'),
        ('rejected', '审批驳回'),
        ('cancelled', '已撤回'),
    ], string='状态', default='draft', tracking=True, index=True,
    )

    # ── 申请人 ──
    request_user_id = fields.Many2one(
        'res.users', string='申请人',
        default=lambda self: self.env.user, required=True, index=True,
    )
    request_date = fields.Datetime(
        string='申请时间', default=fields.Datetime.now,
    )
    approved_date = fields.Datetime(string='审批完成时间')

    # ── 审批进度（多节点并行） ──
    current_node_ids = fields.Many2many(
        'approval.node', 'approval_request_current_node_rel',
        'request_id', 'node_id', string='当前审批节点',
    )
    completed_node_ids = fields.Many2many(
        'approval.node', 'approval_request_completed_node_rel',
        'request_id', 'node_id', string='已完成节点',
    )

    # ── 审批记录 ──
    record_ids = fields.One2many(
        'approval.record', 'request_id', string='审批记录',
    )
    record_count = fields.Integer(
        string='审批次数', compute='_compute_record_count',
    )

    # ── 抄送记录 ──
    cc_ids = fields.One2many(
        'approval.cc', 'request_id', string='抄送记录',
    )
    cc_count = fields.Integer(
        string='抄送人数', compute='_compute_cc_count',
    )

    # ── 附件 ──
    attachment_ids = fields.One2many(
        'ir.attachment', 'res_id',
        domain=[('res_model', '=', 'approval.request')],
        string='附件',
    )
    attachment_count = fields.Integer(
        string='附件数', compute='_compute_attachment_count',
    )

    # ── 申请说明 ──
    description = fields.Text(string='申请说明')

    @api.depends('name', 'category_id')
    def _compute_display_name(self):
        for req in self:
            cat_name = req.category_id.name or ''
            req.display_name = f'[{cat_name}] {req.name}'

    @api.depends('model_name', 'res_id')
    def _compute_res_reference(self):
        for req in self:
            if req.model_name and req.res_id:
                req.res_reference = f'{req.model_name},{req.res_id}'

    @api.depends('record_ids')
    def _compute_record_count(self):
        for req in self:
            req.record_count = len(req.record_ids)

    @api.depends('cc_ids')
    def _compute_cc_count(self):
        for req in self:
            req.cc_count = len(req.cc_ids)

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for req in self:
            req.attachment_count = len(req.attachment_ids)

    # ══════════════════════════════════════════════════════════════
    # 审批流程引擎（图结构）
    # ══════════════════════════════════════════════════════════════

    def action_submit(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('只有草稿状态的审批请求才能提交。'))

        start_nodes = self._get_start_nodes()
        if not start_nodes:
            raise UserError(_('审批流程 "%s" 没有配置起始节点。') % self.flow_id.name)

        self.write({
            'state': 'submitted',
            'current_node_ids': [(6, 0, start_nodes.ids)],
            'request_date': fields.Datetime.now(),
        })

        for node in start_nodes:
            self._activate_node(node)

        self.message_post(body=_('审批请求已提交，进入审批流程。'))
        self._sync_business_model('submitted')

    def action_approve(self, comment=''):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能审批。'))

        approver = self.env.user
        active_record = self._get_user_active_record(approver)[:1]

        if not active_record:
            raise UserError(_('您没有待审批的节点。'))

        active_record.write({
            'state': 'approved',
            'comment': comment or _('同意'),
            'approved_date': fields.Datetime.now(),
        })

        node = active_record.node_id
        self.message_post(
            body=_('%s 审批通过【%s】节点。') % (approver.name, node.name)
        )

        if self._check_node_approved(node):
            self._complete_node(node)

    def action_reject(self, reason=''):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能驳回。'))

        approver = self.env.user
        active_record = self._get_user_active_record(approver)[:1]

        if not active_record:
            raise UserError(_('您没有待审批的节点。'))

        reject_msg = reason or _('驳回')
        active_record.write({
            'state': 'rejected',
            'comment': reject_msg,
            'approved_date': fields.Datetime.now(),
        })

        node = active_record.node_id
        self._cancel_node_pending_records(node)
        self._reject_all_pending()

        self.write({
            'state': 'rejected',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })

        self.message_post(
            body=_('%s 驳回了审批【%s】：%s') % (approver.name, node.name, reject_msg)
        )

    def action_cancel(self):
        self.ensure_one()
        if self.state not in ('draft', 'submitted'):
            raise UserError(_('只有草稿或审批中的请求才能撤回。'))

        self.record_ids.filtered(lambda r: r.state == 'pending').write({
            'state': 'cancelled',
        })
        self.write({
            'state': 'cancelled',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('审批请求已撤回。'))
        self._sync_business_model('cancelled')

    def action_resubmit(self):
        self.ensure_one()
        if self.state != 'rejected':
            raise UserError(_('只有被驳回的请求才能重新提交。'))

        self.record_ids.filtered(
            lambda r: r.state != 'approved'
        ).write({'state': 'cancelled'})
        self.write({
            'state': 'draft',
            'current_node_ids': [(5, 0, 0)],
            'completed_node_ids': [(5, 0, 0)],
        })
        self.action_submit()

    def action_handler_done(self):
        self.ensure_one()
        handler = self.env.user
        active_record = self._get_user_active_handler_record(handler)

        if not active_record:
            raise UserError(_('您没有待办理的节点。'))

        active_record.write({
            'state': 'approved',
            'comment': _('已办理'),
            'approved_date': fields.Datetime.now(),
        })

        node = active_record.node_id
        self._complete_node(node)
        self.message_post(
            body=_('%s 已完成办理【%s】节点。') % (handler.name, node.name)
        )

    # ── 内部：图遍历 ──────────────────────────────────────────

    def _get_start_nodes(self):
        return self.flow_id.node_ids.filtered(
            lambda n: n.active and not n.parent_ids
        )

    def _get_end_nodes(self):
        return self.flow_id.node_ids.filtered(
            lambda n: n.active and not n.child_ids
        )

    def _get_user_active_record(self, user):
        return self.record_ids.filtered(
            lambda r: r.record_type == 'approver'
            and r.approver_id == user
            and r.state == 'pending'
            and r.node_id in self.current_node_ids
        )

    def _get_user_active_handler_record(self, user):
        return self.record_ids.filtered(
            lambda r: r.record_type == 'handler'
            and r.approver_id == user
            and r.state == 'pending'
            and r.node_id in self.current_node_ids
        )

    def _activate_node(self, node):
        self.ensure_one()
        if node.node_type in ('approver', 'handler'):
            if node.node_type == 'approver':
                users = node.get_approvers(self)
                record_type = 'approver'
            else:
                users = node.get_handlers(self)
                record_type = 'handler'

            for user in users:
                self.env['approval.record'].create({
                    'request_id': self.id,
                    'node_id': node.id,
                    'approver_id': user.id,
                    'state': 'pending',
                    'record_type': record_type,
                })
            self._notify_users(node, users, node.node_type)

        elif node.node_type == 'cc':
            users = node.get_cc_users(self)
            for user in users:
                self.env['approval.cc'].create({
                    'request_id': self.id,
                    'node_id': node.id,
                    'user_id': user.id,
                })
            self._notify_users(node, users, 'cc')
            self._complete_node(node)

        elif node.node_type == 'condition':
            next_nodes = node.evaluate_condition(self)
            if next_nodes:
                self._complete_node(node)
                node_names = ', '.join(next_nodes.mapped('name'))
                self.message_post(
                    body=_('条件分支【%s】→ 流转到【%s】。') % (node.name, node_names)
                )
                for next_node in next_nodes:
                    self._activate_node(next_node)
            else:
                self._complete_node(node)
                self.message_post(
                    body=_('条件分支【%s】无匹配规则，流程终止。') % node.name
                )

    def _complete_node(self, node):
        self.ensure_one()
        self.write({
            'current_node_ids': [(3, node.id)],
            'completed_node_ids': [(4, node.id)],
        })

        if node.node_type == 'condition':
            return

        children = node.child_ids.filtered('active')
        if not children:
            if not self.current_node_ids:
                self._finish_approval()
            return

        children_to_activate = self.env['approval.node'].browse()
        for child in children:
            parents = child.parent_ids.filtered('active')
            all_parents_done = all(
                p in self.completed_node_ids for p in parents
            )
            if all_parents_done and child not in self.current_node_ids:
                children_to_activate |= child

        if children_to_activate:
            self.write({
                'current_node_ids': [(4, n.id) for n in children_to_activate],
            })
            for child in children_to_activate:
                self._activate_node(child)

    def _check_node_approved(self, node):
        node_records = self.record_ids.filtered(
            lambda r: r.node_id == node and r.record_type == 'approver'
        )
        if node.sign_type == 'countersign':
            return all(r.state == 'approved' for r in node_records)
        elif node.sign_type == 'or_sign':
            return any(r.state == 'approved' for r in node_records)
        return False

    def _cancel_node_pending_records(self, node):
        self.record_ids.filtered(
            lambda r: r.node_id == node and r.state == 'pending'
        ).write({'state': 'cancelled'})

    def _reject_all_pending(self):
        self.record_ids.filtered(
            lambda r: r.state == 'pending'
        ).write({'state': 'cancelled'})
        self._sync_business_model('rejected')

    def _finish_approval(self):
        self.write({
            'state': 'approved',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('🎉 审批全部通过！'))
        self._sync_business_model('approved')

    def _sync_business_model(self, new_state):
        if self.model_name and self.res_id:
            try:
                target = self.env[self.model_name].browse(self.res_id)
                if target.exists() and hasattr(target, 'approval_state'):
                    target.with_context(_approval_syncing=True).write(
                        {'approval_state': new_state}
                    )
            except Exception:
                _logger.exception(
                    '同步审批状态到业务模型失败: model=%s, res_id=%s, state=%s',
                    self.model_name, self.res_id, new_state,
                )

    def _notify_users(self, node, users, action_type):
        if not users:
            return
        labels = {
            'approver': '审批',
            'handler': '办理',
            'cc': '抄送',
        }
        action_label = labels.get(action_type, '处理')

        for user in users:
            self.message_post(
                body=_('请 %s %s【%s】节点。') % (user.name, action_label, node.name),
                partner_ids=[user.partner_id.id],
                message_type='notification',
            )

    # ── 转交 / 催办 / 超时 ──────────────────────────────────────

    def action_transfer(self, target_user_id):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能转交。'))

        approver = self.env.user
        active_record = self._get_user_active_record(approver)[:1]
        if not active_record:
            handler_record = self._get_user_active_handler_record(approver)
            if handler_record:
                active_record = handler_record
            else:
                raise UserError(_('您没有待处理的节点。'))

        target_user = self.env['res.users'].browse(target_user_id)
        if not target_user.exists():
            raise UserError(_('目标用户不存在。'))

        old_user = active_record.approver_id
        active_record.write({
            'approver_id': target_user.id,
            'comment': _('由 %s 转交给 %s') % (old_user.name, target_user.name),
        })

        self.message_post(
            body=_('%s 将【%s】节点转交给了 %s。') % (
                old_user.name, active_record.node_id.name, target_user.name
            ),
            partner_ids=[target_user.partner_id.id],
            message_type='notification',
        )

    def action_urge(self):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能催办。'))

        pending_records = self.record_ids.filtered(
            lambda r: r.state == 'pending'
            and r.record_type in ('approver', 'handler')
        )
        if not pending_records:
            raise UserError(_('没有待处理的审批记录。'))

        for record in pending_records:
            self.message_post(
                body=_('催办提醒：请 %s 尽快处理【%s】节点。') % (
                    record.approver_id.name, record.node_id.name
                ),
                partner_ids=[record.approver_id.partner_id.id],
                message_type='notification',
            )

    @api.model
    def _cron_check_timeout(self):
        requests = self.search([('state', '=', 'submitted')])
        now = fields.Datetime.now()

        for req in requests:
            for record in req.record_ids.filtered(
                lambda r: r.state == 'pending'
                and r.node_id.timeout_hours > 0
            ):
                if record.create_date:
                    elapsed = (now - record.create_date).total_seconds() / 3600
                    if elapsed >= record.node_id.timeout_hours:
                        last_reminder = record.last_reminder_date
                        if last_reminder:
                            since_last = (now - last_reminder).total_seconds() / 3600
                            if since_last < record.node_id.timeout_hours:
                                continue
                        req.message_post(
                            body=_('超时提醒：%s 的【%s】节点已超时 %d 小时。') % (
                                record.approver_id.name,
                                record.node_id.name,
                                int(elapsed),
                            ),
                            partner_ids=[record.approver_id.partner_id.id],
                            message_type='notification',
                        )
                        record.write({'last_reminder_date': now})

    # ── UI 动作 ────────────────────────────────────────────────

    def action_view_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '审批记录',
            'res_model': 'approval.record',
            'view_mode': 'list,form',
            'domain': [('request_id', '=', self.id)],
        }

    def unlink(self):
        """禁止删除已审批通过的请求"""
        for record in self:
            if record.state == 'approved':
                from odoo.exceptions import UserError
                from odoo import _
                raise UserError(
                    _('审批单 %s 已审批通过，不允许删除。') % record.name
                )
        return super().unlink()

    def action_view_cc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '抄送记录',
            'res_model': 'approval.cc',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
        }