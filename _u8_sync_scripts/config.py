# -*- coding: utf-8 -*-
"""U8-Odoo 同步配置 — 多公司多账套"""

# U8 服务器基础连接
U8_SERVER_BASE = {
    "server": "172.15.102.245",
    "user": "odoo_sync",
    "password": "Odoo@Sync2026",
}

# Odoo 连接
ODOO_CONFIG = {
    "url": "http://localhost:8069",
    "db": "wb123data",
    "username": "postmaster@wanbang.xin",
    "password": "admin123",
}

# ==========================================
# 公司 → U8 账套映射
# ==========================================
# key: Odoo res.company id
# u8_db: U8 数据库名
# description: 公司描述（可选）
COMPANIES = {
    1: {"u8_db": "UFDATA_999_2025", "description": "四川万邦胜辉"},
    5: {"u8_db": "UFDATA_998_2025", "description": "宇能锂工"},
    6: {"u8_db": "UFDATA_998_2025", "description": "谷锂公司"},
    7: {"u8_db": "UFDATA_998_2025", "description": "中试公司"},
}

# 共享同一 U8 账套的公司（他们的 U8 数据在同库中，通过 cVenCode 等字段区分）
# 当前: 宇能锂工、谷锂公司、中试公司 → UFDATA_998_2025
#      万邦胜辉 → UFDATA_999_2025


def get_u8_config(odoo_company_id):
    """根据 Odoo 公司 ID 返回对应 U8 连接配置"""
    company = COMPANIES.get(odoo_company_id)
    if not company:
        return None
    cfg = dict(U8_SERVER_BASE)
    cfg["database"] = company["u8_db"]
    return cfg


def get_all_u8_configs():
    """返回所有唯一的 U8 连接配置（去重）"""
    seen = set()
    configs = []
    for company_id, info in COMPANIES.items():
        db = info["u8_db"]
        if db not in seen:
            seen.add(db)
            cfg = dict(U8_SERVER_BASE)
            cfg["database"] = db
            configs.append(cfg)
    return configs


def get_company_ids_for_u8_db(u8_db):
    """返回映射到指定 U8 数据库的所有 Odoo 公司 ID"""
    return [cid for cid, info in COMPANIES.items() if info["u8_db"] == u8_db]
