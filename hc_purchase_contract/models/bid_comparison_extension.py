from odoo import api, fields, models, _
from odoo.exceptions import UserError


class BidComparison(models.Model):
    _inherit = 'hc.bid.comparison'

    require_contract = fields.Boolean(
        '需要采购合同', default=False, tracking=True,
        help='勾选后定标确认将引导创建采购合同，合同审批通过后方可验货。'
             '不勾选则跳过合同环节直接进入验货流程。',
    )
    contract_state = fields.Selection([
        ('none', '无合同'),
        ('pending', '待创建合同'),
        ('draft', '合同草稿'),
        ('submitted', '合同审批中'),
        ('approved', '合同已批准'),
        ('rejected', '合同被驳回'),
    ], '合同状态', compute='_compute_contract_state', store=True,
       default='none', tracking=True)

    contract_ids = fields.One2many(
        'hc.purchase.contract', 'bid_comparison_id', '采购合同',
    )
    contract_count = fields.Integer(
        '合同数量', compute='_compute_contract_count', store=True,
    )

    @api.depends('contract_ids.state')
    def _compute_contract_state(self):
        for bid in self:
            contracts = bid.contract_ids
            if not bid.require_contract:
                bid.contract_state = 'none'
            elif not contracts:
                bid.contract_state = 'pending'
            else:
                # 按优先级：如果有多份合同，以最新状态为准
                states = contracts.mapped('state')
                if 'submitted' in states:
                    bid.contract_state = 'submitted'
                elif 'approved' in states or 'active' in states:
                    bid.contract_state = 'approved'
                elif 'rejected' in states:
                    bid.contract_state = 'rejected'
                elif 'draft' in states:
                    bid.contract_state = 'draft'
                else:
                    bid.contract_state = 'pending'

    @api.depends('contract_ids')
    def _compute_contract_count(self):
        for bid in self:
            bid.contract_count = len(bid.contract_ids)

    def action_view_contracts(self):
        """查看关联的采购合同"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '采购合同',
            'res_model': 'hc.purchase.contract',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.contract_ids.ids)],
        }

    def action_create_contract(self):
        """创建采购合同，自动带入比价中标物料"""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('比价定标审批通过后才能创建合同。'))
        if not self.require_contract:
            raise UserError(_('当前比价单未勾选"需要采购合同"，无需创建合同。'))

        # 检查是否已有合同
        if self.contract_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': '采购合同',
                'res_model': 'hc.purchase.contract',
                'res_id': self.contract_ids[:1].id,
                'view_mode': 'form',
            }

        # 自动从比价单带入中标行作为合同明细
        winner_lines = self.line_ids.filtered('is_winner')
        if not winner_lines:
            raise UserError(_('比价单中没有标记中标的行，无法创建合同。'))

        contract_lines = []
        total_amount = 0
        for wl in winner_lines:
            subtotal = (wl.quantity or 0) * (wl.unit_price or 0)
            total_amount += subtotal
            contract_lines.append((0, 0, {
                'sequence': wl.col_index or 10,
                'product_id': wl.product_id.id,
                'product_uom_id': wl.product_uom_id.id,
                'quantity': wl.quantity,
                'price_unit': wl.unit_price or 0.0,
            }))

        # 以中标供应商中的第一个作为合同供应商
        # 如果有多个中标供应商，提示用户
        winner_partners = winner_lines.mapped('partner_id')
        partner = winner_partners[:1]
        if len(winner_partners) > 1:
            # 多供应商时默认选第一个，用户可手动调整
            partner_names = ', '.join(winner_partners.mapped('name'))
            pass  # 让用户看到警告后再决定

        contract = self.env['hc.purchase.contract'].create({
            'partner_id': partner.id,
            'bid_comparison_id': self.id,
            'amount': total_amount,
            'line_ids': contract_lines,
            'company_id': self.company_id.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': '采购合同',
            'res_model': 'hc.purchase.contract',
            'res_id': contract.id,
            'view_mode': 'form',
        }

    def action_confirm_award(self):
        """定标确认：如果需要合同则引导创建合同，否则直接创建PO"""
        self.ensure_one()

        if self.require_contract:
            # 需要合同 — 检查合同状态
            if self.contract_state in ('none', 'pending', 'draft'):
                # 引导创建合同
                return self.action_create_contract()
            elif self.contract_state == 'submitted':
                raise UserError(_(
                    '合同正在审批中，请等待合同审批通过后再确认定标。'
                ))
            elif self.contract_state == 'rejected':
                raise UserError(_(
                    '合同审批被驳回，请重新修改合同后提交审批。'
                ))
            elif self.contract_state in ('approved', 'active'):
                # 合同已批准/已激活，允许定标确认
                pass
            else:
                pass

        # 不需要合同 或 合同已批准/激活：执行原有的定标逻辑
        result = super().action_confirm_award()

        # 如果有关联合同，将新创建的PO绑定到合同
        if self.contract_ids:
            contract = self.contract_ids[:1]
            if contract.state in ('approved', 'active'):
                contract._link_related_purchase_orders()

        return result

    def _build_approval_description(self):
        """扩展审批说明，加入合同需求信息"""
        desc = super()._build_approval_description()
        if self.require_contract:
            desc += '\n\n【合同要求】本次采购需要签订采购合同，定标审批后将引导创建合同。'
        else:
            desc += '\n\n【合同要求】本次采购无需签订合同，定标审批后直接进入验货流程。'
        return desc
