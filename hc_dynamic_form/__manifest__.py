{
    "name": "HC Dynamic Form",
    "version": "19.0.1.0.1",
    "category": "Approval",
    "summary": "Dynamic form module",
    "author": "HC",
    "depends": ["approval_cn", "mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/form_template_views.xml",
        "views/form_instance_views.xml",
        "views/form_menus.xml",
        "views/approval_request_inherit.xml",
        "views/setup_wizard_views.xml"
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
    "auto_install": False
}
