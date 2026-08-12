import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

RESULT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>审批结果</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         display: flex; justify-content: center; align-items: center;
         min-height: 100vh; background: #f5f5f5; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 2px 16px rgba(0,0,0,0.1);
          padding: 48px 40px; text-align: center; max-width: 400px; width: 90%; }
  .icon { width: 64px; height: 64px; border-radius: 50%; display: inline-flex;
          align-items: center; justify-content: center; font-size: 32px; margin-bottom: 20px; }
  .success .icon { background: #e8f5e9; color: #4caf50; }
  .error .icon { background: #ffebee; color: #f44336; }
  h2 { font-size: 20px; margin-bottom: 12px; color: #333; }
  p { font-size: 15px; color: #666; line-height: 1.6; }
</style>
</head>
<body>
<div class="card {css_class}">
  <div class="icon">{icon}</div>
  <h2>{title}</h2>
  <p>{message}</p>
</div>
</body>
</html>"""


class ApprovalExternalController(http.Controller):

    @http.route('/approval/external/callback', type='http', auth='public', methods=['GET'], csrf=False)
    def approval_callback(self, **kwargs):
        request_id = kwargs.get('request_id')
        action = kwargs.get('action', '')
        user_id = kwargs.get('user_id', '0')

        _logger.info('收到外部审批回调: request_id=%s, action=%s, user_id=%s',
                     request_id, action, user_id)

        if not request_id or not user_id:
            return self._render_html(False, '参数不完整')

        try:
            approval_request = request.env['approval.request'].sudo().browse(
                int(request_id)
            )
            odoo_user = request.env['res.users'].sudo().browse(int(user_id))
        except (ValueError, TypeError):
            return self._render_html(False, '无效的参数')

        if not approval_request.exists():
            return self._render_html(False, '审批请求不存在或已被删除')
        if not odoo_user.exists():
            return self._render_html(False, '用户不存在')

        approval_request = approval_request.with_user(odoo_user)

        if action == 'approve':
            return self._handle_approve(approval_request)
        elif action == 'reject':
            return self._handle_reject(approval_request)
        else:
            return self._render_html(False, '无效的操作类型')

    def _handle_approve(self, approval_request):
        if approval_request.state == 'approved':
            return self._render_html(True, '该审批请求已经通过，无需重复操作')
        if approval_request.state != 'submitted':
            return self._render_html(False, f'审批状态为"{approval_request.state}"，无法执行此操作')

        try:
            approval_request.action_approve(comment='外部审批通过')
            return self._render_html(True, f'「{approval_request.name}」已审批通过')
        except Exception as e:
            _logger.exception('外部回调审批失败')
            return self._render_html(False, str(e))

    def _handle_reject(self, approval_request):
        if approval_request.state == 'rejected':
            return self._render_html(True, '该审批请求已被驳回，无需重复操作')
        if approval_request.state != 'submitted':
            return self._render_html(False, f'审批状态为"{approval_request.state}"，无法执行此操作')

        try:
            approval_request.action_reject(reason='外部审批驳回')
            return self._render_html(True, f'「{approval_request.name}」已驳回')
        except Exception as e:
            _logger.exception('外部回调驳回失败')
            return self._render_html(False, str(e))

    def _render_html(self, success, message):
        if success:
            html = RESULT_HTML.format(
                css_class='success',
                icon='✓',
                title='操作成功',
                message=message,
            )
        else:
            html = RESULT_HTML.format(
                css_class='error',
                icon='✗',
                title='操作失败',
                message=message,
            )
        return request.make_response(html)