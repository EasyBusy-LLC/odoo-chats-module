/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

/**
 * Registry namespace for chat actions exposed to the React widget.
 * Additional modules can register factories that receive the available
 * services and return action descriptors to display inside the chat panel.
 */
export const CHAT_ACTIONS_CATEGORY = "easy_busy_chats.chat_actions";

const chatActionsRegistry = registry.category(CHAT_ACTIONS_CATEGORY);

/**
 * Utility to collect chat actions from every registered factory.
 *
 * @param {Object} env
 * @param {Object} env.services
 * @param {Object} env.payload optional event-specific payload
 * @returns {Array<Object>}
 */
export const getChatActions = ({ services, payload } = { services: {} }) => {
    const actions = [];

    for (const [, factory] of chatActionsRegistry.getEntries()) {
        if (typeof factory !== "function") {
            continue;
        }
        const producedActions = factory({ services, payload }) || [];
        for (const descriptor of producedActions) {
            const { id, callback } = descriptor || {};
            if (!id || typeof callback !== "function") {
                continue;
            }
            actions.push(descriptor);
        }
    }

    return actions;
};

const sanitizeContext = (context) => {
    const sanitized = {};
    for (const [key, value] of Object.entries(context || {})) {
        if (value !== undefined) {
            sanitized[key] = value;
        }
    }
    return sanitized;
};

const buildChatLinkPayload = ({ chat = {}, contact = {}, provider, accountId } = {}) => {
    const chatId = chat?.id; 
    if (!chatId || !provider) {
        return undefined;
    } 
    const contactId = contact?.id ?? chat?.contactId ?? chatId;
    return sanitizeContext({
        provider: provider, 
        account_id: accountId,
        chat_id: chatId,
        chat_type: chat?.chatType,
        chat_title: chat?.title,
        contact_user_name: contact?.userName ?? chat?.userName,
        contact_id: contactId,
    });
};

const applyChatLinkPayload = (context, payload) => {
    if (payload) {
        context.easy_busy_chat_link_payload = payload;
    }
};

/**
 * Default actions available out of the box.
 * Can be extended/removed by overriding this registry entry.
 */
chatActionsRegistry.add("core.create_records", ({ services, payload: factoryPayload = {} }) => {
    const actionService = services?.action;
    if (!actionService) {
        return [];
    }
    const serverState = factoryPayload.serverState || {};

    const triggerOnComplete = (onComplete) => {
        if (typeof onComplete !== "function") {
            return;
        }
        Promise.resolve(onComplete()).catch((error) => {
            console.error("easy_busy_chats: onComplete callback failed", error);
        });
    };

    const openCreateOpportunity = (payload = {}) => {
       
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState = serverState,
            onComplete,
            provider = payload.chat.provider,
            accountId,
        } = payload;
        const effectiveState = runtimeState || serverState;
        const contactPhoneNumber = contact.phoneNumber || chat.phoneNumber;
        const contactEmail =
            contact.emailAddress || contact.email || chat.email || contact.mail;
        const chatLinkPayload = buildChatLinkPayload({
            chat,
            contact,
            provider,
            accountId,
        });
        const defaultCustomerAction = effectiveState?.contact_partner_id ? "exist" : "create";
        const baseContext = {
            default_name: chat.title,
            default_description: chat.description || chat.lastMessageText,
            default_phone: contactPhoneNumber,
            default_email_from: contactEmail,
            default_contact_name: contact.userName || chat.contactName || chat.title,
            default_customer_action: defaultCustomerAction,
            default_partner_id: effectiveState?.contact_partner_id,
        };
        const context = sanitizeContext(Object.assign(baseContext, extraContext));
        applyChatLinkPayload(context, chatLinkPayload);

        return actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Create Opportunity"),
            res_model: "easy.busy.create.opportunity",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context,
        }, {
            onClose: () => {
                triggerOnComplete(onComplete);
            },
        });
    };

    const openCreateContact = (payload = {}) => {
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState = serverState,
            onComplete,
            provider = payload.chat.provider,
            accountId,
        } = payload;
        const effectiveState = runtimeState || serverState;
        const contactPhoneNumber = contact.phoneNumber || chat.phoneNumber;
        const chatLinkPayload = buildChatLinkPayload({
            chat,
            contact,
            provider,
            accountId,
        });

        const baseContext = {
            default_name: chat.title,
            default_phone: contactPhoneNumber,
            default_parent_id: effectiveState?.contact_partner_id
        };
        applyChatLinkPayload(baseContext, chatLinkPayload);

        const context = sanitizeContext(
            Object.assign(baseContext, extraContext)
        );

        return actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Create Contact"),
            res_model: "res.partner",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context,
        }, {
            onClose: () => {
                triggerOnComplete(onComplete);
            },
        });
    };

    const viewExistingContact = (payload = {}) => {
        const {
            serverState: runtimeState = serverState,
            onComplete,
        } = payload;
        const effectiveState = runtimeState || serverState;
        const partnerId = effectiveState?.contact_partner_id;
        if (!partnerId) {
            return Promise.resolve();
        }

        return actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("View Contact"),
            res_model: "res.partner",
            res_id: partnerId,
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
        }, {
            onClose: () => {
                triggerOnComplete(onComplete);
            },
        });
    };

    const openLinkContact = (payload = {}) => {
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState = serverState,
            onComplete,
            provider = payload.chat.provider,
            accountId,
        } = payload;
        const effectiveState = runtimeState || serverState;
        const chatLinkPayload = buildChatLinkPayload({
            chat,
            contact,
            provider,
            accountId,
        });
        const context = sanitizeContext(
            Object.assign(
                {
                    default_partner_id: effectiveState?.contact_partner_id,
                },
                extraContext
            )
        );
        applyChatLinkPayload(context, chatLinkPayload);

        let completed = false;
        const completeOnce = () => {
            if (completed) {
                return;
            }
            completed = true;
            triggerOnComplete(onComplete);
        };

        return actionService.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("Link Existing Contact"),
                res_model: "easy.busy.link.contact",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context,
            },
            {
                onClose: () => {
                    completeOnce();
                },
            }
        );
    };

    return [
        {
            id: "create_opportunity",
            label: _t("Create Opportunity"),
            description: _t("Open a new CRM opportunity form."),
            callback: openCreateOpportunity
        },
        {
            id: "create_contact",
            label: _t("Create Contact"),
            description: _t("Open a dialog to create a new contact."),
            callback: openCreateContact
        },
        {
            id: "link_contact",
            label: _t("Link Existing Contact"),
            description: _t("Associate this chat with an existing contact."),
            callback: openLinkContact
        },
        {
            id: "view_contact",
            label: _t("View Contact"),
            description: _t("Open the existing contact form."),
            callback: viewExistingContact
        },
    ];
});
