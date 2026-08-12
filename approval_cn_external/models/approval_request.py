from odoo import models, _

import logging

_logger = logging.getLogger(__name__)

PLATFORM_DISPLAY = {
    'wechat': '企业微信',
    'dingtalk': '钉钉',
}


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    def _notify_users(self, node, users, action_type):
        super()._notify_users(node, users, action_type)
        self._notify_external_platform(node, users, action_type)

    def _notify_external_platform(self, node, users, action_type):
        if action_type not in ('approver', 'handler'):
            return

        configs = self.env['approval.external.config'].sudo().search([
            ('active', '=', True),
        ])

        for config in configs:
            for user in users:
                mapping = self.env['approval.external.user'].sudo().search([
                    ('config_id', '=', config.id),
                    ('user_id', '=', user.id),
                    ('active', '=', True),
                ], limit=1)

                if not mapping:
                    _logger.debug(
                        '用户 %s 在平台 %s 中无映射，跳过外部通知',
                        user.name, config.platform,
                    )
                    continue

                try:
                    success = config.send_approval_card(
                        mapping.external_user_id, self, user,
                    )
                    if success:
                        self.message_post(
                            body=_('已通过%s向 %s 发送审批通知。') % (
                                PLATFORM_DISPLAY.get(config.platform, config.platform),
                                user.name,
                            ),
                        )
                except Exception as e:
                    _logger.exception('外部通知发送失败: %s', e)