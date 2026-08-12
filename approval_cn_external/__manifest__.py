{
    'name': '审批系统 - 外部平台集成',
    'version': '19.0.1.0',
    'summary': '通过企业微信/钉钉消息卡片执行审批，结果回写Odoo',
    'depends': ['approval_cn', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/external_config_views.xml',
        'views/external_menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}