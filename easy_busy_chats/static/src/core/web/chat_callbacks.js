/** @odoo-module **/

import { getChatActions } from "./chat_actions";

const sanitizePayload = (payload) => {
    try {
        return JSON.parse(JSON.stringify(payload || {}));
    } catch (error) {
        console.warn("easy_busy_chats: failed to sanitize payload", error);
        return {};
    }
};

const filterActionsByIds = (actions, allowedIds) => {
    if (!Array.isArray(allowedIds)) {
        return actions;
    }
    if (!allowedIds.length) {
        return [];
    }
    const allowedSet = new Set(allowedIds);
    return actions.filter((action) => allowedSet.has(action.id));
};

const applyOverrides = (actions, overrides) => {
    if (!overrides) {
        return actions;
    }
    return actions.map((action) => ({
        ...action,
        ...(overrides[action.id] || {}),
    }));
};

export const getChatCallbacks = ({ services }) => {
    const { orm } = services;

    const buildActions = (payload, serverState) => {
        const baseActions = getChatActions({
            services,
            payload: Object.assign({}, payload, { serverState }),
        });
        const filtered = filterActionsByIds(baseActions, serverState?.allowed_action_ids);
        const overridden = applyOverrides(filtered, serverState?.action_overrides);
        return overridden.map((action) => ({
            ...action,
            serverState,
        }));
    };

    return {
        async onOpenChat(payload = {}) {
            let serverState;
            if (orm) {
                try {
                    serverState = await orm.call(
                        "easy.busy.chats",
                        "on_open_chat",
                        [sanitizePayload(payload)]
                    );
                } catch (error) {
                    console.error("easy_busy_chats: failed to process onOpenChat callback", error);
                }
            }
            return buildActions(payload, serverState);
        },
    };
};
