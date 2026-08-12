# Odoo 19 自研模块全集

> **项目**: 四川万邦胜辉 ERP 系统定制开发  
> **Odoo 版本**: 19.0 Community  
> **语言**: Python 3.12+ / JavaScript / XML  

## 模块清单 (15 个)

### 1. `approval_cn` - 中国式审批系统 ✔
符合中国企业管理特色的审批系统，支持自定义环节、条件分支、会签或签、抄送。  
**功能**: 
- 多级审批流程（会签/或签/顺签）
- 条件分支（按金额、部门等条件路由不同审批人）
- 审批记录追溯、撤销、驳回
- 已审批单据禁止删除保护

### 2. `approval_cn_purchase` - 审批-采购集成 ✔
将上述审批流程集成到采购订单中。采购订单确认后自动进入审批流程。

### 3. `approval_cn_external` - 审批外部集成 ✘
通过企业微信/钉钉消息卡片执行审批，结果回写 Odoo。  
**状态**: 未安装（待配置外部平台）

### 4. `hc_purchase_requisition` - 请购单管理 ✔
完整的请购申请 → 审批 → 生成采购订单流程。  
支持：需求部门、申请人、项目关联、多供应商询价、自动生成 PO 并带入项目。

### 5. `hc_purchase_quote_bid` - 询价比价 ✔
供应商报价管理，支持多供应商对比、替代品管理。  
**功能**: 报价录入、比较、选中、生成采购订单。

### 6. `hc_purchase_contract` - 采购合同管理 ✔
采购合同的生命周期管理，关联采购订单。

### 7. `hc_u8_connector` - 用友U8多账套连接器 ✔
模块化 U8 数据同步，支持多公司多账套独立配置。  
**功能**: 
- Odoo → U8 采购订单自动同步（每 5 分钟）
- U8 → Odoo 供应商每日同步
- 在 Odoo UI 中配置账套连接（无需改代码）
- 独立权限控制（U8管理员组）

### 8. `hc_project_cost` - 项目总花费 ✔
在项目列表和表单中显示总花费（采购金额 + 工时成本）。

### 9. `hc_dynamic_form` - 动态表单扩展 ✔
表单字段动态展示控制。

### 10. `project_budget_dashboard` - 项目预算看板 ✔
项目预算仪表盘视图。

### 11. `project_purchase_requisition` - 项目-请购单桥接 ✔
项目模块与请购单的集成桥接模块。

### 12. `l10n_cn_standard_latest` - 2026中国会计科目表 ✔
最新中国会计准则科目表，含科目组、税率模板、多级科目编码（金蝶风格）。  
来源: odooai.cn (LGPL-3)

### 13. `app_odoo_customize` - Odoo增强定制 ✘
Odoo 界面和功能增强。  
**状态**: 版本不兼容（v18→v19待升级）

### 14. `app_common` - 基础工具库 ✘
odooai.cn 模块的公共基础库。

### 15. `base_setup` - 基础设置扩展 ✔
Odoo 基础设置模块的定制扩展。

## 标准模块源码修改 (7 处)

| 文件 | 修改说明 |
|------|---------|
| `base/models/res_users.py` | `_get_company_ids()` 管理员返回全部活跃公司 |
| `base/models/ir_rule.py` | `_eval_context()` 管理员公司权限不受 web 上下文限制 |
| `web/models/models.py` | `onchange` 方法 API 参数兼容 (Odoo 19) |
| `project/models/project_project.py` | `milestone_count` 字段移除 groups 限制 |
| `project/models/project_role.py` | 添加 `company_id` 字段 |
| `approval_cn/models/approval_request.py` | 已审批单据禁止删除 |
| `tools/pdf/__init__.py` | `add_attachment()` 添加 `afrelationship` 参数 |

## U8 同步脚本

| 文件 | 说明 |
|------|------|
| `sync.py` | U8 PO/供应商/物料/库存同步主逻辑 |
| `config.py` | U8 服务器连接和公司-账套映射配置 |

## 部署说明

```bash
# 1. 复制模块到 Odoo addons 路径
cp -r * /opt/odoo/custom-addons/

# 2. 更新模块列表 + 安装
odoo -d <db_name> -c /etc/odoo/odoo.conf -u all --stop-after-init

# 3. 标准模块修改需手动应用到系统路径
# 见 _modified_standard/ 目录下的文件
```

## 授权

本项目各模块遵循其原始授权（LGPL-3 / AGPL-3）。