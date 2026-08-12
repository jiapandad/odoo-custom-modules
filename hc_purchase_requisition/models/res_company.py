from odoo import api, models, SUPERUSER_ID


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            self._ensure_warehouse(company)
            self._ensure_account_journals(company)
        return companies

    def _ensure_warehouse(self, company):
        """为新公司自动创建仓库（含入库/出库 picking type）。"""
        warehouse = self.env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1
        )
        if not warehouse:
            self.env['stock.warehouse'].create({
                'name': company.name + ' 仓库',
                'code': 'WH' + str(company.id),
                'company_id': company.id,
            })

    def _ensure_account_journals(self, company):
        """为新公司自动复制会计日记账（从公司1）。"""
        Journal = self.env['account.journal'].sudo()
        existing = Journal.search_count([('company_id', '=', company.id)])
        if existing:
            return

        # 从公司1复制所有日记账
        src_journals = Journal.search([('company_id', '=', 1)])
        for src in src_journals:
            Journal.create({
                'name': src.name,
                'code': src.code,
                'type': src.type,
                'company_id': company.id,
                'default_account_id': src.default_account_id.id,
                'currency_id': src.currency_id.id,
                'sequence': src.sequence,
                'refund_sequence': src.refund_sequence,
                'payment_sequence': src.payment_sequence,
                'show_on_dashboard': src.show_on_dashboard,
            })
