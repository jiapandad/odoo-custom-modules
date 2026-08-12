from odoo import api, fields, models

class HrExpense(models.Model):
    _inherit = 'hr.expense'

    project_id = fields.Many2one(
        'project.project', string='关联项目',
        help='选择费用归属的项目',
        index=True,
    )

    @api.onchange('project_id')
    def _onchange_project_id(self):
        if self.project_id and self.project_id.account_id:
            self.analytic_distribution = {str(self.project_id.account_id.id): 100}
        elif not self.project_id:
            self.analytic_distribution = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('project_id') and not vals.get('analytic_distribution'):
                project = self.env['project.project'].browse(vals['project_id'])
                if project.account_id:
                    vals['analytic_distribution'] = {str(project.account_id.id): 100}
        return super().create(vals_list)

    def write(self, vals):
        if 'project_id' in vals:
            if vals.get('project_id') is False:
                self.analytic_distribution = False
            else:
                project = self.env['project.project'].browse(vals['project_id'])
                if project.account_id and not vals.get('analytic_distribution'):
                    self.analytic_distribution = {str(project.account_id.id): 100}
        return super().write(vals)
