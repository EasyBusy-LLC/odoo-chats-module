# Easy Busy Chats – Architecture Notes

The addon bridges the React plugin (“easy_busy_chats” bundle) with Odoo CRM so that chats can create/view CRM artifacts and show contextual buttons only when relevant.

## Runtime flow

1. `static/src/core/web/chats_client_action.js` mounts the React widget. Instead of passing static actions it now sends a `callbacks` object produced by `getChatCallbacks`.
2. `static/src/core/web/chat_callbacks.js` exposes the `onOpenChat` callback. It sanitizes the React payload, calls `easy.busy.chats.on_open_chat` on the server, and feeds the server response into `getChatActions`.
3. `static/src/core/web/chat_actions.js` pulls every action factory from the registry (`easy_busy_chats.chat_actions`). A descriptor is a button (`callback`) or a select (`type: "select"`, `options`, `onSelect`), with optional `variant` and `htmlIcon` (see chats-front `app/src/plugin/CONFIG.md`). The default factory (`core.create_records`) produces:
   - `contact` (select, ghost): `view_contact` / `unlink_contact` when the chat is linked, `create_contact` / `link_contact` otherwise;
   - `deals` (select, outline): the linked contact's opportunities plus `manage_deals`;
   - `create_opportunity` (primary button).

   Every id, including select options, must be in the server's `allowed_action_ids`. Handlers open dialogs via the `action` service and call `payload.onComplete?.()` (through `triggerOnComplete`) so React refreshes the actions.

   `ChatsClientAction` keeps the instance returned by `window.renderChatsApp` and exposes it as `services.getChatsInstance()`. `create_opportunity` reads `chats.getSelectedMessages()`, normalizes the messages and passes them as `easy_busy_chat_selected_messages` in the wizard context; the wizard (`easy_busy_chats_crm`) renders them into its `description` (the deal's Notes) and, on confirm, copies their files into the opportunity (attachments + chatter note).

4. `models/easy_busy_chats.py:on_open_chat` decides which actions are allowed (`_collect_allowed_actions`):
   - if a `res.partner` is linked (an `easy.busy.chat.link` matching provider + contact id, or found by phone when the company enables it), we expose `view_contact` and `unlink_contact` (`unlink_chat_contact` removes the links); otherwise `create_contact` and `link_contact`;
   - the server state also carries `contact_partner_name` for the contact select;
   - whenever a partner exists, we upsert a record in `easy.busy.chat.link` for the “Chats” tab;
   - `easy_busy_chats_crm` adds `create_opportunity` and, when the contact has opportunities, `deals` with `deals` / `deals_count` in the server state.

5. The React hook `useChatActions` (`chats-front/app/src/features/active-chat/model/useChatActions.ts`) drives the UI:
   - calls `callbacks.onOpenChat` when the active chat changes or contact info is refetched;
   - forwards `provider`, `accountId`, and `onComplete` to the Odoo callbacks;
   - tracks per-button loading state and refreshes the action list once Odoo reports that a modal closed (so “Create Contact” immediately becomes “View Contact” after creation).

## Messenger tab / server data

- `models/easy_busy_chat_link.py` defines the link table. It stores provider/account/chat IDs, titles, last message metadata, and exposes two buttons:
  - `action_open_chat` ("Open Chat") returns the `easy_busy_chats.open_conversation` client action. It is a function action (`static/src/core/web/chat_conversation_dialog.js`) that opens `ChatConversationDialog` via the dialog service and mounts the plugin with `view: "conversation"` for that provider/account/chat, with the same `onOpenChat` actions as the chats page. It uses the dialog service, not a `target: "new"` action, because Odoo replaces an open action dialog with the next one, which would close the chat as soon as one of its actions opens a form. Links without `account_id` fall back to `action_open_all_chats`.
    The dialog header (no title: the plugin already shows the chat name) has "All Chats" and "Unlink". "Unlink" deletes this link record after confirmation, closes the dialog and runs `soft_reload` so the Chats tab refreshes.
  - `action_open_all_chats` ("All Chats" in the dialog header) returns `easy_busy_chats.action_chats` (the full chats page) with `selectedProvider`/`selectedChatId`/`selectedAccountId` in `params`, consumed by `ChatsClientAction.setup()` (the URL hash is the fallback).
- "New Chat" (Chats tab, always shown) calls `res.partner.action_easy_busy_new_chat`, which opens the same dialog without a chat selected and with `partner_id` + `contact_preset` (first/last name, E.164 phone from mobile/phone, using the contact's or the company's country). The dialog calls `chats.openCreateContactModal({ ...preset, type: "auto" })`; the plugin's `onChatCreated` callback then calls `easy.busy.chats.link_chat_to_partner` (skipped if the chat is already linked to another contact) and `chats.update()` selects the new chat. Closing the dialog with ×/Escape after a link was created soft-reloads the contact form.
- `static/src/core/web/chats_plugin.js` loads `plugin/loader.js` once and mounts the plugin (`EasyBusyChats.mount`, falling back to `renderChatsApp` for older builds).
- `models/res_partner.py` adds `easy_busy_chat_link_ids` and the computed count for the smart button/tab.
- `views/res_partner_views.xml` injects the “Chats” page on the contact form. The list hides the technical fields via CSS and renders “Open Chat” and “Unlink” (`action_unlink_from_contact`, with confirmation) for each row. The link form shows “Open Chat” too.
- "View Contact" opens the contact form in an extra-large dialog with `easy_busy_full_form_dialog` in the context: `static/src/core/web/full_form_dialog.js` then keeps the smart buttons and the chatter that Odoo hides in dialogs (the chatter is shown below the sheet, see `chats.css`).

## Opportunity wizard

- `easy_busy_chats_crm/models/easy_busy_create_opportunity.py` handles conversion/merge flows launched from the chat action:
  - `duplicated_lead_ids` is a user-editable many2many, filled by `_get_duplicate_opportunities` when partner/phone/email change;
  - `_action_merge` now respects the selection because the field is no longer computed;
  - `_action_convert` creates the lead/opportunity and links the partner/chat if needed.
- `easy_busy_chats_crm/views/easy_busy_create_opportunity_views.xml` defines the wizard layout (“Opportunities”, “Opportunity Details”, etc.); translations exist for all labels.

## Adding new chat actions

1. Register a factory in `static/src/core/web/chat_actions.js` (or extend `core.create_records`). Each descriptor needs `id`, `label`, optional `description`, and a `callback(payload)` that eventually calls `payload.onComplete?.()`.
2. Update `easy.busy.chats.on_open_chat` so it returns the new action id inside `allowed_action_ids` when applicable and provides any required metadata in `serverState`.
3. Add translations to `i18n/easy_busy_chats.pot` and propagate to the locale `.po` files.
4. If the action requires extra UI logic, adjust `useChatActions` (ordering, payload hints) or the React component accordingly.

## React integration summary

- `Plugin.tsx` receives callbacks from Odoo and stores them in Redux (`chatActionsSlice`).
- `useChatActions` orchestrates callback calls, loading state, and contact refetching.
- `ActiveChatHeader` renders the buttons returned by the hook; the buttons pass `onComplete` down to Odoo so state is refreshed immediately after a modal closes.

Keep future work callback-driven so the React widget only needs to render descriptors supplied by Odoo, avoiding hardcoded business logic on the frontend.
