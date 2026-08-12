"""Pre-migration: fix approval_record schema to support cascade delete and nullable fields."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # 1. 删除 NOT NULL 约束
    cr.execute("ALTER TABLE approval_record ALTER COLUMN node_id DROP NOT NULL")
    cr.execute("ALTER TABLE approval_record ALTER COLUMN approver_id DROP NOT NULL")
    # 2. 改 FK 约束为 CASCADE（删除节点/审批人时自动删除）
    cr.execute("""
        ALTER TABLE approval_record
        DROP CONSTRAINT IF EXISTS approval_record_node_id_fkey
    """)
    cr.execute("""
        ALTER TABLE approval_record
        ADD CONSTRAINT approval_record_node_id_fkey
        FOREIGN KEY (node_id) REFERENCES approval_node(id) ON DELETE CASCADE
    """)
    cr.execute("""
        ALTER TABLE approval_record
        DROP CONSTRAINT IF EXISTS approval_record_approver_id_fkey
    """)
    cr.execute("""
        ALTER TABLE approval_record
        ADD CONSTRAINT approval_record_approver_id_fkey
        FOREIGN KEY (approver_id) REFERENCES res_users(id) ON DELETE CASCADE
    """)
    # 3. 加 snapshot 字段
    cr.execute("ALTER TABLE approval_record ADD COLUMN IF NOT EXISTS snapshot_node_name varchar")
    cr.execute("ALTER TABLE approval_record ADD COLUMN IF NOT EXISTS snapshot_approver_name varchar")
    # 4. 改其他引用 approval_node 的 FK 为 CASCADE
    for table, col in [
        ('approval_node_child_rel', 'child_id'),
        ('approval_node_child_rel', 'parent_id'),
        ('approval_node_user_rel', 'node_id'),
        ('approval_node_group_rel', 'node_id'),
        ('approval_node_handler_rel', 'node_id'),
        ('approval_node_handler_group_rel', 'node_id'),
        ('approval_node_cc_rel', 'node_id'),
        ('approval_node_cc_group_rel', 'node_id'),
        ('approval_node', 'default_child_id'),
        ('approval_condition_next_node_rel', 'node_id'),
        ('approval_condition_line', 'node_id'),
        ('approval_form_field', 'node_id'),
        ('approval_request_current_node_rel', 'node_id'),
        ('approval_request_completed_node_rel', 'node_id'),
        ('approval_cc', 'node_id'),
    ]:
        cr.execute(f"""
            DO $$
            DECLARE
                v_constraint text;
            BEGIN
                SELECT conname INTO v_constraint
                FROM pg_constraint
                WHERE conrelid = '{table}'::regclass
                  AND contype = 'f'
                  AND pg_get_constraintdef(oid) LIKE '%approval_node%'
                LIMIT 1;
                IF v_constraint IS NOT NULL THEN
                    EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT ' || v_constraint;
                    EXECUTE 'ALTER TABLE {table} ADD CONSTRAINT ' || v_constraint || ' FOREIGN KEY ({col}) REFERENCES approval_node(id) ON DELETE CASCADE';
                END IF;
            END $$;
        """)
