/** @odoo-module **/

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/**
 * hc.form.instance 自定义字段 widget
 * 显示为多行 textarea，直接编辑 JSON
 */
export class FormDataTextField extends Component {
    static template = "hc_dynamic_form.FormDataTextField";
    static props = {
        ...standardFieldProps,
        record: { type: Object, optional: true },
    };

    setup() {
        this.text = useState({ value: this.props.value || "{}" });
    }

    onInput(ev) {
        this.text.value = ev.target.value;
        this.props.update(this.text.value);
    }
}

registry.category("fields").add("form_data_text", {
    component: FormDataTextField,
    supportedTypes: ["text", "char"],
});

export class FormDataHtmlField extends Component {
    static template = "hc_dynamic_form.FormDataHtmlField";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.fields = useState({ value: [] });
        this.options = useState({ value: { users: [], companies: [], departments: [] } });
        this.loaded = useState({ value: false });
        this.error = useState({ value: null });

        onWillStart(async () => {
            try {
                await this.loadFields();
            } catch (e) {
                console.error("hc_dynamic_form: fallback to textarea", e);
                this.error.value = String(e.message || e);
                this.loaded.value = true;
            }
        });

        onWillUpdateProps(async (nextProps) => {
            const oldTpl = this.props.record?.data?.template_id;
            const newTpl = nextProps.record?.data?.template_id;
            if (oldTpl !== newTpl && newTpl) {
                try {
                    this.loaded.value = false;
                    await this.loadFields();
                } catch (e) {
                    this.error.value = String(e);
                    this.loaded.value = true;
                }
            }
        });
    }

    async loadFields() {
        const record = this.props.record;
        if (!record) return;
        let templateId = record.data?.template_id;
        if (Array.isArray(templateId)) templateId = templateId[0];
        if (templateId && typeof templateId === 'object') templateId = templateId.id;
        if (!templateId) {
            this.loaded.value = true;
            this.error.value = "未找到模板ID，请先选择模板";
            return;
        }
        try {
            // 加载模板字段
            const fields = await this.orm.searchRead(
                "hc.form.template.field",
                [["template_id", "=", templateId]],
                ["name", "field_key", "field_type", "required", "default_value", "selection_options", "help_text", "sequence"],
                { orderBy: [{ name: "sequence", asc: true }] }
            );
            this.fields.value = fields;
            // 加载用户/公司/部门选项
            const [users, companies, departments] = await Promise.all([
                this.orm.searchRead("res.users", [], ["id", "name"]),
                this.orm.searchRead("res.company", [], ["id", "name"]),
                this.orm.searchRead("hr.department", [], ["id", "name"]).catch(() => []),
            ]);
            this.options.value = { users, companies, departments };
        } catch (e) {
            console.error("hc_dynamic_form: loadFields failed", e);
        }
        this.loaded.value = true;
    }

    onChange() {
        const data = {};
        const root = this.__owl__.htmlParent || document;
        root.querySelectorAll('.hc_df_row').forEach((row) => {
            const key = row.dataset.key;
            const el = row.querySelector('input, select, textarea');
            if (!el || !key) return;
            if (row.dataset.type === 'boolean') data[key] = el.checked;
            else if (el.type === 'file') data[key] = el.files?.[0]?.name || null;
            else data[key] = el.value || null;
        });
        this.text.value = JSON.stringify(data, null, 2);
        this.props.update(data);
    }

    getValue(key) {
        return (this.props.value || {})[key] || '';
    }
}

registry.category("fields").add("form_data_dynamic", {
    component: FormDataHtmlField,
    supportedTypes: ["json"],
});
