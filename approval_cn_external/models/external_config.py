from odoo import api, fields, models, _
from odoo.exceptions import UserError

import json
import logging
import requests

_logger = logging.getLogger(__name__)


class ApprovalExternalConfig(models.Model):
    _name = 'approval.external.config'
    _description = '外部审批平台配置'

    name = fields.Char(string='名称', required=True)
    platform = fields.Selection([
        ('wechat', '企业微信'),
        ('dingtalk', '钉钉'),
    ], string='平台', required=True)
    active = fields.Boolean(string='启用', default=True)

    corp_id = fields.Char(string='CorpID / AppKey')
    agent_id = fields.Char(string='AgentID / AgentKey')
    secret = fields.Char(string='Secret / AppSecret')
    token = fields.Char(string='回调Token')
    encoding_aes_key = fields.Char(string='回调EncodingAESKey')

    user_mapping_ids = fields.One2many(
        'approval.external.user', 'config_id', string='用户映射',
    )

    def _get_access_token(self):
        self.ensure_one()
        if self.platform == 'wechat':
            return self._get_wechat_token()
        elif self.platform == 'dingtalk':
            return self._get_dingtalk_token()
        return None

    def _get_wechat_token(self):
        url = 'https://qyapi.weixin.qq.com/cgi-bin/gettoken'
        params = {
            'corpid': self.corp_id,
            'corpsecret': self.secret,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                return data.get('access_token')
            _logger.error('企业微信获取token失败: %s', data)
        except Exception as e:
            _logger.exception('企业微信获取token异常: %s', e)
        return None

    def _get_dingtalk_token(self):
        url = 'https://oapi.dingtalk.com/gettoken'
        params = {
            'appkey': self.corp_id,
            'appsecret': self.secret,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                return data.get('access_token')
            _logger.error('钉钉获取token失败: %s', data)
        except Exception as e:
            _logger.exception('钉钉获取token异常: %s', e)
        return None

    def send_approval_card(self, external_user_id, request, odoo_user):
        self.ensure_one()
        if self.platform == 'wechat':
            return self._send_wechat_card(external_user_id, request, odoo_user)
        elif self.platform == 'dingtalk':
            return self._send_dingtalk_card(external_user_id, request, odoo_user)
        return False

    def _send_wechat_card(self, external_user_id, request, odoo_user):
        token = self._get_access_token()
        if not token:
            return False

        url = f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}'
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        active_records = request.record_ids.filtered(
            lambda r: r.state == 'pending'
            and r.record_type in ('approver', 'handler')
        )
        node_names = ', '.join(active_records.mapped('node_id.name'))

        approve_url = (
            f'{base_url}/approval/external/callback'
            f'?request_id={request.id}&action=approve&user_id={odoo_user.id}'
        )
        reject_url = (
            f'{base_url}/approval/external/callback'
            f'?request_id={request.id}&action=reject&user_id={odoo_user.id}'
        )

        amount_text = ''
        if request.amount:
            amount_text = f'\n>**金额**: <font color="warning">¥{request.amount:,.2f}</font>'

        content = (
            f"## {request.name}\n"
            f">申请人: <font color=\"info\">{request.request_user_id.name}</font>\n"
            f">审批类型: {request.category_id.name or ''}\n"
            f">待审批节点: {node_names}\n"
            f">申请时间: {request.request_date or ''}"
            f"{amount_text}\n\n"
            f"[同意]({approve_url})　　　　[驳回]({reject_url})"
        )

        payload = {
            'touser': external_user_id,
            'agentid': int(self.agent_id) if self.agent_id else 0,
            'msgtype': 'markdown',
            'markdown': {
                'content': content,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                _logger.info('企业微信消息发送成功: %s', external_user_id)
                return True
            _logger.error('企业微信消息发送失败: %s', data)
        except Exception as e:
            _logger.exception('企业微信消息发送异常: %s', e)
        return False

    def _send_dingtalk_card(self, external_user_id, request, odoo_user):
        token = self._get_access_token()
        if not token:
            return False

        url = f'https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token={token}'
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')

        active_records = request.record_ids.filtered(
            lambda r: r.state == 'pending'
            and r.record_type in ('approver', 'handler')
        )
        node_names = ', '.join(active_records.mapped('node_id.name'))

        callback_base = (
            f'{base_url}/approval/external/callback'
            f'?request_id={request.id}&user_id={odoo_user.id}'
        )

        markdown_text = (
            f"## {request.name}\n\n"
            f"**申请人**: {request.request_user_id.name}  \n"
            f"**审批类型**: {request.category_id.name or ''}  \n"
            f"**金额**: ¥{request.amount:,.2f}\n" if request.amount else ''
            f"**待审批节点**: {node_names}  \n"
            f"**申请时间**: {request.request_date or ''}  \n"
        )

        payload = {
            'agent_id': int(self.agent_id) if self.agent_id else 0,
            'userid_list': external_user_id,
            'msg': {
                'msgtype': 'action_card',
                'action_card': {
                    'title': request.name,
                    'markdown': markdown_text,
                    'btn_orientation': '0',
                    'btn_json_list': [
                        {
                            'title': '同意',
                            'action_url': f'{callback_base}&action=approve',
                        },
                        {
                            'title': '驳回',
                            'action_url': f'{callback_base}&action=reject',
                        },
                    ],
                },
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get('errcode') == 0:
                _logger.info('钉钉消息发送成功: %s', external_user_id)
                return True
            _logger.error('钉钉消息发送失败: %s', data)
        except Exception as e:
            _logger.exception('钉钉消息发送异常: %s', e)
        return False


class ApprovalExternalUser(models.Model):
    _name = 'approval.external.user'
    _description = '外部平台用户映射'

    config_id = fields.Many2one(
        'approval.external.config', string='平台配置',
        required=True, ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users', string='Odoo用户', required=True,
        ondelete='cascade',
    )
    external_user_id = fields.Char(
        string='外部用户ID', required=True,
        help='企业微信：UserID；钉钉：UserID',
    )
    active = fields.Boolean(string='启用', default=True)