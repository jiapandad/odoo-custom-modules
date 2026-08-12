from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})

    admin_group = env.ref('approval_cn.group_approval_admin', raise_if_not_found=False)
    user_group = env.ref('approval_cn.group_approval_user', raise_if_not_found=False)
    if not admin_group or not user_group:
        return

    if user_group not in admin_group.implied_ids:
        admin_group.write({'implied_ids': [(4, user_group.id)]})

    admin_user = env.ref('base.user_admin', raise_if_not_found=False)
    if admin_user and admin_user not in admin_group.users:
        admin_group.write({'users': [(4, admin_user.id)]})