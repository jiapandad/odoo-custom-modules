from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'approval_cn')
class TestApprovalFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env['approval.category']
        cls.Flow = cls.env['approval.flow']
        cls.Node = cls.env['approval.node']
        cls.Request = cls.env['approval.request']
        cls.ConditionLine = cls.env['approval.condition.line']

        cls.category = cls.Category.create({
            'name': '测试审批类型',
            'code': 'test_approval',
            'model_name': 'res.partner',
        })

    def test_create_flow_with_nodes(self):
        flow = self.Flow.create({
            'name': '测试流程',
            'category_id': self.category.id,
            'condition_type': 'always',
        })

        start_node = self.Node.create({
            'name': '开始节点',
            'flow_id': flow.id,
            'node_type': 'approver',
            'approver_type': 'specific_user',
            'approver_ids': [(4, self.env.uid)],
            'sign_type': 'or_sign',
        })

        self.assertEqual(start_node.flow_id, flow)
        self.assertEqual(start_node.node_type, 'approver')

        end_node = self.Node.create({
            'name': '结束节点',
            'flow_id': flow.id,
            'node_type': 'approver',
            'approver_type': 'specific_user',
            'approver_ids': [(4, self.env.uid)],
            'sign_type': 'or_sign',
            'parent_ids': [(4, start_node.id)],
        })

        self.assertIn(end_node, start_node.child_ids)
        self.assertIn(start_node, end_node.parent_ids)

    def test_cycle_detection(self):
        flow = self.Flow.create({
            'name': '循环测试流程',
            'category_id': self.category.id,
            'condition_type': 'always',
        })

        node_a = self.Node.create({
            'name': '节点A',
            'flow_id': flow.id,
            'node_type': 'approver',
            'approver_type': 'specific_user',
            'approver_ids': [(4, self.env.uid)],
            'sign_type': 'or_sign',
        })

        node_b = self.Node.create({
            'name': '节点B',
            'flow_id': flow.id,
            'node_type': 'approver',
            'approver_type': 'specific_user',
            'approver_ids': [(4, self.env.uid)],
            'sign_type': 'or_sign',
            'parent_ids': [(4, node_a.id)],
        })

        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            node_a.write({'parent_ids': [(4, node_b.id)]})

    def test_condition_node_requires_rules(self):
        flow = self.Flow.create({
            'name': '条件测试流程',
            'category_id': self.category.id,
            'condition_type': 'always',
        })

        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Node.create({
                'name': '空条件节点',
                'flow_id': flow.id,
                'node_type': 'condition',
            })

    def test_amount_range_condition(self):
        condition = self.ConditionLine.create({
            'name': '金额范围测试',
            'condition_type': 'amount_range',
            'condition_amount_min': 100,
            'condition_amount_max': 500,
        })

        self.assertTrue(condition.evaluate(amount=100))
        self.assertTrue(condition.evaluate(amount=500))
        self.assertFalse(condition.evaluate(amount=99))
        self.assertFalse(condition.evaluate(amount=501))