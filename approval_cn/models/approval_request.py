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

    # ── 审批进度 ──
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

    # ── 加签记录 ──
    countersign_ids = fields.One2many(
        'approval.countersign', 'request_id', string='加签记录',
    )
    countersign_count = fields.Integer(
        string='加签次数', compute='_compute_countersign_count',
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

    # ── 委托 ──
    delegate_user_id = fields.Many2one(
        'res.users', string='委托审批人',
        help='将当前用户的所有待审批任务委托给此用户处理',
    )

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

    @api.depends('countersign_ids')
    def _compute_countersign_count(self):
        for req in self:
            req.countersign_count = len(req.countersign_ids)

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
        self._send_push_notification('submitted')
        self._sync_business_model('submitted')

    def action_approve(self, comment=''):
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能审批。'))

        approver = self.env.user
        active_record = self._get_user_active_record(approver)[:1]

        if not active_record:
            # Check delegate
            delegate_record = self._get_user_delegate_record(approver)
            if delegate_record:
                active_record = delegate_record
            else:
                raise UserError(_('您没有待审批的节点。'))

        active_record.write({
            'state': 'approved',
            'comment': comment or _('同意'),
            'approved_date': fields.Datetime.now(),
        })

        node = active_record.node_id
        self.message_post(
            body=_('%s 审批通过【%s】节点。%s') % (
                approver.name, node.name,
                (' (委托)' if active_record.delegate_from_id else '')
            )
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
            delegate_record = self._get_user_delegate_record(approver)
            if delegate_record:
                active_record = delegate_record
            else:
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
        self._send_push_notification('rejected')

    # ── 撤回（仅提交人可用） ────────────────────────────────────

    def action_recall(self):
        """提交人撤回审批中的请求"""
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能撤回。'))
        if self.env.user != self.request_user_id and not self.env.user._is_admin():
            raise UserError(_('只有申请人或管理员才能撤回审批请求。'))

        self.record_ids.filtered(lambda r: r.state == 'pending').write({
            'state': 'cancelled',
        })
        self.write({
            'state': 'cancelled',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(
            body=_('审批请求已被申请人 %s 撤回。') % self.env.user.name
        )
        self._send_push_notification('recalled')
        self._sync_business_model('cancelled')

    def action_cancel(self):
        self.ensure_one()
        if self.state not in ('draft', 'submitted'):
            raise UserError(_('只有草稿或审批中的请求才能取消。'))

        if self.state == 'submitted' and self.env.user != self.request_user_id \
                and not self.env.user._is_admin():
            raise UserError(_('只有申请人或管理员才能取消审批中的请求。'))

        self.record_ids.filtered(lambda r: r.state == 'pending').write({
            'state': 'cancelled',
        })
        self.write({
            'state': 'cancelled',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('审批请求已取消。'))
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

    # ── 加签 ────────────────────────────────────────────────────

    def action_countersign(self, user_id, position='after', comment=''):
        """
        加签：在当前审批节点添加额外审批人
        :param user_id: 被加签的用户ID
        :param position: 'before'(前加签) 或 'after'(后加签)
        :param comment: 加签原因
        """
        self.ensure_one()
        if self.state != 'submitted':
            raise UserError(_('只有审批中的请求才能加签。'))

        approver = self.env.user
        active_record = self._get_user_active_record(approver)[:1]

        if not active_record:
            raise UserError(_('您没有待审批的节点，无法加签。'))

        target_user = self.env['res.users'].browse(user_id)
        if not target_user.exists():
            raise UserError(_('目标用户不存在。'))
        if target_user == approver:
            raise UserError(_('不能给自己加签。'))

        node = active_record.node_id
        position_label = _('前加签') if position == 'before' else _('后加签')

        # Create countersign record
        cs = self.env['approval.countersign'].create({
            'request_id': self.id,
            'node_id': node.id,
            'from_user_id': approver.id,
            'to_user_id': target_user.id,
            'position': position,
            'comment': comment or '',
            'state': 'pending',
            'record_id': active_record.id,
        })

        # Create a new pending record for the countersigning user
        new_record = self.env['approval.record'].create({
            'request_id': self.id,
            'node_id': node.id,
            'approver_id': target_user.id,
            'state': 'pending' if position == 'before' else 'waiting',
            'record_type': 'approver',
            'countersign_id': cs.id,
        })

        cs.write({'new_record_id': new_record.id})

        # If 前加签 (before): 当前审批人暂停 → 加签人先审批
        if position == 'before':
            active_record.write({'state': 'waiting'})

        self.message_post(
            body=_('%(approver)s 对【%(node)s】节点进行了%(pos)s，加签人：%(target)s。原因：%(reason)s') % {
                'approver': approver.name,
                'node': node.name,
                'pos': position_label,
                'target': target_user.name,
                'reason': comment or _('未说明'),
            },
            partner_ids=[target_user.partner_id.id, approver.partner_id.id],
            message_type='notification',
        )
        self._send_push_notification('countersign', user_ids=[target_user.id])

    def _get_user_delegate_record(self, user):
        """获取用户作为委托审批人的待处理记录"""
        return self.record_ids.filtered(
            lambda r: r.record_type == 'approver'
            and r.state == 'pending'
            and r.node_id in self.current_node_ids
            and r.delegate_from_id
            and user in r.delegate_from_id.delegate_user_id
        )[:1]

    # ── 批量审批 ─────────────────────────────────────────────────

    @api.model
    def action_batch_approve(self, request_ids, comment=''):
        """批量审批多个请求"""
        requests = self.browse(request_ids)
        if not requests:
            raise UserError(_('请选择要审批的请求。'))

        approved = []
        errors = []
        for req in requests:
            try:
                req.action_approve(comment=comment or _('批量审批通过'))
                approved.append(req.name)
            except UserError as e:
                errors.append(f'{req.name}: {str(e)}')

        msg = _('批量审批完成：通过 %d 个') % len(approved)
        if errors:
            msg += _('，失败 %d 个：\n%s') % (len(errors), '\n'.join(errors))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('批量审批'),
                'message': msg,
                'type': 'success' if not errors else 'warning',
                'sticky': True if errors else False,
            }
        }

    @api.model
    def action_batch_reject(self, request_ids, reason=''):
        """批量驳回多个请求"""
        requests = self.browse(request_ids)
        if not requests:
            raise UserError(_('请选择要驳回的请求。'))

        rejected = []
        errors = []
        for req in requests:
            try:
                req.action_reject(reason=reason or _('批量驳回'))
                rejected.append(req.name)
            except UserError as e:
                errors.append(f'{req.name}: {str(e)}')

        msg = _('批量驳回完成：%d 个') % len(rejected)
        if errors:
            msg += _('，失败 %d 个：\n%s') % (len(errors), '\n'.join(errors))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('批量驳回'),
                'message': msg,
                'type': 'success' if not errors else 'warning',
                'sticky': True if errors else False,
            }
        }

    # ── 委托 ──────────────────────────────────────────────────────

    @api.model
    def action_set_delegate(self, delegate_user_id):
        """设置委托审批人"""
        user = self.env.user
        if not delegate_user_id:
            user.write({'delegate_user_id': False})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('委托审批'),
                    'message': _('已取消委托。'),
                    'type': 'info',
                }
            }

        target = self.env['res.users'].browse(delegate_user_id)
        if not target.exists():
            raise UserError(_('目标用户不存在。'))

        user.write({'delegate_user_id': target.id})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('委托审批'),
                'message': _('已将审批任务委托给 %s。') % target.name,
                'type': 'success',
            }
        }

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
        # First check delegate records
        delegate_records = self.record_ids.filtered(
            lambda r: r.record_type == 'approver'
            and r.state == 'pending'
            and r.node_id in self.current_node_ids
            and r.delegate_from_id
            and user in r.delegate_from_id.delegate_user_id
        )
        if delegate_records:
            return delegate_records

        # Then check own records
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
                # Check if user has a delegate set
                delegate_id = False
                if hasattr(user, 'delegate_user_id') and user.delegate_user_id:
                    # Create records for both original and delegate
                    self.env['approval.record'].create({
                        'request_id': self.id,
                        'node_id': node.id,
                        'approver_id': user.delegate_user_id.id,
                        'state': 'pending',
                        'record_type': record_type,
                        'delegate_from_id': user.id,
                    })
                    delegate_id = user.delegate_user_id

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

        # If countersign after completed node, append to next nodes
        pending_countersigns = self.countersign_ids.filtered(
            lambda c: c.state == 'pending' and c.position == 'after' and c.record_id.node_id == node
        )
        for cs in pending_countersigns:
            if cs.new_record_id and cs.new_record_id.state == 'waiting':
                cs.new_record_id.write({'state': 'pending'})
                cs.write({'state': 'done'})

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
        # Only count non-waiting records
        node_records = node_records.filtered(lambda r: r.state != 'waiting')
        if node.sign_type == 'countersign':
            return all(r.state == 'approved' for r in node_records)
        elif node.sign_type == 'or_sign':
            return any(r.state == 'approved' for r in node_records)
        return False

    def _cancel_node_pending_records(self, node):
        self.record_ids.filtered(
            lambda r: r.node_id == node and r.state in ('pending', 'waiting')
        ).write({'state': 'cancelled'})

    def _reject_all_pending(self):
        self.record_ids.filtered(
            lambda r: r.state in ('pending', 'waiting')
        ).write({'state': 'cancelled'})
        # Also cancel pending countersigns
        self.countersign_ids.filtered(
            lambda c: c.state == 'pending'
        ).write({'state': 'cancelled'})
        self._sync_business_model('rejected')

    def _finish_approval(self):
        self.write({
            'state': 'approved',
            'current_node_ids': [(5, 0, 0)],
            'approved_date': fields.Datetime.now(),
        })
        self.message_post(body=_('🎉 审批全部通过！'))
        self._send_push_notification('approved')
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

        # External push notification hook
        self._send_push_notification(action_type, user_ids=users.ids)

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
        self._send_push_notification('transfer', user_ids=[target_user.id])

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
            self._send_push_notification('urge', user_ids=[record.approver_id.id])

    @api.model
    def _cron_check_timeout(self):
        """定时任务：检查超时审批并自动处理"""
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
                        node = record.node_id
                        # Auto-action based on node config
                        if node.timeout_action == 'auto_approve':
                            record.write({
                                'state': 'approved',
                                'comment': _('超时自动通过（%d小时未处理）') % int(elapsed),
                                'approved_date': now,
                            })
                            req.message_post(
                                body=_('%s 的【%s】节点超时 %d 小时，自动通过。') % (
                                    record.approver_id.name, node.name, int(elapsed)
                                )
                            )
                            if req._check_node_approved(node):
                                req._complete_node(node)

                        elif node.timeout_action == 'auto_reject':
                            record.write({
                                'state': 'rejected',
                                'comment': _('超时自动驳回（%d小时未处理）') % int(elapsed),
                                'approved_date': now,
                            })
                            req._reject_all_pending()
                            req.write({
                                'state': 'rejected',
                                'current_node_ids': [(5, 0, 0)],
                                'approved_date': now,
                            })
                            req.message_post(
                                body=_('%s 的【%s】节点超时 %d 小时，自动驳回。') % (
                                    record.approver_id.name, node.name, int(elapsed)
                                )
                            )
                            req._send_push_notification('auto_rejected')

                        else:
                            # Just remind
                            last_reminder = record.last_reminder_date
                            if last_reminder:
                                since_last = (now - last_reminder).total_seconds() / 3600
                                if since_last < node.timeout_hours:
                                    continue
                            req.message_post(
                                body=_('超时提醒：%s 的【%s】节点已超时 %d 小时。') % (
                                    record.approver_id.name, node.name, int(elapsed),
                                ),
                                partner_ids=[record.approver_id.partner_id.id],
                                message_type='notification',
                            )
                            record.write({'last_reminder_date': now})
                            req._send_push_notification('timeout', user_ids=[record.approver_id.id])

    # ── 推送通知钩子 ──────────────────────────────────────────

    def _send_push_notification(self, event, user_ids=None):
        """
        外部平台推送通知钩子（企业微信/钉钉/邮件）
        子模块（approval_cn_external）可重写此方法
        """
        # 基类默认不做任何外部推送
        # 子模块通过继承重写此方法实现具体平台的推送
        self.ensure_one()
        if not user_ids:
            user_ids = []

        # 发送邮件通知（通过 mail.message）
        # 外部平台推送由 approval_cn_external 模块处理
        _logger.info(
            '审批推送事件: request=%s, event=%s, users=%s',
            self.name, event, user_ids
        )

    # ── UI 动作 ────────────────────────────────────────────────

    def action_view_records(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '审批记录',
            'res_model': 'approval.record',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
        }

    def action_view_countersigns(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '加签记录',
            'res_model': 'approval.countersign',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
        }

    def action_view_timeline(self):
        """返回审批时间线数据"""
        self.ensure_one()
        timeline = []
        # Submission
        timeline.append({
            'date': self.request_date,
            'event': 'submitted',
            'label': _('提交审批'),
            'user': self.request_user_id.name,
        })
        # Records
        for rec in self.record_ids.sorted('create_date'):
            if rec.state == 'approved':
                label = _('审批通过')
            elif rec.state == 'rejected':
                label = _('审批驳回')
            elif rec.state == 'cancelled':
                label = _('已取消')
            elif rec.state == 'waiting':
                label = _('等待加签')
            else:
                label = _('待处理')
            timeline.append({
                'date': rec.approved_date or rec.create_date,
                'event': rec.state,
                'label': f'{rec.node_id.name} - {label}',
                'user': rec.approver_id.name,
                'comment': rec.comment,
            })
        # Countersigns
        for cs in self.countersign_ids:
            pos = _('前加签') if cs.position == 'before' else _('后加签')
            timeline.append({
                'date': cs.create_date,
                'event': 'countersign',
                'label': f'{pos}：{cs.from_user_id.name} → {cs.to_user_id.name}',
                'user': cs.from_user_id.name,
                'comment': cs.comment,
            })
        # Sort
        timeline.sort(key=lambda x: x['date'] or '')
        return timeline

    def action_view_cc(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '抄送记录',
            'res_model': 'approval.cc',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
        }

    def unlink(self):
        """禁止删除已审批通过的请求"""
        for record in self:
            if record.state == 'approved':
                raise UserError(
                    _('审批单 %s 已审批通过，不允许删除。') % record.name
                )
        return super().unlink()
