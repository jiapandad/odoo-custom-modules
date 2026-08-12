{
    'name': '请购单管理',
    'version': '19.0.1.2.0',
    'category': 'Purchases',
    'summary': '多公司请购单管理，集成审批流程',
    'description': """
        请购单模块，支持多公司/多组织环境。
        功能：
        - 请购单创建、编辑、提交
        - 按部门/项目归集物料需求
        - 集成 approval_cn 审批流程
        - 审批通过后自动生成采购需求任务
        - 请购单状态追踪（草稿→审批中→已审批→已下推采购→完成）
    """,
    'author': 'HC',
    'website': '',
    'depends': [
        'base',
        'product',
        'purchase',
        'stock',
        'hr',
        'approval_cn',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'data/approval_data.xml',
        'views/purchase_requisition_views.xml',
        'views/purchase_order_views.xml',
        'views/approval_request_inherit.xml',
        'views/menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
