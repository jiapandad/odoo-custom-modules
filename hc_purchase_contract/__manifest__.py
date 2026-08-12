{
    'name': '采购合同管理',
    'version': '19.0.1.0.0',
    'category': 'Purchases',
    'summary': '采购合同审批 + 框架合同 + 自动带入采购物资',
    'description': """
        在比价定标后加入合同管理流程：
        - 比价单勾选是否需要采购合同
        - 需要合同 → 创建合同 → 上传合同文件 → 合同审批
        - 不需要合同 → 直接跳转验货
        - 框架合同：月结供应商适用，物料可自动带入后续采购订单
    """,
    'author': 'HC',
    'depends': [
        'base',
        'purchase',
        'product',
        'approval_cn',
        'hc_purchase_quote_bid',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/approval_data.xml',
        'views/purchase_contract_views.xml',
        'views/bid_comparison_views.xml',
        'views/purchase_order_views.xml',
        'views/approval_request_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
