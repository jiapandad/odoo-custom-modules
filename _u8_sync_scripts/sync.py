# -*- coding: utf-8 -*-
"""U8-Odoo 数据同步 — 多公司多账套版"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pymssql, xmlrpc.client, psycopg2
from config import ODOO_CONFIG, COMPANIES, get_u8_config, get_all_u8_configs, get_company_ids_for_u8_db

common = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/common")
uid = common.authenticate(ODOO_CONFIG['db'], ODOO_CONFIG['username'],
                          ODOO_CONFIG['password'], {})
models = xmlrpc.client.ServerProxy(f"{ODOO_CONFIG['url']}/xmlrpc/2/object")


def _get_u8_conn(odoo_company_id):
    """获取指定 Odoo 公司对应的 U8 连接"""
    cfg = get_u8_config(odoo_company_id)
    if not cfg:
        return None
    return pymssql.connect(**cfg)


def sync_u8_vendors():
    """U8 Vendor → Odoo res.partner"""
    for u8_cfg in get_all_u8_configs():
        u8_db = u8_cfg["database"]
        company_ids = get_company_ids_for_u8_db(u8_db)
        conn = pymssql.connect(**u8_cfg)
        cur = conn.cursor()
        cur.execute("SELECT cVenCode, cVenName FROM Vendor")
        rows = cur.fetchall()
        added = 0
        for code, name in rows:
            if not code or not code.strip():
                continue
            exists = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'res.partner', 'search_count', [[('ref', '=', code.strip())]])
            if not exists:
                partner_id = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'res.partner', 'create', [{
                        'name': name.strip(), 'ref': code.strip(),
                        'company_type': 'company', 'is_company': True,
                        'supplier_rank': 1,
                        'company_id': company_ids[0] if len(company_ids) == 1 else False,
                    }])
                added += 1
                # 如果多个公司共享同一 U8 账套，为该合作伙伴添加多公司访问
                if len(company_ids) > 1:
                    models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                        'res.partner', 'write', [[partner_id], {
                            'company_ids': [(6, 0, company_ids)],
                        }])
        print(f"    {u8_db}: {added} new / {len(rows)} total")
        conn.close()


def sync_u8_products():
    """U8 Inventory → Odoo product.template"""
    for u8_cfg in get_all_u8_configs():
        u8_db = u8_cfg["database"]
        company_ids = get_company_ids_for_u8_db(u8_db)
        conn = pymssql.connect(**u8_cfg)
        cur = conn.cursor()
        cur.execute("SELECT cInvCode, cInvName, cInvStd FROM Inventory")
        rows = cur.fetchall()
        added = 0
        for code, name, spec in rows:
            if not code or not code.strip():
                continue
            exists = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'search_count', [[('default_code', '=', code.strip())]])
            if not exists:
                spec_str = f" {spec.strip()}" if spec and spec.strip() else ""
                prod_id = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'product.template', 'create', [{
                        'name': f"{name.strip()}{spec_str}",
                        'type': 'consu',
                        'default_code': code.strip(),
                        'company_id': company_ids[0] if len(company_ids) == 1 else False,
                    }])
                added += 1
        print(f"    {u8_db}: {added} new / {len(rows)} total")
        conn.close()


def sync_odoo_purchases():
    """Odoo purchase.order → U8 PO_Pomain + PO_Podetails（按公司路由）"""
    all_orders = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
        'purchase.order', 'search_read',
        [[('state', 'in', ['purchase', 'done']),
          ('company_id', 'in', list(COMPANIES.keys()))],
         ['name', 'date_order', 'partner_id', 'order_line', 'company_id']])

    # 按公司分组
    by_company = {}
    for o in all_orders:
        cid = o['company_id'][0] if o.get('company_id') else 1
        by_company.setdefault(cid, []).append(o)

    total_synced = 0
    for company_id, orders in by_company.items():
        conn = _get_u8_conn(company_id)
        if not conn:
            print(f"    Company {company_id}: no U8 mapping, skipped {len(orders)} POs")
            continue

        cur = conn.cursor()
        synced = 0
        for o in orders:
            odoo_name = o['name']
            cur.execute("SELECT COUNT(*) FROM PO_Pomain WHERE cPOID = %s", (odoo_name,))
            if cur.fetchone()[0] > 0:
                continue

            vendor = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'res.partner', 'search_read', [[('id', '=', o['partner_id'][0])], ['ref']])
            ven_code = vendor[0]['ref'] if vendor and vendor[0].get('ref') else None
            if not ven_code:
                continue

            cur.execute(
                "INSERT INTO PO_Pomain (POID,cPOID,dPODate,cVenCode,cDepCode,cMaker,cState,cPeriod) "
                "VALUES ((SELECT ISNULL(MAX(POID),0)+1 FROM PO_Pomain),%s,%s,%s,'01','odoo_sync','0',DATEPART(yy,GETDATE()))",
                (odoo_name, o['date_order'], ven_code))

            lines = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'purchase.order.line', 'search_read', [[('order_id', '=', o['id'])],
                ['product_id', 'price_unit', 'product_qty']])
            for l in lines:
                prod = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'product.product', 'search_read', [[('id', '=', l['product_id'][0])],
                    ['default_code']])
                inv = prod[0]['default_code'] if prod else 'UNKNOWN'
                cur.execute(
                    "INSERT INTO PO_Podetails (ID,cPOID,cInvCode,iQuantity,iUnitPrice,POID) "
                    "VALUES ((SELECT ISNULL(MAX(ID),0)+1 FROM PO_Podetails),%s,%s,%s,%s,"
                    "(SELECT POID FROM PO_Pomain WHERE cPOID=%s))",
                    (odoo_name, inv, l['product_qty'], l['price_unit'], odoo_name))
            synced += 1
        conn.commit()
        conn.close()
        comp_info = COMPANIES.get(company_id, {})
        u8_db = comp_info.get("u8_db", "?")
        print(f"    {comp_info.get('description', company_id)} → {u8_db}: {synced} POs synced")
        total_synced += synced
    return total_synced


def sync_u8_stock():
    """U8 CurrentStock → Odoo stock.quant"""
    for u8_cfg in get_all_u8_configs():
        u8_db = u8_cfg["database"]
        company_ids = get_company_ids_for_u8_db(u8_db)

        conn = pymssql.connect(**u8_cfg)
        cur = conn.cursor()
        try:
            cur.execute("SELECT cInvCode, cWhCode, iQuantity FROM CurrentStock")
            rows = cur.fetchall()
        except Exception:
            print(f"    {u8_db}: CurrentStock not found, skipped")
            conn.close()
            continue

        loc = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
            'stock.location', 'search_read',
            [[('usage', '=', 'internal')], ['id']], {'limit': 1})
        location_id = loc[0]['id'] if loc else 8

        updated = 0
        for inv_code, wh_code, qty in rows:
            if not inv_code or not inv_code.strip():
                continue
            prod = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'product.product', 'search_read',
                [[('default_code', '=', inv_code.strip())], ['id']])
            if not prod:
                continue
            pid = prod[0]['id']
            quants = models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                'stock.quant', 'search_read',
                [[('product_id', '=', pid), ('location_id', '=', location_id)],
                 ['id', 'quantity']])
            if quants:
                models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'stock.quant', 'write', [[quants[0]['id']], {'inventory_quantity': float(qty)}])
                models.execute_kw(ODOO_CONFIG['db'], uid, ODOO_CONFIG['password'],
                    'stock.quant', 'action_apply_inventory', [quants[0]['id']])
            updated += 1
        print(f"    {u8_db}: {updated} stock items synced")
        conn.close()


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    print("=== U8 Multi-Company Sync ===")
    if mode in ('all', 'vendor'):
        print("--- Vendors ---")
        sync_u8_vendors()
    if mode in ('all', 'product'):
        print("--- Products ---")
        sync_u8_products()
    if mode in ('all', 'po'):
        print("--- Purchase Orders ---")
        total = sync_odoo_purchases()
        print(f"  Total: {total} POs synced")
    if mode in ('all', 'stock'):
        print("--- Stock ---")
        sync_u8_stock()
    print("=== Done ===")
