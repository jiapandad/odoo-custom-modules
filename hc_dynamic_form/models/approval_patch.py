"""Override approval.record to support historical archiving and cascade delete.

Key design:
- node_id / approver_id 改为 nullable（用 False 表示"节点/审批人已被删除"）
- 用 ORM 字段约束 ondelete='cascade' 让删除节点时自动清理
- 提供归档方法：旧审批人离职后，保留历史记录但清空 node/approver FK
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalRecord(models.Model):
    _inherit = 'approval.record'

    # 改用 ondelete='cascade'（不是 restrict）：删除节点/审批人时自动清理
    # required=False 使 archived 状态可保留历史快照
    node_id = fields.Many2one(
        'approval.node', string='审批节点',
        ondelete='cascade', index=True, required=False,
    )
    approver_id = fields.Many2one(
        'res.users', string='审批人/办理人',
        ondelete='cascade', index=True, required=False,
    )

    # 归档：用户离职/岗位变动时调用
    def action_archive_history(self, reason=''):
        """把已完成的审批人/节点引用清空（保留历史值在 snapshot_* 字段）"""
        for rec in self:
            update_vals = {}
            # 如果还没保存过原值，则保存到 snapshot
            if rec.node_id and not rec.snapshot_node_name:
                update_vals['snapshot_node_name'] = rec.node_id.name
                update_vals['node_id'] = False
            if rec.approver_id and not rec.snapshot_approver_name:
                update_vals['snapshot_approver_name'] = rec.approver_id.display_name
                update_vals['approver_id'] = False
            if update_vals:
                rec.write(update_vals)
        return True

    # 添加历史快照字段（防止 FK 清空后无法显示）
    snapshot_node_name = fields.Char('节点名称（历史）', readonly=True)
    snapshot_approver_name = fields.Char('审批人（历史）', readonly=True)

    @api.depends('node_id', 'snapshot_node_name', 'approver_id', 'snapshot_approver_name', 'state', 'record_type')
    def _compute_display_name(self):
        super()._compute_display_name() if hasattr(self, '_compute_display_name') else None
        for rec in self:
            node_name = rec.node_id.name if rec.node_id else (rec.snapshot_node_name or '')
            approver_name = rec.approver_id.display_name if rec.approver_id else (rec.snapshot_approver_name or '')
            rec.display_name = f"{node_name} / {approver_name}"


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    @api.model
    def _on_approval_history_update(self, records, old_approver=None, old_node=None):
        """节点/审批人变更时，调用此方法归档历史审批记录。

        由外部代码（hc 模块的 _auto_archive_changed_*）调用
        """
        for rec in records:
            if rec.state in ('pending', 'submitted') and old_approver and rec.approver_id == old_approver:
                # 正在进行的记录：保留，但记录变更原因
                rec.message_post(body=_(
                    '审批人已变更：原 %s → 新 %s'
                ) % (old_approver.display_name, rec.approver_id.display_name))
            else:
                # 已完成：归档
                rec.sudo().action_archive_history()


class ApprovalNode(models.Model):
    _inherit = 'approval.node'

    def write(self, vals):
        """允许修改已存在的节点。
        白名单字段：approver_ids/approver_group_ids/name 任何时候都可改
        结构性字段（flow_id/parent_ids/child_ids/node_type）仅当无 pending 任务时允许
        """
        always_allowed = {
            'approver_ids', 'approver_group_ids', 'name',
            'sequence', 'sign_type', 'approver_type',
            'handler_type', 'handler_ids', 'handler_group_ids',
            'cc_type', 'cc_ids', 'cc_group_ids', 'default_child_id',
            'description', 'active',
        }
        protected = {'flow_id', 'parent_ids', 'child_ids', 'node_type'}

        for record in self:
            to_check = protected & set(vals.keys())
            if not to_check:
                continue
            has_pending = self.env['approval.record'].search_count([
                ('node_id', '=', record.id),
                ('state', '=', 'pending'),
            ])
            if has_pending:
                raise UserError(_(
                    '节点 "%s" 有进行中的审批任务，无法修改结构字段 %s。\n'
                    '请先处理完相关审批。'
                ) % (record.name, ', '.join(to_check)))
        return super().write(vals)

    def unlink(self):
        """允许删除节点。FK 约束已改为 ON DELETE CASCADE（migration），
        关联记录会自动清理。进行中的 pending 任务仍阻止删除。"""
        for node in self:
            pending = self.env['approval.record'].search_count([
                ('node_id', '=', node.id),
                ('state', '=', 'pending'),
            ])
            if pending:
                raise UserError(_(
                    '节点 "%s" 有进行中的审批任务，无法删除。\n'
                    '请先处理完相关审批。'
                ) % node.name)
        return super().unlink()


class ApprovalFlow(models.Model):
    _inherit = 'approval.flow'

    def write(self, vals):
        """允许修改流程的描述、是否默认等（不影响节点结构）。"""
        structural = {'node_ids', 'category_id', 'condition_type', 'condition_lines'}
        for record in self:
            intersection = structural & set(vals.keys())
            if intersection:
                active = self.env['approval.request'].search_count([
                    ('flow_id', '=', record.id),
                    ('state', '=', 'submitted'),
                ])
                if active:
                    raise UserError(_(
                        '流程 "%s" 有进行中的审批请求，无法修改结构 %s。\n'
                        '请先处理完所有审批，或新建一个流程替换。'
                    ) % (record.name, ', '.join(intersection)))
        return super().write(vals)
