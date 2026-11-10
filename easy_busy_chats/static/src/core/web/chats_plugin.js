/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

/**
 * Loading and mounting of the EasyBusy Chats plugin (chats-front).
 *
 * `pluginUrl` points to `plugin/loader.js`, which defines
 * `window.EasyBusyChats.mount` as soon as it runs; the promise it returns
 * resolves once the full bundle has loaded and mounted. Older builds only
 * expose `window.renderChatsApp` once the bundle is loaded.
 */

let loadingPromise = null;

const isPluginAvailable = () =>
    typeof window.EasyBusyChats?.mount === "function" ||
    typeof window.renderChatsApp === "function";

export function loadChatsPlugin(pluginUrl) {
    if (isPluginAvailable()) {
        return Promise.resolve();
    }
    if (!loadingPromise) {
        loadingPromise = new Promise((resolve, reject) => {
            let script = [...document.scripts].find((s) => s.src === pluginUrl);
            if (!script) {
                script = document.createElement("script");
                script.src = pluginUrl;
                document.head.appendChild(script);
            }
            script.addEventListener("load", () => resolve());
            script.addEventListener("error", () => {
                loadingPromise = null;
                script.remove();
                reject(new Error(_t("Failed to load the chats plugin")));
            });
        });
    }
    return loadingPromise;
}

const waitFor = (predicate, { interval = 100, timeout = 30000 } = {}) =>
    new Promise((resolve, reject) => {
        const startedAt = Date.now();
        const check = () => {
            if (predicate()) {
                resolve();
            } else if (Date.now() - startedAt > timeout) {
                reject(new Error(_t("Failed to load the chats plugin")));
            } else {
                setTimeout(check, interval);
            }
        };
        check();
    });

/**
 * Mounts the plugin on `target` (element id) and resolves with the plugin
 * instance (`update`, `unmount`, `getSelectedMessages`, …).
 */
export async function mountChats(target, options) {
    if (typeof window.EasyBusyChats?.mount === "function") {
        return window.EasyBusyChats.mount({ ...options, target });
    }
    await waitFor(() => typeof window.renderChatsApp === "function");
    return window.renderChatsApp(target, options);
}

// ChatProviderSource enum of chats-front → URL slug used by Odoo links.
const PROVIDER_SLUGS = {
    1: "telegrambot",
    2: "instagram",
    3: "telegram",
    4: "facebook",
    5: "viberbot",
    6: "whatsapp",
    7: "webchat",
    8: "echatviber",
    9: "whatsapppersonal",
    10: "viberbusiness",
    11: "viberpersonal",
    13: "signal",
};
const KNOWN_SLUGS = new Set(Object.values(PROVIDER_SLUGS));

/**
 * Normalizes a provider given as enum value (`9`, `"9"`), enum name
 * (`"WhatsAppPersonal"`) or slug (`"whatsapppersonal"`) to the slug.
 */
export function toProviderSlug(provider) {
    if (provider === undefined || provider === null || provider === "") {
        return undefined;
    }
    const value = String(provider).trim();
    if (/^\d+$/.test(value)) {
        return PROVIDER_SLUGS[Number(value)];
    }
    const slug = value.toLowerCase();
    return KNOWN_SLUGS.has(slug) ? slug : undefined;
}
