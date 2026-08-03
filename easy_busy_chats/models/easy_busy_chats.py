import logging

from psycopg2 import IntegrityError

from odoo import api, models

_logger = logging.getLogger(__name__)

EASY_BUSY_PLUGIN_URL = 'https://chats.easy-busy.cloud/plugin/loader.js'

# Mirrors the client-side precedence used in
# static/src/core/web/chat_actions.js (contact.phoneNumber || chat.phoneNumber),
# with defensive spellings so a provider variation does not silently disable
# the automatic linking.
PHONE_PAYLOAD_KEYS = ("phoneNumber", "phone_number", "phone", "contactPhone", "number")


class EasyBusyChats(models.Model):
    _name = 'easy.busy.chats'
    _description = 'Easy Busy Chats'

    @api.model
    def get_settings(self):
        if not self.env.user.has_group('easy_busy_chats.group_easy_busy_chats_user'):
            return {}

        user = self.env.user
        return {
            "accessToken": user.sudo().easy_busy_access_token or "",
            "companyId": user.sudo().easy_busy_company_id or "",
            "pluginUrl": EASY_BUSY_PLUGIN_URL,
            "lang": self.env.context.get("lang", "en_US").replace("_", "-"),
        }

    @api.model
    def on_open_chat(self, payload):
        if not self.env.user.has_group('easy_busy_chats.group_easy_busy_chats_user'):
            return {"allowed_action_ids": []}

        payload = payload or {}
        chat_data = payload.get("chat") or {}
        contact_data = payload.get("contact") or {}

        provider = (payload.get("provider", None) or chat_data.get("provider", "")).lower()
        account_id = payload.get("accountId", None) or chat_data.get("accountId")
        contact_id = (
            contact_data.get("id")
            or chat_data.get("contactId")
            or chat_data.get("id")
        )

        domain = [
            ("provider", "=", provider),
            ("contact_id", "=", contact_id),
        ]
        links = self.env["easy.busy.chat.link"].search(domain, limit=1)
        partner_record = links[:1].partner_id
        auto_linked = False

        if not partner_record:
            # No link yet: optionally recognise the contact by its phone number
            partner_record = self._easy_busy_resolve_unlinked_partner(
                provider, contact_id, chat_data, contact_data,
            )
            auto_linked = bool(partner_record)

        partner_exists = bool(partner_record)

        allowed_action_ids = self._collect_allowed_actions(chat_data, partner_exists)

        if partner_exists:
            extra = {
                "provider": provider,
                "accountId": account_id,
            }
            try:
                with self.env.cr.savepoint():
                    self.env["easy.busy.chat.link"].sudo().upsert_from_payload(
                        partner_record,
                        chat_data,
                        contact_data,
                        extra,
                    )
            except IntegrityError:
                # unique(provider, chat_id, contact_id): the very same link was
                # created concurrently, or upsert_from_payload derived a
                # slightly different contact_id than we did. Not an error here.
                _logger.info(
                    "easy_busy_chats: chat link %s/%s already exists, skipping upsert",
                    provider, contact_id,
                )

        return {
            "allowed_action_ids": allowed_action_ids,
            "contact_exists": partner_exists,
            "contact_partner_id": partner_record.id if partner_record else False,
            "contact_auto_linked": auto_linked,
        }

    def _collect_allowed_actions(self, chat_data, partner_exists):
        allowed_action_ids = []
        if partner_exists:
            allowed_action_ids.append("view_contact")
        else:
            allowed_action_ids.extend(["create_contact", "link_contact"])
        return allowed_action_ids

    def _easy_busy_resolve_unlinked_partner(self, provider, contact_id, chat_data, contact_data):
        """Contact an unlinked chat should be attached to, if any.

        Returns an empty res.partner recordset unless the company setting
        ``easy_busy_auto_link_partner_by_phone`` is enabled and exactly one
        existing contact owns the phone number reported by the messenger.
        """
        partner_model = self.env["res.partner"]
        company = self.env.company
        if not company.sudo().easy_busy_auto_link_partner_by_phone:
            return partner_model
        if not contact_id:
            # without a contact_id we cannot build a stable chat link key
            return partner_model

        number = self._easy_busy_extract_phone(chat_data, contact_data)
        if not number:
            # group chats, channels, or providers that hide the number
            return partner_model

        partner = partner_model._easy_busy_find_partner_by_phone(number, company=company)
        if partner:
            _logger.info(
                "easy_busy_chats: linking chat %s/%s to contact %s found by phone %s",
                provider, contact_id, partner.id, number,
            )
        return partner

    @staticmethod
    def _easy_busy_extract_phone(chat_data, contact_data):
        for source in (contact_data or {}, chat_data or {}):
            if not isinstance(source, dict):
                continue
            for key in PHONE_PAYLOAD_KEYS:
                value = source.get(key)
                if isinstance(value, bool):
                    # isinstance(True, int) is True in Python
                    continue
                if isinstance(value, (int, float)):
                    value = str(int(value))
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
