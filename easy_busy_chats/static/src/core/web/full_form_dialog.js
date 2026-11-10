/** @odoo-module **/

import { useSubEnv } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormController } from "@web/views/form/form_controller";

/**
 * Full form in a dialog: with `easy_busy_full_form_dialog` in the action
 * context, a form opened in a dialog keeps what Odoo hides there, i.e. the
 * smart buttons (button box) and the chatter (shown below the sheet).
 * Used for the contact opened from the chats.
 */
export const FULL_FORM_DIALOG_KEY = "easy_busy_full_form_dialog";

const IN_DIALOG = "__comp__.env.inDialog";
const FULL_FORM = "__comp__.env.easyBusyFullFormDialog";

const fullFormCompilerPatch = {
    compile(key, params = {}) {
        const res = super.compile(key, params);

        // Chatter: mail hides it in dialogs with a condition starting with
        // `!env.inDialog` (Odoo 18+), or with CSS (Odoo 17, see chats.css).
        for (const chatter of res.querySelectorAll(".o-mail-Form-chatter[t-if]")) {
            const condition = chatter.getAttribute("t-if");
            if (condition.startsWith(`!${IN_DIALOG}`)) {
                chatter.setAttribute(
                    "t-if",
                    `(!${IN_DIALOG} or ${FULL_FORM})${condition.slice(IN_DIALOG.length + 1)}`
                );
            }
        }

        // Smart buttons: with a sheet, the button box is rendered in the
        // control panel, which dialogs don't have. Render it at the top of the
        // sheet instead, in full form dialogs only.
        const sheet = res.querySelector(".o_form_sheet");
        const arch = this.templates[key];
        const buttonBoxArch = sheet && arch?.querySelector?.("div[name='button_box']:not(field div)");
        if (buttonBoxArch) {
            const buttonBox = this.compileNode(buttonBoxArch.cloneNode(true), params);
            if (buttonBox && typeof buttonBox !== "string" && buttonBox.nodeName === "ButtonBox") {
                buttonBox.setAttribute("t-if", `${IN_DIALOG} and ${FULL_FORM}`);
                sheet.prepend(buttonBox);
            }
        }
        return res;
    },
};

// Applied when the services start, i.e. after every module-level patch: mail
// patches `FormCompiler.compile` too and its result must be adjusted here
// (this module can't depend on mail, so the asset order isn't guaranteed).
let compilerPatched = false;
registry.category("services").add("easy_busy_chats.full_form_dialog", {
    start() {
        if (!compilerPatched) {
            compilerPatched = true;
            patch(FormCompiler.prototype, fullFormCompilerPatch);
        }
    },
});

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.env.inDialog && this.props.context?.[FULL_FORM_DIALOG_KEY]) {
            useSubEnv({ easyBusyFullFormDialog: true });
        }
    },

    get className() {
        const result = super.className;
        if (this.env.inDialog && this.props.context?.[FULL_FORM_DIALOG_KEY]) {
            result.o_easy_busy_full_form_dialog = true;
        }
        return result;
    },
});
