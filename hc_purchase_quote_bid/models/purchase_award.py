from odoo import fields, models


class PurchaseAward(models.Model):
    _name = 'hc.purchase.award'
    _description = '定标记录'
    _inherit = ['mail.thread']

    name = fields.Char('定标编号', readonly=True, copy=False, default='新建')
    comparison_id = fields.Many2one(
        'hc.bid.comparison', '比价单',
        required=True, ondelete='cascade',
    )
    winner_partner_id = fields.Many2one(
        'res.partner', '中标供应商', required=True,
    )
    award_reason = fields.Text('定标理由')
    state = fields.Selection([
        ('draft', '草稿'),
        ('done', '已完成'),
    ], '状态', default='draft')
    company_id = fields.Many2one(
        'res.company', '公司',
        related='comparison_id.company_id', store=True,
    )
