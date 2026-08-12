# -*- coding: utf-8 -*-
"""U8 账套配置模型"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class U8AccountConfig(models.Model):
    _name = 'hc.u8.account'
    _description = 'U8 账套配置'
    _order = 'sequence, id'
    _sql_constraints = [
        ('unique_u8_company',
         'UNIQUE(company_id)',
         '一个 Odoo 公司只能绑定一个 U8 账套'),
    ]

    name = fields.Char('账套名称', compute='_compute_name', store=True)
    sequence = fields.Integer('排序', default=10)

    # --- U8 连接 ---
    server = fields.Char('SQL Server 地址', required=True, default='172.15.102.245')
    database = fields.Char('U8 数据库名', required=True,
        help='如 UFDATA_999_2025')
    db_user = fields.Char('数据库用户', required=True, default='odoo_sync')
    db_password = fields.Char('数据库密码', required=True, default='Odoo@Sync2026')

    # --- Odoo 关联 ---
    company_id = fields.Many2one(
        'res.company', '对应 Odoo 公司',
        required=True, ondelete='cascade',
        help='采购订单按 company_id 路由到对应 U8 账套',
    )
    active = fields.Boolean('启用', default=True)

    # --- 同步状态 ---
    last_sync = fields.Datetime('上次同步时间', readonly=True)
    last_sync_status = fields.Selection([
        ('success', '成功'),
        ('warning', '部分成功'),
        ('error', '失败'),
    ], '同步状态', readonly=True)
    last_sync_message = fields.Text('同步消息', readonly=True)
    sync_count_po = fields.Integer('同步PO数', readonly=True)

    @api.depends('company_id.name', 'database')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.company_id.name} → {rec.database}" if rec.company_id else rec.database

    def _get_connection(self):
        """获取 pymssql 连接"""
        import pymssql
        self.ensure_one()
        try:
            return pymssql.connect(
                server=self.server,
                database=self.database,
                user=self.db_user,
                password=self.db_password,
                timeout=15,
            )
        except Exception as e:
            raise UserError(_('连接 U8 数据库失败 [%s]: %s') % (self.database, e))

    def _update_status(self, status, message, count=0):
        self.write({
            'last_sync': fields.Datetime.now(),
            'last_sync_status': status,
            'last_sync_message': message,
            'sync_count_po': count,
        })

    # ============================================================
    #  同步入口
    # ============================================================

    def action_sync_all(self):
        """【按钮】手动全量同步"""
        result = self._sync_purchases()
        self._sync_vendors()
        self._sync_products()
        self._sync_stock()

    def _sync_cron(self):
        """【Cron 调用】所有启用的账套自动同步 PO"""
        for account in self.search([('active', '=', True)]):
            try:
                account._sync_purchases()
            except Exception as e:
                account._update_status('error', str(e))
    # ============================================================
    #  PO 同步（Odoo → U8）
    # ============================================================

    def _sync_purchases(self):
        """Odoo purchase.order -> U8 PO_Pomain + PO_Podetails
        增强：智能物料编码映射、供应商自动创建、失败告警"""
        self.ensure_one()
        PO = self.env['purchase.order'].sudo()
        orders = PO.search([
            ('state', 'in', ['purchase', 'done']),
            ('company_id', '=', self.company_id.id),
        ])
        if not orders:
            self._update_status('success', '无待同步单据', 0)
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'U8同步', 'message': '无待同步单据', 'type': 'info'}}
        conn = self._get_connection()
        cur = conn.cursor()
        synced = 0
        errors = []
        try:
            for o in orders:
                odoo_name = o.name
                cur.execute("SELECT COUNT(*) FROM PO_Pomain WHERE cPOID = %s", (odoo_name,))
                if cur.fetchone()[0] > 0:
                    continue
                ven_code = o.partner_id.ref if o.partner_id.ref else None
                if not ven_code:
                    ven_code = o.partner_id.name[:20].replace(' ', '').replace('(', '').replace(')', '')
                    cur.execute(
                        "IF NOT EXISTS (SELECT 1 FROM Vendor WHERE cVenCode=%s) INSERT INTO Vendor (cVenCode,cVenName) VALUES (%s,%s)",
                        (ven_code, ven_code, o.partner_id.name[:50]))
                    conn.commit()
                cur.execute(
                    "INSERT INTO PO_Pomain (POID,cPOID,dPODate,cVenCode,cDepCode,cPersonCode,cPTCode,cSCCode,cPayCode,cexch_name,cMaker,cState,cPeriod) "
                    "VALUES ((SELECT ISNULL(MAX(POID),0)+1 FROM PO_Pomain),%s,%s,%s,'1','01','01','01','01',%s,%s,%s,'odoo_sync','0',DATEPART(yy,GETDATE()))",
                    (odoo_name, o.date_order, ven_code, '人民币'))
                for line in o.order_line:
                    code = self._get_u8_inv_code(cur, line)
                    cname = (line.product_id.name or '')[:60]
                    cur.execute(
                        "INSERT INTO PO_Podetails (ID,cPOID,cInvCode,cItemName,iQuantity,iUnitPrice,POID) "
                        "VALUES ((SELECT ISNULL(MAX(ID),0)+1 FROM PO_Podetails),%s,%s,%s,%s,%s,(SELECT POID FROM PO_Pomain WHERE cPOID=%s))",
                        (odoo_name, code, cname, line.product_qty, line.price_unit, odoo_name))
                synced += 1
            conn.commit()
            msg = '同步 %d 张PO' % synced
            if errors:
                msg += '；%d 笔跳过(%s)' % (len(errors), '; '.join(errors[:3]))
            self._update_status('success' if not errors else 'warning', msg, synced)
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'U8同步', 'message': msg, 'type': 'success' if not errors else 'warning'}}
        except Exception as e:
            conn.rollback()
            err_msg = str(e)[:200]
            self._update_status('error', err_msg)
            self._send_sync_alert('error', err_msg)
            raise
        finally:
            conn.close()

    def _get_u8_inv_code(self, cur, line):
        product = line.product_id
        if not product:
            return 'UNKNOWN'
        code = product.default_code
        if code:
            code = code.strip()[:20]
            cur.execute("SELECT COUNT(*) FROM Inventory WHERE cInvCode=%s", (code,))
            if cur.fetchone()[0] > 0:
                return code
        if product.barcode:
            code = product.barcode.strip()[:20]
            cur.execute("SELECT COUNT(*) FROM Inventory WHERE cInvCode=%s", (code,))
            if cur.fetchone()[0] > 0:
                return code
        code = (product.default_code or 'ODOO%d' % product.id)[:20]
        name = (product.name or 'Product')[:60]
        unit = (product.uom_id.name or '个')[:10]
        try:
            cur.execute(
                "IF NOT EXISTS (SELECT 1 FROM Inventory WHERE cInvCode=%s) INSERT INTO Inventory (cInvCode,cInvName,cInvStd,cInvCCode) VALUES (%s,%s,%s,%s)",
                (code, code, name, unit, '01'))
        except:
            pass
        return code

    def _send_sync_alert(self, status, message):
        try:
            body = 'U8同步告警 [%s]\n状态: %s\n详情: %s' % (self.database, status, message)
            admin_group = self.env.ref('base.group_erp_manager', raise_if_not_found=False)
            if admin_group:
                for user in admin_group.users:
                    self.env['mail.message'].sudo().create({
                        'subject': 'U8同步失败 - %s' % self.database,
                        'body': body,
                        'model': 'hc.u8.account',
                        'res_id': self.id,
                        'message_type': 'notification',
                        'partner_ids': [(4, user.partner_id.id)],
                    })
        except Exception:
            pass



    # ============================================================
    #  供应商同步（U8 → Odoo）
    # ============================================================

    def _sync_vendors(self):
        """U8 Vendor → Odoo res.partner"""
        self.ensure_one()
        conn = self._get_connection()
        cur = conn.cursor()
        added = skipped = 0
        try:
            cur.execute("SELECT cVenCode, cVenName FROM Vendor")
            for code, name in cur.fetchall():
                if not code or not code.strip():
                    continue
                code = code.strip()
                exists = self.env['res.partner'].sudo().search_count([('ref', '=', code)])
                if not exists:
                    self.env['res.partner'].sudo().create({
                        'name': (name or '').strip(),
                        'ref': code,
                        'company_type': 'company',
                        'is_company': True,
                        'supplier_rank': 1,
                        'company_id': self.company_id.id,
                    })
                    added += 1
                else:
                    skipped += 1
            conn.commit()
            self._log(f'供应商: 新增 {added}, 已存在 {skipped}')
        finally:
            conn.close()

    # ============================================================
    #  物料同步（U8 → Odoo）
    # ============================================================

    def _sync_products(self):
        """U8 Inventory → Odoo product.template"""
        self.ensure_one()
        conn = self._get_connection()
        cur = conn.cursor()
        added = skipped = 0
        try:
            cur.execute("SELECT cInvCode, cInvName, cInvStd FROM Inventory")
            for code, name, spec in cur.fetchall():
                if not code or not code.strip():
                    continue
                code = code.strip()
                exists = self.env['product.product'].sudo().search_count(
                    [('default_code', '=', code)])
                if not exists:
                    spec_str = f" {spec.strip()}" if spec and spec.strip() else ""
                    self.env['product.template'].sudo().create({
                        'name': f"{(name or '').strip()}{spec_str}",
                        'type': 'consu',
                        'default_code': code,
                        'company_id': self.company_id.id,
                    })
                    added += 1
                else:
                    skipped += 1
            conn.commit()
            self._log(f'物料: 新增 {added}, 已存在 {skipped}')
        finally:
            conn.close()

    # ============================================================
    #  库存同步（U8 → Odoo）
    # ============================================================

    def _sync_stock(self):
        """U8 CurrentStock → Odoo stock.quant"""
        self.ensure_one()
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT cInvCode, ISNULL(iQuantity,0) FROM CurrentStock")
            rows = cur.fetchall()
            if not rows:
                self._log('库存: CurrentStock 表为空，跳过')
                return

            warehouse = self.env['stock.warehouse'].sudo().search(
                [('company_id', '=', self.company_id.id)], limit=1)
            if not warehouse:
                self._log('库存: 未找到仓库')
                return

            updated = 0
            for code, qty in rows:
                if not code or not code.strip():
                    continue
                prod = self.env['product.product'].sudo().search(
                    [('default_code', '=', code.strip())], limit=1)
                if not prod:
                    continue
                quant = self.env['stock.quant'].sudo().search([
                    ('product_id', '=', prod.id),
                    ('location_id', '=', warehouse.lot_stock_id.id),
                ], limit=1)
                if quant:
                    quant.sudo().inventory_quantity = qty
                else:
                    self.env['stock.quant'].sudo().create({
                        'product_id': prod.id,
                        'location_id': warehouse.lot_stock_id.id,
                        'inventory_quantity': qty,
                    })
                updated += 1
            conn.commit()
            self._log(f'库存: 更新 {updated} 项')
        finally:
            conn.close()

    def _log(self, message):
        """内部日志"""
        self.ensure_one()
        last_msg = (self.last_sync_message or '') + '\n' + message
        self.write({
            'last_sync_message': last_msg[-2000:],
            'last_sync_status': 'success',
        })
