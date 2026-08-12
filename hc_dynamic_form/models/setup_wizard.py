from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalSetupWizard(models.TransientModel):
    _name = 'hc.approval.setup.wizard'
    _description = '一键配置审批类型和流程'

    # 类型信息
    name = fields.Char('审批类型名称', required=True,
                       help='如"付款申请"、"采购申请"')
    code = fields.Char('类型编码', required=True,
                       help='英文唯一标识，如 payment_request')
    model_name = fields.Selection(
        '_get_model_selection', string='关联模型', required=True,
        help='触发此审批的业务模型',
    )
    description = fields.Text('描述')

    # 流程信息
    flow_name = fields.Char('流程名称', required=True,
                            help='默认"基础审批流"即可')
    # 节点信息
    node_count = fields.Integer('审批节点数', default=2, required=True,
                                help='几级审批（建议 2-3）')
    approver_ids = fields.Many2many('res.users', 'hc_approval_setup_user_rel', 'wizard_id', 'user_id',
                                    string='审批人列表',
                                    help='按级别选审批人')

    @api.model
    def _get_model_selection(self):
        return [
            ('hc.form.instance', '动态表单'),
            ('purchase.order', '采购订单'),
            ('hc.purchase.requisition', '请购单'),
            ('hc.purchase.contract', '采购合同'),
            ('hc.purchase.quote', '采购报价'),
            ('sale.order', '销售订单'),
            ('hr.expense', '费用报销'),
            ('account.move', '账单'),
        ]

    def action_create(self):
        """创建审批类型+流程+节点"""
        self.ensure_one()
        if not self.name or not self.code or not self.model_name:
            raise UserError(_('请填写完整的类型信息。'))
        if self.node_count < 1 or self.node_count > 10:
            raise UserError(_('审批节点数应在 1-10 之间。'))

        # 1. 创建审批类型
        Category = self.env['approval.category']
        if Category.search([('code', '=', self.code)], limit=1):
            raise UserError(_('类型编码 "%s" 已存在，请用其他编码。') % self.code)
        category = Category.create({
            'name': self.name,
            'code': self.code,
            'model_name': self.model_name,
            'description': self.description or '',
            'sequence': 10,
        })

        # 2. 创建审批流程
        Flow = self.env['approval.flow']
        flow = Flow.create({
            'name': self.flow_name or f'{self.name}默认流程',
            'category_id': category.id,
            'is_default': True,
            'active': True,
        })

        # 3. 创建审批节点
        Node = self.env['approval.node']
        approvers = self.approver_ids if self.approver_ids else self.env['res.users'].search([], limit=self.node_count)
        for i in range(1, self.node_count + 1):
            approver = approvers[(i - 1) % len(approvers)] if approvers else False
            Node.create({
                'flow_id': flow.id,
                'name': f'第{i}级审批',
                'sequence': i * 10,
                'node_type': 'approver',
                'approver_ids': [(6, 0, [approver.id])] if approver else False,
            })

        # 4. 自动创建对应的动态表单模板（如果模型是 hc.form.instance）
        if self.model_name == 'hc.form.instance':
            Template = self.env['hc.form.template']
            tpl = Template.create({
                'name': self.name,
                'code': self.code,
                'category_id': category.id,
                'description': self.description or '',
            })
            return {
                'type': 'ir.actions.act_window',
                'name': '已创建模板',
                'res_model': 'hc.form.template',
                'res_id': tpl.id,
                'view_mode': 'form',
            }

        return {
            'type': 'ir.actions.act_window',
            'name': '已创建',
            'res_model': 'approval.flow',
            'res_id': flow.id,
            'view_mode': 'form',
        }
