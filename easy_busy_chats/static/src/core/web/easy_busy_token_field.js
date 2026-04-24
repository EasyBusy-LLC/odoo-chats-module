/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useInputField } from "@web/views/fields/input_field_hook";
import { onMounted, useRef } from "@odoo/owl";

const SELECTION_FIELD = "easy_busy_company_id";

export class EasyBusyTokenField extends CharField {
    setup() {
        this.input = useRef("input");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this._lastCommittedToken = this.props.record.data[this.props.name] || "";
        this._refreshRequestId = 0;
        useInputField({
            getValue: () => this.props.record.data[this.props.name] || "",
            parse: (v) => this.parse(v),
            shouldSave: () => false,
        });
        onMounted(() => {
            const inputEl = this.input.el;
            if (!inputEl) {
                return;
            }
            inputEl.addEventListener("change", () => {
                setTimeout(() => {
                    void this._commitTokenChange(inputEl.value || "");
                }, 0);
            });
            inputEl.addEventListener("paste", () => {
                setTimeout(() => {
                    void this._commitTokenChange(inputEl.value || "");
                }, 0);
            });
        });
    }

    async _commitTokenChange(rawValue) {
        const token = this.parse(rawValue || "");
        if (token === this._lastCommittedToken) {
            return;
        }
        this._lastCommittedToken = token;
        await this._refreshCompanies(this.props.record, token);
    }

    async _refreshCompanies(record, token) {
        const requestId = ++this._refreshRequestId;
        try {
            if (record.fields[SELECTION_FIELD]) {
                record.fields[SELECTION_FIELD].selection = [];
            }
            await record.update(
                {
                    [this.props.name]: token || false,
                    [SELECTION_FIELD]: false,
                },
                { save: true },
            );
            const fieldsInfo = await this.orm.call(
                record.resModel,
                "fields_get",
                [[SELECTION_FIELD], ["selection"]],
                { context: record.context },
            );
            const refreshedSelection = fieldsInfo?.[SELECTION_FIELD]?.selection;
            if (
                requestId === this._refreshRequestId &&
                refreshedSelection &&
                record.fields[SELECTION_FIELD]
            ) {
                record.fields[SELECTION_FIELD].selection = refreshedSelection;
            }
            if (requestId === this._refreshRequestId) {
                await record.load();
            }
        } catch (error) {
            this.notification.add(
                _t("Could not refresh Easy Busy companies."),
                { type: "warning" },
            );
        }
    }
}

export const easyBusyTokenField = {
    ...charField,
    component: EasyBusyTokenField,
};

registry.category("fields").add("easy_busy_token", easyBusyTokenField);
