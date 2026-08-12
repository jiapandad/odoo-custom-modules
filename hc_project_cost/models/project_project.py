# -*- coding: utf-8 -*-
"""扩展项目模型，添加总花费计算字段"""
from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = 'project.project'

    total_cost = fields.Float(
        '项目总花费',
        compute='_compute_total_cost',
        store=False,
        help='所有关联采购订单行总金额 + 工时成本',
    )

    def _compute_total_cost(self):
        PurchaseOrder = self.env['purchase.order']
        for project in self:
            # 1) 采购订单总金额（analytic_account_id == 项目分析账户）
            po_total = 0.0
            if project.analytic_account_id:
                orders = PurchaseOrder.sudo().search([
                    ('state', 'in', ['purchase', 'done']),
                    ('analytic_account_id', '=', project.analytic_account_id.id),
                ])
                po_total = sum(orders.mapped('amount_total'))
            # 2) 工时成本
            timesheet_cost = 0.0
            timesheets = project.sudo().mapped('task_ids.timesheet_ids').filtered(
                lambda t: t.unit_amount and t.employee_id.hourly_cost
            )
            for ts in timesheets:
                timesheet_cost += ts.unit_amount * ts.employee_id.hourly_cost

            project.total_cost = po_total + timesheet_cost