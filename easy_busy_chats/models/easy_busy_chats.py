import logging
from odoo import api, models

_logger = logging.getLogger(__name__)

EASY_BUSY_PLUGIN_URL = 'https://chats.easy-busy.cloud/plugin/loader.js'


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

        provider = payload.get("provider") or chat_data.get("provider")
        account_id = payload.get("accountId") or chat_data.get("accountId")
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
        partner_exists = bool(links)
        partner_record = links[0].partner_id if partner_exists else self.env["res.partner"]

        allowed_action_ids = self._collect_allowed_actions(chat_data, partner_exists)

        if partner_exists:
            extra = {
                "provider": provider,
                "accountId": account_id,
            }
            self.env["easy.busy.chat.link"].upsert_from_payload(
                partner_record,
                chat_data,
                contact_data,
                extra,
            )

        return {
            "allowed_action_ids": allowed_action_ids,
            "contact_exists": partner_exists,
            "contact_partner_id": partner_record.id if partner_record else False,
        }

    def _collect_allowed_actions(self, chat_data, partner_exists):
        allowed_action_ids = []
        if partner_exists:
            allowed_action_ids.append("view_contact")
        else:
            allowed_action_ids.extend(["create_contact", "link_contact"])
        return allowed_action_ids
