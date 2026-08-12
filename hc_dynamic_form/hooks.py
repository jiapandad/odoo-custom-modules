from odoo import SUPERUSER_ID


def post_init_hook(env):
    """Ensure ir.model records exist for hc_dynamic_form models."""
    Model = env['ir.model']
    for model_name in (
        'hc.form.template',
        'hc.form.template.field',
        'hc.form.instance',
    ):
        if not Model.search([('model', '=', model_name)]):
            Model.sudo().create({
                'name': model_name.replace('.', ' ').title(),
                'model': model_name,
                'state': 'manual',
            })
