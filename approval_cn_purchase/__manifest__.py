{
    'name': '审批系统 - 采购模块桥接',
    'version': '19.0.1.0',
    'category': 'Approval',
    'summary': '将审批流程集成到采购订单中',
    'description': '''
        在采购模块中集成审批流程：
        - 采购订单创建后可提交审批
        - 审批通过后方可进行询价、确认订单等操作
        - 审批拒绝后采购订单自动取消
    ''',
    'author': 'SOLO',
    'depends': ['approval_cn', 'purchase'],
    'data': [
        'views/purchase_order_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}