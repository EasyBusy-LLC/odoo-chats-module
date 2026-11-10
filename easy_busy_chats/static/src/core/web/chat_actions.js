/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { formatDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

/**
 * Registry namespace for chat actions exposed to the React widget.
 * Additional modules can register factories that receive the available
 * services and return action descriptors to display inside the chat panel.
 *
 * A descriptor is either a button (`callback`) or a select
 * (`type: "select"`, non-empty `options`, `onSelect`).
 */
export const CHAT_ACTIONS_CATEGORY = "easy_busy_chats.chat_actions";

const chatActionsRegistry = registry.category(CHAT_ACTIONS_CATEGORY);

const isValidDescriptor = (descriptor) => {
    if (!descriptor?.id) {
        return false;
    }
    if (descriptor.type === "select") {
        return (
            typeof descriptor.onSelect === "function" &&
            Array.isArray(descriptor.options) &&
            descriptor.options.length > 0
        );
    }
    return typeof descriptor.callback === "function";
};

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
            if (isValidDescriptor(descriptor)) {
                actions.push(descriptor);
            }
        }
    }

    return actions;
};

// Lucide icons (https://lucide.dev), rendered by the chats plugin via `htmlIcon`.
const svgIcon = (paths) =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

export const CHAT_ACTION_ICONS = {
    user: svgIcon('<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
    userPlus: svgIcon(
        '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="19" x2="19" y1="8" y2="14"/><line x1="22" x2="16" y1="11" y2="11"/>'
    ),
    x: svgIcon('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
    link: svgIcon(
        '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'
    ),
    briefcase: svgIcon(
        '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>'
    ),
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
    const resolvedProvider = provider || chat?.provider || contact?.provider;
    const resolvedAccountId = accountId || chat?.accountId || contact?.accountId;
    if (!chatId || !resolvedProvider) {
        return undefined;
    }
    const contactId = contact?.id ?? chat?.contactId ?? chatId;
    return sanitizeContext({
        provider: resolvedProvider,
        account_id: resolvedAccountId,
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
 * Messages the user selected in the open chat (chats-front message models,
 * oldest first). Read from the plugin instance; the action payload carries the
 * same list and is used when the instance is not available (older plugin).
 */
const getSelectedMessages = (services, payload = {}) => {
    const chats = services?.getChatsInstance?.();
    if (typeof chats?.getSelectedMessages === "function") {
        try {
            return chats.getSelectedMessages() || [];
        } catch (error) {
            console.warn("easy_busy_chats: failed to read selected messages", error);
        }
    }
    return Array.isArray(payload.selectedMessages) ? payload.selectedMessages : [];
};

const formatMessageDate = (timestamp) => {
    if (!timestamp) {
        return "";
    }
    // Plugin timestamps are milliseconds; accept seconds too.
    const millis = timestamp < 1e12 ? timestamp * 1000 : timestamp;
    const date = DateTime.fromMillis(millis);
    return date.isValid ? formatDateTime(date) : "";
};

const isWebUrl = (url) => typeof url === "string" && /^https?:\/\//i.test(url);

/**
 * Reduces a chats-front message model to what the deal note renders, so the
 * wizard context stays small. Rendering and escaping happen server side.
 */
const normalizeMessage = (message = {}) => {
    const body = message.body || {};
    const attachments = [];
    const addFiles = (files, kind, fallbackName) => {
        for (const file of files || []) {
            attachments.push({
                kind,
                name: file.fileName || fallbackName,
                mimetype: file.mimeType || undefined,
                url: isWebUrl(file.fileUrl) ? file.fileUrl : undefined,
            });
        }
    };
    addFiles(body.photos, "image", _t("Photo"));
    addFiles(body.videos, "video", _t("Video"));
    addFiles(body.audios, "audio", _t("Audio"));
    addFiles(body.documents, "document", _t("Document"));
    if (body.sticker) {
        attachments.push({ name: body.sticker.emoji || _t("Sticker") });
    }
    if (body.call) {
        attachments.push({ name: _t("Call") });
    }

    const from = message.from || {};
    const sender = message.sender || {};
    const author = message.isIncome
        ? from.fullName || from.username
        : sender.fullName || sender.username || from.fullName || from.username;

    return sanitizeContext({
        id: message.messageId,
        author: author || undefined,
        is_income: Boolean(message.isIncome),
        date: formatMessageDate(message.timestamp),
        text: body.text || body.caption || "",
        attachments: attachments.length ? attachments : undefined,
    });
};

/**
 * Default actions available out of the box.
 * Can be extended/removed by overriding this registry entry.
 *
 * Every id (top-level action or select option) must be listed in the server's
 * `allowed_action_ids` to be shown.
 */
chatActionsRegistry.add("core.create_records", ({ services, payload: factoryPayload = {} }) => {
    const actionService = services?.action;
    const orm = services?.orm;
    if (!actionService) {
        return [];
    }
    const serverState = factoryPayload.serverState || {};
    const allowedIds = Array.isArray(serverState.allowed_action_ids)
        ? new Set(serverState.allowed_action_ids)
        : null;
    const isAllowed = (id) => !allowedIds || allowedIds.has(id);

    const triggerOnComplete = (onComplete) => {
        if (typeof onComplete !== "function") {
            return;
        }
        Promise.resolve(onComplete()).catch((error) => {
            console.error("easy_busy_chats: onComplete callback failed", error);
        });
    };

    const doDialogAction = (action, onComplete) =>
        actionService.doAction(action, {
            onClose: () => {
                triggerOnComplete(onComplete);
            },
        });

    const resolveState = (runtimeState) => runtimeState || serverState;

    const openCreateOpportunity = (payload = {}) => {
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState,
            onComplete,
            provider = payload.chat?.provider || payload.contact?.provider,
            accountId,
        } = payload;
        const effectiveState = resolveState(runtimeState);
        const contactPhoneNumber = contact.phoneNumber || chat.phoneNumber;
        const contactEmail =
            contact.emailAddress || contact.email || chat.email || contact.mail;
        const chatLinkPayload = buildChatLinkPayload({
            chat,
            contact,
            provider,
            accountId,
        });
        const selectedMessages = getSelectedMessages(services, payload).map(normalizeMessage);
        const defaultCustomerAction = effectiveState?.contact_partner_id ? "exist" : "create";
        const baseContext = {
            default_name: chat.title,
            // The selected messages become the deal note (rendered server side).
            default_description: selectedMessages.length
                ? undefined
                : chat.description || chat.lastMessageText,
            default_phone: contactPhoneNumber,
            default_email_from: contactEmail,
            default_contact_name: contact.userName || chat.contactName || chat.title,
            default_customer_action: defaultCustomerAction,
            default_partner_id: effectiveState?.contact_partner_id,
            easy_busy_chat_selected_messages: selectedMessages.length
                ? selectedMessages
                : undefined,
        };
        const context = sanitizeContext(Object.assign(baseContext, extraContext));
        applyChatLinkPayload(context, chatLinkPayload);

        return doDialogAction(
            {
                type: "ir.actions.act_window",
                name: _t("Create Opportunity"),
                res_model: "easy.busy.create.opportunity",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context,
            },
            onComplete
        );
    };

    const openCreateContact = (payload = {}) => {
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState,
            onComplete,
            provider = payload.chat?.provider || payload.contact?.provider,
            accountId,
        } = payload;
        const effectiveState = resolveState(runtimeState);
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
            default_parent_id: effectiveState?.contact_partner_id,
        };
        applyChatLinkPayload(baseContext, chatLinkPayload);

        const context = sanitizeContext(Object.assign(baseContext, extraContext));

        return doDialogAction(
            {
                type: "ir.actions.act_window",
                name: _t("Create Contact"),
                res_model: "res.partner",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context,
            },
            onComplete
        );
    };

    const viewExistingContact = (payload = {}) => {
        const { serverState: runtimeState, onComplete } = payload;
        const partnerId = resolveState(runtimeState)?.contact_partner_id;
        if (!partnerId) {
            triggerOnComplete(onComplete);
            return Promise.resolve();
        }

        return doDialogAction(
            {
                type: "ir.actions.act_window",
                name: _t("View Contact"),
                res_model: "res.partner",
                res_id: partnerId,
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                // Same as the full page: smart buttons and chatter.
                context: { dialog_size: "extra-large", easy_busy_full_form_dialog: true },
            },
            onComplete
        );
    };

    const openLinkContact = (payload = {}) => {
        const {
            chat = {},
            contact = {},
            extraContext = {},
            serverState: runtimeState,
            onComplete,
            provider = payload.chat?.provider || payload.contact?.provider,
            accountId,
        } = payload;
        const effectiveState = resolveState(runtimeState);
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

        return doDialogAction(
            {
                type: "ir.actions.act_window",
                name: _t("Link Existing Contact"),
                res_model: "easy.busy.link.contact",
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
                context,
            },
            onComplete
        );
    };

    const notify = (message, type = "success") => services?.notification?.add(message, { type });

    const unlinkContact = async (payload = {}) => {
        const { chat = {}, contact, provider, accountId, onComplete } = payload;
        try {
            if (orm) {
                await orm.call("easy.busy.chats", "unlink_chat_contact", [
                    JSON.parse(JSON.stringify({ chat, contact, provider, accountId })),
                ]);
                notify(_t("Chat unlinked from the contact."));
            }
        } catch (error) {
            console.error("easy_busy_chats: failed to unlink the contact", error);
            notify(_t("Failed to unlink the contact."), "danger");
        } finally {
            triggerOnComplete(onComplete);
        }
    };

    const openDeal = (dealId, { onComplete } = {}) =>
        doDialogAction(
            {
                type: "ir.actions.act_window",
                name: _t("Opportunity"),
                res_model: "crm.lead",
                res_id: dealId,
                view_mode: "form",
                views: [[false, "form"]],
                target: "new",
            },
            onComplete
        );

    const manageDeals = async (payload = {}) => {
        const { serverState: runtimeState, onComplete } = payload;
        const partnerId = resolveState(runtimeState)?.contact_partner_id;
        try {
            if (partnerId) {
                await actionService.doAction({
                    type: "ir.actions.act_window",
                    name: _t("Opportunities"),
                    res_model: "crm.lead",
                    view_mode: "kanban,list,form",
                    views: [
                        [false, "kanban"],
                        [false, "list"],
                        [false, "form"],
                    ],
                    domain: [
                        ["type", "=", "opportunity"],
                        ["partner_id", "child_of", partnerId],
                    ],
                    context: {
                        default_type: "opportunity",
                        default_partner_id: partnerId,
                    },
                    target: "current",
                });
            }
        } finally {
            triggerOnComplete(onComplete);
        }
    };

    const actions = [];

    // Contact: one select grouping every contact action.
    if (isAllowed("contact")) {
        const partnerName = serverState.contact_partner_name;
        const contactHandlers = {
            view_contact: viewExistingContact,
            unlink_contact: unlinkContact,
            create_contact: openCreateContact,
            link_contact: openLinkContact,
        };
        const contactOptions = [
            { value: "view_contact", label: _t("View Contact"), htmlIcon: CHAT_ACTION_ICONS.user },
            { value: "unlink_contact", label: _t("Unlink Contact"), htmlIcon: CHAT_ACTION_ICONS.x },
            {
                value: "create_contact",
                label: _t("Create Contact"),
                htmlIcon: CHAT_ACTION_ICONS.userPlus,
            },
            {
                value: "link_contact",
                label: _t("Link Existing Contact"),
                htmlIcon: CHAT_ACTION_ICONS.link,
            },
        ].filter((option) => isAllowed(option.value));
        const contactLabel = partnerName || _t("Contact");

        actions.push({
            id: "contact",
            type: "select",
            label: contactLabel,
            placeholder: contactLabel,
            description: partnerName ? _t("Linked contact") : _t("No contact linked to this chat"),
            variant: "ghost",
            htmlIcon: CHAT_ACTION_ICONS.user,
            // No value: the select works as a menu and always shows the placeholder.
            options: contactOptions,
            onSelect: (payload) => contactHandlers[payload.value]?.(payload),
        });
    }

    // Deals: the contact's opportunities plus a link to the full list.
    const deals = Array.isArray(serverState.deals) ? serverState.deals : [];
    if (isAllowed("deals") && deals.length) {
        const dealsCount = serverState.deals_count || deals.length;
        actions.push({
            id: "deals",
            type: "select",
            label: _t("Deals (%s)", dealsCount),
            placeholder: _t("Deals (%s)", dealsCount),
            variant: "outline",
            htmlIcon: CHAT_ACTION_ICONS.briefcase,
            options: [
                ...deals.map((deal) => ({
                    value: `deal:${deal.id}`,
                    label: deal.name,
                    description: `#${deal.id}`,
                })),
                {
                    value: "manage_deals",
                    label: _t("Manage Deals"),
                    htmlIcon: CHAT_ACTION_ICONS.link,
                },
            ],
            onSelect: (payload) => {
                if (payload.value === "manage_deals") {
                    return manageDeals(payload);
                }
                const dealId = Number(String(payload.value).split(":")[1]);
                if (!dealId) {
                    triggerOnComplete(payload.onComplete);
                    return undefined;
                }
                return openDeal(dealId, payload);
            },
        });
    }

    if (isAllowed("create_opportunity")) {
        actions.push({
            id: "create_opportunity",
            label: _t("Create Opportunity"),
            description: _t("Create a deal; selected messages are added to its notes."),
            variant: "default",
            htmlIcon: CHAT_ACTION_ICONS.briefcase,
            callback: openCreateOpportunity,
        });
    }

    return actions;
});
