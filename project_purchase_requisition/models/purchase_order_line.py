from odoo import api, fields, models

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    project_id = fields.Many2one(
        'project.project', string='关联项目',
        help='选择项目，自动填充该项目的分析账户',
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
            for line in self:
                if vals.get('project_id') is False:
                    vals2 = dict(vals)
                    vals2.pop('project_id', None)
                    super(PurchaseOrderLine, line).write(vals2)
                    line.analytic_distribution = False
                    continue
                project = self.env['project.project'].browse(vals['project_id'])
                if project.account_id and not vals.get('analytic_distribution'):
                    line.analytic_distribution = {str(project.account_id.id): 100}
        return super().write(vals)
