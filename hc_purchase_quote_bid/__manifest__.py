{
    'name': '采购比价定标',
    'version': '19.0.1.0.0',
    'category': 'Purchases',
    'summary': '采购员录入供应商报价 + 比价矩阵 + 定标审批',
    'description': """
        在采购询价单上添加供应商报价录入和比价定标功能。
        功能：
        - 采购员手动录入各供应商报价（品牌、含税单价、交货期等）
        - 自动生成比价对比矩阵
        - 推荐供应商 → 定标 → 审批
        - 定标结果自动更新采购订单供应商
    """,
    'author': 'HC',
    'depends': [
        'base',
        'purchase',
        'product',
        'approval_cn',
        'approval_cn_purchase',
        'hc_purchase_requisition',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/approval_data.xml',
        'data/approval_category_data.xml',
        'views/supplier_quote_views.xml',
        'views/purchase_order_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
