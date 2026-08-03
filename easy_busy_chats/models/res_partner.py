import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


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

    @api.model
    def _easy_busy_find_partner_by_phone(self, number, company=None, email=None):
        """Return the single contact owning ``number``, or an empty recordset.

        An empty recordset is returned both when nothing matches and when the
        match is ambiguous (several contacts share the number), so that the
        caller keeps offering "Create Contact" / "Link Existing Contact" and a
        human decides which contact the chat belongs to.

        :param str number: phone number as reported by the messenger
        :param company: res.company used to normalise the number and to scope
            the search; defaults to ``self.env.company``
        :param str email: optional fallback criterion, only tried once every
            phone representation failed
        """
        company = company or self.env.company
        candidate_groups = company.sudo()._easy_busy_phone_candidate_groups(number)
        email = (email or "").strip()
        if not candidate_groups and not email:
            return self.browse()

        partner_model = self.sudo().with_context(active_test=True)
        base_domain = [
            ("type", "in", ["contact", False]),
            "|", ("company_id", "=", False), ("company_id", "=", company.id),
        ]
        # res.partner.mobile no longer exists as of Odoo 19
        phone_fields = [name for name in ("phone", "mobile") if name in self._fields]

        for candidates in candidate_groups:
            leaves = [(name, "in", candidates) for name in phone_fields]
            phone_domain = ["|"] * (len(leaves) - 1) + leaves
            matches = partner_model.search(base_domain + phone_domain, limit=2)
            if len(matches) == 1:
                return matches
            if len(matches) > 1:
                _logger.info(
                    "easy_busy_chats: %s contacts share the phone %r in company %s, "
                    "not linking automatically",
                    len(matches), number, company.id,
                )
                return self.browse()

        if email:
            matches = partner_model.search(
                base_domain + [("email", "=ilike", email)], limit=2,
            )
            if len(matches) == 1:
                return matches

        return self.browse()

    @staticmethod
    def _sanitize_easy_busy_chat_payload(payload):
        if not isinstance(payload, dict):
            return False
        provider = (payload.get("provider") or payload.get("chat", {}).get("provider", "")).lower()
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
