/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

const FIELD_WIDGETS = {
    char: { tag: "input", type: "text" },
    text: { tag: "textarea" },
    integer: { tag: "input", type: "number", step: "1" },
    float: { tag: "input", type: "number", step: "any" },
    date: { tag: "input", type: "date" },
    datetime: { tag: "input", type: "datetime-local" },
    boolean: { tag: "input", type: "checkbox" },
    selection: { tag: "select" },
    many2one: { tag: "select" },
    html: { tag: "textarea" },
    user: { tag: "select" },
    company: { tag: "select" },
    image: { tag: "input", type: "file", accept: "image/*" },
    binary: { tag: "input", type: "file" },
};

export class DynamicFormBody extends Component {
    static template = "hc_dynamic_form.DynamicFormBody";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            fields: [],
            loading: false,
            error: null,
            templateId: null,
        });
        this._checkTemplateChange();
    }

    _getTemplateId() {
        const record = this.props.record;
        if (!record || !record.data) return null;
        const tid = record.data.template_id;
        if (!tid) return null;
        return Array.isArray(tid) ? tid[0] : tid;
    }

    async _checkTemplateChange() {
        const tid = this._getTemplateId();
        if (tid && tid !== this.state.templateId) {
            await this._loadFields(tid);
        } else if (!tid && this.state.templateId) {
            this.state.fields = [];
            this.state.templateId = null;
        }
    }

    async _loadFields(templateId) {
        this.state.templateId = templateId;
        this.state.loading = true;
        this.state.error = null;
        try {
            const fields = await this.orm.searchRead(
                "hc.form.template.field",
                [["template_id", "=", templateId]],
                ["name", "field_key", "field_type", "required",
                 "default_value", "placeholder", "help_text",
                 "selection_options", "related_model", "sequence"],
                { order: "sequence, id" }
            );

            for (const f of fields) {
                if (f.field_type === "selection" && f.selection_options) {
                    f._options = f.selection_options
                        .split("\n").map(s => s.trim()).filter(Boolean);
                } else if (f.field_type === "user") {
                    const users = await this.orm.searchRead(
                        "res.users", [["active", "=", true]],
                        ["name"], { limit: 200 }
                    );
                    f._options = users.map(u => [u.id, u.name]);
                } else if (f.field_type === "company") {
                    const companies = await this.orm.searchRead(
                        "res.company", [], ["name"], { limit: 100 }
                    );
                    f._options = companies.map(c => [c.id, c.name]);
                } else if (f.field_type === "many2one" && f.related_model) {
                    try {
                        const records = await this.orm.searchRead(
                            f.related_model, [], ["display_name"], { limit: 200 }
                        );
                        f._options = records.map(r => [r.id, r.display_name]);
                    } catch (e) {
                        f._options = [];
                    }
                }
            }

            this.state.fields = fields;
            this.state.loading = false;
        } catch (e) {
            this.state.error = e.message || String(e);
            this.state.loading = false;
        }
    }

    _getValue(fieldKey) {
        const record = this.props.record;
        if (!record || !record.data) return "";
        const raw = record.data[this.props.name];
        if (raw === null || raw === undefined) return "";
        if (typeof raw === "object" && !Array.isArray(raw)) {
            return raw[fieldKey] !== undefined ? raw[fieldKey] : "";
        }
        return "";
    }

    _onInput(fieldKey, value) {
        const record = this.props.record;
        if (!record) return;
        const raw = record.data[this.props.name] || {};
        const newData = { ...raw, [fieldKey]: value };
        // Use the model.data mutation API
        try {
            if (record.model && record.model.update) {
                record.model.update((data) => {
                    data[this.props.name] = newData;
                });
            } else {
                // Fallback: just notify
                this.props.value = newData;
            }
        } catch (e) {
            // Silently ignore for now
        }
    }

    _onFileChange(fieldKey, ev) {
        const file = ev.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => this._onInput(fieldKey, reader.result);
        reader.readAsDataURL(file);
    }

    // Override willUpdate to react to record changes
    willUpdate() {
        this._checkTemplateChange();
    }
}

export const dynamicFormBody = {
    component: DynamicFormBody,
    displayName: "Dynamic Form Body",
};

registry.category("fields").add("dynamic_form_body", dynamicFormBody);
