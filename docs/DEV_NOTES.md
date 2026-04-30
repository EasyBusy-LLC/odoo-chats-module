# Easy Busy Chats – Architecture Notes

The addon bridges the React plugin (“easy_busy_chat” bundle) with Odoo CRM so that chats can create/view CRM artifacts and show contextual buttons only when relevant.

## Runtime flow

1. `static/src/core/web/chats_client_action.js` mounts the React widget. Instead of passing static actions it now sends a `callbacks` object produced by `getChatCallbacks`.
2. `static/src/core/web/chat_callbacks.js` exposes the `onOpenChat` callback. It sanitizes the React payload, calls `easy.busy.chats.on_open_chat` on the server, and feeds the server response into `getChatActions`.
3. `static/src/core/web/chat_actions.js` pulls every action factory from the registry (`easy_busy_chat.chat_actions`). The default factory (`core.create_records`) registers three actions:
   - `create_opportunity`
   - `create_contact`
   - `view_contact`

   Each action:
   - opens the corresponding server action via the `action` service;
   - injects chat/contact metadata (IDs, titles, photos) into the action context;
   - calls `payload.onComplete?.()` through the helper `triggerOnComplete` so React can refresh state once the modal closes.

4. `models/easy_busy_chat.py:on_open_chat` decides which actions are allowed:
   - only chats with `chatType == "User"` get CRM buttons;
   - if a `res.partner` already exists (matched by `eb_chat_external_id` / `eb_external_contact_id`), we expose `view_contact`; otherwise we expose `create_contact`;
   - whenever a partner exists, we upsert a record in `easy.busy.chat.link` for the “Messengers” tab.

5. The React hook `useChatActions` (`chats-front/app/src/features/active-chat/model/useChatActions.ts`) drives the UI:
   - calls `callbacks.onOpenChat` when the active chat changes or contact info is refetched;
   - forwards `provider`, `accountId`, and `onComplete` to the Odoo callbacks;
   - tracks per-button loading state and refreshes the action list once Odoo reports that a modal closed (so “Create Contact” immediately becomes “View Contact” after creation).

## Messenger tab / server data

- `models/easy_busy_chat_link.py` defines the link table. It stores provider/account/chat IDs, titles, last message metadata, and exposes `action_open_chat` (an `ir.actions.act_url` hitting `/redirect/chats`).
- `models/res_partner.py` adds `easy_busy_chat_link_ids` and the computed count for the smart button/tab.
- `views/res_partner_views.xml` injects the “Messengers” page on the contact form. The tree view hides the technical fields via CSS and renders an “Open Chat” button for each row. The form view shows the same button so the detail popup stays consistent.

## Opportunity wizard

- `models/easy_busy_create_opportunity.py` handles conversion/merge flows launched from the chat action:
  - `duplicated_lead_ids` is a user-editable many2many, filled by `_get_duplicate_opportunities` when partner/phone/email change;
  - `_action_merge` now respects the selection because the field is no longer computed;
  - `_action_convert` creates the lead/opportunity and links the partner/chat if needed.
- `views/easy_busy_create_opportunity_views.xml` defines the wizard layout (“Opportunities”, “Opportunity Details”, etc.); translations exist for all labels.

## Adding new chat actions

1. Register a factory in `static/src/core/web/chat_actions.js` (or extend `core.create_records`). Each descriptor needs `id`, `label`, optional `description`, and a `callback(payload)` that eventually calls `payload.onComplete?.()`.
2. Update `easy.busy.chats.on_open_chat` so it returns the new action id inside `allowed_action_ids` when applicable and provides any required metadata in `serverState`.
3. Add translations to `i18n/easy_busy_chat.pot` and propagate to the locale `.po` files.
4. If the action requires extra UI logic, adjust `useChatActions` (ordering, payload hints) or the React component accordingly.

## React integration summary

- `Plugin.tsx` receives callbacks from Odoo and stores them in Redux (`chatActionsSlice`).
- `useChatActions` orchestrates callback calls, loading state, and contact refetching.
- `ActiveChatHeader` renders the buttons returned by the hook; the buttons pass `onComplete` down to Odoo so state is refreshed immediately after a modal closes.

Keep future work callback-driven so the React widget only needs to render descriptors supplied by Odoo, avoiding hardcoded business logic on the frontend.
