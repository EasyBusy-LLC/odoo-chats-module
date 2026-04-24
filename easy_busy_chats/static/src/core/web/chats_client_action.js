/** @odoo-module **/

import { Component, onWillStart, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { getChatCallbacks } from "./chat_callbacks";

export class ChatsClientAction extends Component {

    static props = ["*"];
    static template = "easy_busy_chats.ChatsClientAction";

    setup() {
        const orm = useService("orm");
        const actionService = useService("action");
        const services = {
            orm,
            action: actionService,
        };
        const chatCallbacks = getChatCallbacks({ services });

        const hash = window.location.hash.slice(1);
        // Parse provider and chatid from URL hash fragment
        const getUrlParams = () => {

            const params = new URLSearchParams(hash);
            return {
                selectedAccountId: params.get("accountid"),
                selectedProvider: params.get("provider"),
                selectedChatId: params.get("chatid"),
            };
        };

        const openUserSettings = async () => {
            const action = await orm.call(
                "res.users",
                "action_open_easy_busy_chats_settings",
                [[user.userId]]
            );
            return actionService.doAction(action, {
                onClose: () => actionService.doAction("reload"),
            });
        };

        const showSettingsMessage = (title, description) => {
            const messageContainer = document.getElementById("chat_container_holder_text");
            if (!messageContainer) {
                return;
            }

            const wrapper = document.createElement("div");
            wrapper.className = "o_easy_busy_chats_message";

            const titleElement = document.createElement("p");
            titleElement.className = "o_easy_busy_chats_message_title";
            titleElement.textContent = title;

            const descriptionElement = document.createElement("p");
            descriptionElement.className = "o_easy_busy_chats_message_description";
            descriptionElement.textContent = description;

            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-primary";
            button.textContent = _t("Open Settings");
            button.addEventListener("click", () => {
                void openUserSettings();
            });

            wrapper.append(titleElement, descriptionElement, button);
            messageContainer.replaceChildren(wrapper);
            messageContainer.style.display = "block";
        };

        const processSettingsSetup = (chatSettings) => {
            //document.querySelector('.o_content').classList.add('chats-active');
            if (!chatSettings) {
                showSettingsMessage(
                    _t("Failed to load settings"),
                    _t("Easy Busy Chats settings are unavailable right now.")
                );
                return false;
            }
            if (!chatSettings.accessToken) {
                showSettingsMessage(
                    _t("Easy Busy Chats is not configured"),
                    _t("Add your Easy Busy access token in Preferences to continue.")
                );
                return false;
            }
            if (!chatSettings.companyId) {
                showSettingsMessage(
                    _t("Easy Busy company is not connected"),
                    _t("Open Preferences and load your Easy Busy companies to continue.")
                );
                return false;
            }
            return true;
        };

        const initializeChat = (chatSettings) => {
            const { selectedProvider, selectedChatId, selectedAccountId } = getUrlParams();
            const interval = setInterval(() => {
                if (window.renderChatsApp) {
                    clearInterval(interval);

                    try {
                        window.localStorage.setItem('token', chatSettings.accessToken);
                    } catch (error) {
                        console.log(error);
                    }

                    window.renderChatsApp('chat_container_holder', {
                        companyId: chatSettings.companyId,
                        accessToken: chatSettings.accessToken,
                        lang: chatSettings.lang,
                        productType: 'Chat',
                        selectedProvider: selectedProvider,
                        selectedChatId: selectedChatId,
                        selectedAccountId: selectedAccountId,
                        callbacks: chatCallbacks,
                    });

                    const messageContainer = document.getElementById("chat_container_holder_text");
                    if (messageContainer) {
                        messageContainer.replaceChildren();
                        messageContainer.style.display = "none";
                    }
                }
            }, 100);
        };

        onWillStart(async () => {
            const chatSettings = await orm.call("easy.busy.chats", "get_settings");

            if (!window.renderChatsApp) {
                const waitInitInterval = setInterval(() => {
                    const container = document.getElementById('chat_container');
                    if (!container) return;

                    clearInterval(waitInitInterval);

                    if (!processSettingsSetup(chatSettings)) return;

                    const script = document.createElement('script');
                    script.src = chatSettings.pluginUrl;
                    script.onload = () => initializeChat(chatSettings);

                    document.head.appendChild(script);
                }, 200);
            } else {
                if (processSettingsSetup(chatSettings)) {
                    initializeChat(chatSettings);
                }
            }
        });

        onWillDestroy(() => {
            if (window.unmountChatsApp) {
                window.unmountChatsApp('chat_container_holder');
            }
            //document.querySelector('.o_content').classList.remove('chats-active');
        });
    }
}

registry.category("actions").add("easy_busy_chats.action_chats", ChatsClientAction);
