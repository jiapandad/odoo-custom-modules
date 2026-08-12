from odoo import api, fields, models

class ProjectProject(models.Model):
    _inherit = 'project.project'

    budget_amount = fields.Monetary(
        string='项目总预算', currency_field='currency_id',
        tracking=True, help='本项目的总预算金额',
    )
    purchase_cost = fields.Monetary(
        string='采购花费', currency_field='currency_id',
        compute='_compute_purchase_cost',
        help='通过采购订单关联本项目的总花费',
    )
    bill_cost = fields.Monetary(
        string='供应商账单', currency_field='currency_id',
        compute='_compute_bill_cost',
        help='关联到本项目的供应商应付账单金额',
    )
    other_cost = fields.Monetary(
        string='其他费用', currency_field='currency_id',
        compute='_compute_other_cost',
        help='关联到本项目的分析分录总额（工时、费用报销等）',
    )
    total_cost = fields.Monetary(
        string='总花费', currency_field='currency_id',
        compute='_compute_total_cost',
    )
    remaining_budget = fields.Monetary(
        string='剩余预算', currency_field='currency_id',
        compute='_compute_remaining_budget',
    )
    budget_percent_used = fields.Float(
        string='使用率', compute='_compute_budget_percent',
    )
    currency_id = fields.Many2one(
        'res.currency', string='货币', related='company_id.currency_id',
    )

    def _compute_purchase_cost(self):
        for project in self:
            if not project.account_id:
                project.purchase_cost = 0.0
                continue
            aid = str(project.account_id.id)
            self.env.cr.execute(
                "SELECT COALESCE(SUM(pol.price_unit * pol.product_qty), 0.0) "
                "FROM purchase_order_line pol "
                "JOIN purchase_order po ON pol.order_id = po.id "
                "WHERE po.state IN ('purchase','done') "
                "AND pol.analytic_distribution ? %s",
                [aid])
            result = self.env.cr.fetchone()
            project.purchase_cost = result[0] if result else 0.0

    def _compute_bill_cost(self):
        for project in self:
            if not project.account_id:
                project.bill_cost = 0.0
                continue
            aid = str(project.account_id.id)
            self.env.cr.execute(
                "SELECT COALESCE(SUM(aml.balance), 0.0) "
                "FROM account_move_line aml "
                "JOIN account_move am ON aml.move_id = am.id "
                "WHERE am.move_type = 'in_invoice' AND am.state = 'posted' "
                "AND aml.analytic_distribution ? %s",
                [aid])
            result = self.env.cr.fetchone()
            project.bill_cost = abs(result[0]) if result else 0.0

    def _compute_other_cost(self):
        for project in self:
            if not project.account_id:
                project.other_cost = 0.0
                continue
            self.env.cr.execute(
                "SELECT COALESCE(SUM(aal.amount), 0.0) "
                "FROM account_analytic_line aal "
                "WHERE aal.account_id = %s",
                [project.account_id.id])
            result = self.env.cr.fetchone()
            project.other_cost = abs(result[0]) if result else 0.0

    @api.depends('purchase_cost', 'bill_cost', 'other_cost')
    def _compute_total_cost(self):
        for p in self:
            p.total_cost = p.purchase_cost + p.bill_cost + p.other_cost

    @api.depends('budget_amount', 'total_cost')
    def _compute_remaining_budget(self):
        for p in self:
            p.remaining_budget = p.budget_amount - p.total_cost

    @api.depends('budget_amount', 'total_cost')
    def _compute_budget_percent(self):
        for p in self:
            if p.budget_amount and p.budget_amount > 0:
                p.budget_percent_used = round(p.total_cost / p.budget_amount, 4)
            else:
                p.budget_percent_used = 0.0
