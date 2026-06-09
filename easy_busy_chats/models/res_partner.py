from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    easy_busy_chat_link_ids = fields.One2many(
        "easy.busy.chat.link",
        "partner_id",
        string="Messenger Chats",
    )

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        payload = self.env.context.get("easy_busy_chat_link_payload")
        if payload:
            self._create_easy_busy_chat_links_from_payload(partners, payload)
        return partners

    def _create_easy_busy_chat_links_from_payload(self, partners, payload):
        sanitized = self._sanitize_easy_busy_chat_payload(payload)
        if not sanitized:
            return

        chat_data = {
            "id": sanitized["chat_id"],
            "chatType": sanitized["chat_type"],
            "title": sanitized.get("chat_title"),
        }
        contact_data = {
            "id": sanitized.get("contact_id"),
            "userName": sanitized.get("contact_user_name"),
        }
        extra = {
            "provider": sanitized["provider"],
            "accountId": sanitized.get("account_id"),
        }

        link_model = self.env["easy.busy.chat.link"].sudo()
        for partner in partners:
            link_model.upsert_from_payload(partner, chat_data, contact_data, extra)

    @staticmethod
    def _sanitize_easy_busy_chat_payload(payload):
        if not isinstance(payload, dict):
            return False
        provider = (payload.get("provider", "")).lower()
        chat_id = payload.get("chat_id")
        if not provider or not chat_id:
            return False
        return {
            "provider": provider,
            "account_id": payload.get("account_id"),
            "chat_id": chat_id,
            "chat_type": payload.get("chat_type"),
            "chat_title": payload.get("chat_title"),
            "contact_user_name": payload.get("contact_user_name"),
            "contact_id": payload.get("contact_id"),
        }
