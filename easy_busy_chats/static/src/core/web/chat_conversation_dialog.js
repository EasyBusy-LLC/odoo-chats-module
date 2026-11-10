/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { getChatCallbacks } from "./chat_callbacks";
import { loadChatsPlugin, mountChats, toProviderSlug } from "./chats_plugin";

let nextTargetId = 1;

const isCompleteSelection = (selection) =>
    Boolean(selection.provider && selection.accountId && selection.chatId);

/**
 * Dialog showing a single chat with the plugin's `conversation` view:
 * header, messages and input only. Chat actions (contact, deals, create
 * opportunity) are the same as on the chats page.
 *
 * Two modes:
 * - existing chat: `provider` / `accountId` / `chatId` (+ `linkId`);
 * - new chat for an Odoo contact: `partnerId` + `contactPreset`. The plugin's
 *   create-contact dialog opens (type "auto"); once it has created the chat,
 *   the chat is linked to the partner and shown here.
 */
export class ChatConversationDialog extends Component {
    static template = "easy_busy_chats.ChatConversationDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        provider: { type: String, optional: true },
        chatId: { type: String, optional: true },
        accountId: { type: String, optional: true },
        linkId: { type: Number, optional: true },
        partnerId: { type: Number, optional: true },
        contactPreset: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.notification = useService("notification");
        this.targetId = `easy_busy_chat_conversation_${nextTargetId++}`;
        this.rootRef = useRef("root");
        this.state = useState({
            loading: true,
            error: null,
            selection: {
                provider: this.props.provider,
                accountId: this.props.accountId,
                chatId: this.props.chatId,
            },
            linkId: this.props.linkId,
        });

        // Plugin instance returned by mount (getSelectedMessages, unmount, …).
        this.chats = null;
        this.isDestroyed = false;
        // A chat was linked to the partner here: refresh the view behind when
        // the user closes the dialog (not when an action navigates away).
        this.linkCreated = false;
        this.reloadOnClose = false;
        this.callbacks = {
            ...getChatCallbacks({
                services: {
                    orm: this.orm,
                    action: this.actionService,
                    notification: this.notification,
                    getChatsInstance: () => this.chats,
                },
            }),
            onChatCreated: (payload) => this.onChatCreated(payload),
        };

        // Escape / × of the Odoo dialog: the user closes it.
        this.env.dialogData.dismiss = () => {
            this.reloadOnClose = this.linkCreated;
        };

        // Escape inside the plugin belongs to the plugin (its own dialogs,
        // menus, the message input); it must not close this dialog.
        this.onKeydown = (event) => {
            if (event.key === "Escape") {
                event.stopPropagation();
            }
        };

        onMounted(() => {
            this.rootRef.el?.addEventListener("keydown", this.onKeydown);
            this.mountPlugin();
        });

        onWillUnmount(() => {
            this.isDestroyed = true;
            this.rootRef.el?.removeEventListener("keydown", this.onKeydown);
            this.unmountPlugin();
            if (this.reloadOnClose) {
                // Unprotected service: this component is being destroyed.
                this.env.services.action.doAction("soft_reload");
            }
        });
    }

    get hasChat() {
        return isCompleteSelection(this.state.selection);
    }

    get canStartNewChat() {
        return Boolean(this.props.partnerId && this.props.contactPreset);
    }

    async mountPlugin() {
        try {
            const settings = await this.orm.call("easy.busy.chats", "get_settings");
            if (!settings) {
                throw new Error(_t("Failed to load settings"));
            }
            if (!settings.accessToken || !settings.companyId) {
                throw new Error(_t("Easy Busy Chats is not configured"));
            }
            await loadChatsPlugin(settings.pluginUrl);
            if (this.isDestroyed) {
                return;
            }
            const { selection } = this.state;
            const chats = await mountChats(this.targetId, {
                view: "conversation",
                companyId: settings.companyId,
                accessToken: settings.accessToken,
                lang: settings.lang,
                productType: settings.productType || "Chat",
                selectedProvider: selection.provider,
                selectedAccountId: selection.accountId,
                selectedChatId: selection.chatId,
                callbacks: this.callbacks,
                disableBrowserNotifications: true,
                changeTitleOnNewMessage: false,
            });
            this.chats = chats;
            if (this.isDestroyed) {
                this.unmountPlugin();
                return;
            }
            if (!this.hasChat && this.canStartNewChat) {
                this.openNewChat();
            }
        } catch (error) {
            console.error("easy_busy_chats: failed to open the conversation", error);
            if (!this.isDestroyed) {
                this.state.error = error?.message || _t("Failed to load the chat");
                this.notification.add(this.state.error, { type: "danger" });
            }
        } finally {
            if (!this.isDestroyed) {
                this.state.loading = false;
            }
        }
    }

    /** Plugin's create-contact dialog, prefilled with the Odoo contact. */
    openNewChat() {
        if (!this.chats || !this.canStartNewChat) {
            return;
        }
        this.chats.openCreateContactModal({ ...this.props.contactPreset, type: "auto" });
    }

    /** The plugin created a contact and its chat: link it, then show it. */
    async onChatCreated(payload = {}) {
        console.info("easy_busy_chats: onChatCreated", payload);
        if (this.isDestroyed) {
            return;
        }
        const { chat = {}, contact = {} } = payload;
        const chatId = chat.id ? String(chat.id) : undefined;
        // The payload carries the provider as slug, but fall back to the chat /
        // contact models, which may hold the enum value or name.
        const provider =
            toProviderSlug(payload.provider) ||
            toProviderSlug(chat.provider) ||
            toProviderSlug(contact.provider);
        const accountId = String(payload.accountId || chat.accountId || contact.accountId || "");
        if (!chatId || !provider || !accountId) {
            console.warn("easy_busy_chats: incomplete onChatCreated payload", {
                chatId,
                provider,
                accountId,
                payload,
            });
            this.notification.add(
                _t("The chat was created, but it can't be opened here. Find it in All Chats."),
                { type: "warning" }
            );
            return;
        }

        if (this.props.partnerId) {
            await this.linkCreatedChat({ ...payload, provider, accountId });
        }
        if (this.isDestroyed) {
            return;
        }
        this.state.selection = { provider, accountId, chatId };
        try {
            this.chats?.update({
                selectedProvider: provider,
                selectedAccountId: accountId,
                selectedChatId: chatId,
            });
        } catch (error) {
            console.error("easy_busy_chats: failed to show the new chat", error);
            this.notification.add(
                _t("The chat was created, but it can't be opened here. Find it in All Chats."),
                { type: "warning" }
            );
        }
    }

    async linkCreatedChat(payload) {
        try {
            const result = await this.orm.call("easy.busy.chats", "link_chat_to_partner", [
                this.props.partnerId,
                JSON.parse(JSON.stringify(payload)),
            ]);
            if (result?.status === "linked") {
                this.state.linkId = result.link_id;
                this.linkCreated = true;
                this.notification.add(
                    _t("Chat created and linked to %s.", result.partner_name),
                    { type: "success" }
                );
            } else if (result?.status === "linked_elsewhere") {
                this.notification.add(
                    _t("This chat is already linked to %s, the link was kept.", result.partner_name),
                    { type: "warning" }
                );
            } else {
                this.notification.add(_t("The chat was created but not linked to the contact."), {
                    type: "warning",
                });
            }
        } catch (error) {
            console.error("easy_busy_chats: failed to link the new chat", error);
            this.notification.add(_t("The chat was created but not linked to the contact."), {
                type: "danger",
            });
        }
    }

    /** × in the header. */
    closeDialog() {
        this.reloadOnClose = this.linkCreated;
        this.props.close();
    }

    /** Leave the dialog for the full chats page, with this chat selected. */
    async openAllChats() {
        const { selection, linkId } = this.state;
        let action;
        if (linkId) {
            action = await this.orm.call("easy.busy.chat.link", "action_open_all_chats", [[linkId]]);
        } else {
            action = {
                type: "ir.actions.client",
                tag: "easy_busy_chats.action_chats",
                params: this.hasChat
                    ? {
                          selectedProvider: selection.provider,
                          selectedChatId: selection.chatId,
                          selectedAccountId: selection.accountId,
                      }
                    : {},
            };
        }
        // Close first: it unmounts the conversation before the chats page
        // mounts its own plugin root.
        const actionService = this.actionService;
        this.reloadOnClose = false;
        this.props.close();
        await actionService.doAction(action);
    }

    /** Remove the link between this chat and the contact, then close. */
    unlinkChat() {
        const linkId = this.state.linkId;
        if (!linkId) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Unlink Contact"),
            body: _t("This chat will no longer be linked to the contact. The chat itself is not deleted."),
            confirmLabel: _t("Unlink"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.unlink("easy.busy.chat.link", [linkId]);
                this.notification.add(_t("Chat unlinked from the contact."), { type: "success" });
                const actionService = this.actionService;
                this.reloadOnClose = false;
                this.props.close();
                // Refresh the view behind (e.g. the contact's Messengers tab).
                await actionService.doAction("soft_reload");
            },
            cancel: () => {},
        });
    }

    unmountPlugin() {
        const chats = this.chats;
        this.chats = null;
        try {
            if (typeof chats?.unmount === "function") {
                chats.unmount();
            } else if (chats && window.unmountChatsApp) {
                window.unmountChatsApp(this.targetId);
            }
        } catch (error) {
            console.warn("easy_busy_chats: failed to unmount the conversation", error);
        }
    }
}

/**
 * Client action opening the conversation dialog over the current view.
 *
 * It is a function action on purpose: a `target: "new"` action dialog would
 * be replaced by the next `target: "new"` action, so the chat's own actions
 * (create opportunity, view contact, …) would close it. Dialog service
 * dialogs stack instead.
 *
 * params: `provider`, `chatid`, `accountid`, `link_id` for an existing chat;
 * `partner_id` and `contact_preset` to start a new chat for a contact.
 */
export function openChatConversation(env, action) {
    const params = action.params || {};
    const selection = {
        provider: params.provider ? String(params.provider) : undefined,
        chatId: params.chatid ? String(params.chatid) : undefined,
        accountId: params.accountid ? String(params.accountid) : undefined,
    };
    const partnerId = params.partner_id ? Number(params.partner_id) : undefined;
    if (!isCompleteSelection(selection) && !partnerId) {
        return;
    }
    env.services.dialog.add(ChatConversationDialog, {
        ...selection,
        linkId: params.link_id ? Number(params.link_id) : undefined,
        partnerId,
        contactPreset: params.contact_preset || undefined,
    });
}

registry.category("actions").add("easy_busy_chats.open_conversation", openChatConversation);
