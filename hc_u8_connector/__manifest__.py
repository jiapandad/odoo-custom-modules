{
    "name": "HC U8 Connector",
    "version": "19.0.1.0.0",
    "category": "Purchases",
    "summary": "U8 Multi-Account Connector",
    "author": "HC",
    "depends": [
        "purchase",
        "stock",
        "base"
    ],
    "external_dependencies": {
        "python": [
            "pymssql"
        ]
    },
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/u8_account_views.xml",
        "views/menu.xml"
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3"
}