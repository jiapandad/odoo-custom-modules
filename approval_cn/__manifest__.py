{
    'name': '中国式审批系统',
    'version': '19.0.2.0.0',
    'category': 'Approvals',
    'summary': '符合中国企业管理特色的审批系统，支持自定义环节、条件分支、会签或签、抄送',
    'description': """
中国式审批系统 v2.0
==================

功能特性：
---------
* 4种节点类型：审批人、抄送人、条件分支、办理人
* 会签（全部通过）和或签（任一通过）两种审批模式
* 条件分支：按金额范围、部门等条件自动路由到不同审批链
* 并行审批：多个节点同时进行，全部完成后流转
* 抄送通知：审批完成后自动抄送相关人员
* 6种审批人类型：指定用户、用户组、部门经理、直属上级、发起人自选、动态指定
* 审批转交：委托：加签：撤回：批量审批：超时自动处理：审批时间线
* 超时提醒：定时检查超时审批节点并发送提醒
* 附件支持：审批请求支持上传附件
* 自定义审批表单字段（文本/多行/整数/小数/日期/下拉）
* 图结构流程：支持任意复杂的 DAG 审批拓扑
* 完整的审批历史、抄送记录和审计追踪
* 高度可扩展的混入类设计（4个回调钩子）
* 记录级安全规则
    """,
    'author': 'Odoo CN',
    'website': 'https://www.odoo.com',
    'license': 'LGPL-3',
    'sequence': 90,
    'depends': ['base', 'hr', 'mail', 'web'],
    'data': [
        'security/approval_cn_groups.xml',
        'security/approval_cn_rules.xml',
        'security/ir.model.access.csv',

        'views/approval_category_views.xml',
        'views/approval_flow_views.xml',
        'views/approval_node_views.xml',
        'views/approval_wizard_views.xml',
        'views/approval_request_views.xml',
        'views/approval_record_views.xml',
        'views/approval_cn_menus.xml',

        'data/approval_category_data.xml',
        'data/approval_cron.xml',
    ],
    'demo': [
        'data/approval_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'approval_cn/static/src/scss/approval_cn.scss',
        ],
    },
    'i18n': True,
    'installable': True,
    'application': True,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}