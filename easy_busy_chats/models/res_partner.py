import logging
import re

from odoo import api, fields, models

try:
    import phonenumbers
except ImportError:  # optional, as in phone_validation
    phonenumbers = None

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

    def action_easy_busy_new_chat(self):
        """Open the conversation dialog to start a new chat with this contact:
        the chats plugin creates the messenger contact and its chat (account
        picked by the user), which is then linked to this partner."""
        self.ensure_one()
        name = (self.name or "").strip()
        if self.is_company:
            first_name, last_name = name, ""
        else:
            first_name, _sep, last_name = name.partition(" ")
        # First number that converts to E.164 (needed by the plugin's "auto"
        # dialog); otherwise the raw number prefills its manual form.
        # res.partner.mobile no longer exists as of Odoo 19.
        numbers = [
            self[fname] for fname in ("mobile", "phone")
            if fname in self._fields and self[fname]
        ]
        phone = next(
            (e164 for e164 in map(self._easy_busy_phone_e164, numbers) if e164),
            re.sub(r"[^\d+]", "", numbers[0]) if numbers else "",
        )

        preset = {"firstName": first_name, "lastName": last_name.strip()}
        if phone:
            preset["phoneNumber"] = phone
        return {
            "type": "ir.actions.client",
            "tag": "easy_busy_chats.open_conversation",
            "params": {
                "partner_id": self.id,
                "contact_preset": preset,
            },
        }

    def _easy_busy_phone_e164(self, number):
        """E.164 form of ``number`` or False. Tries the contact's (or the
        company's) country first, then reads a number without "+" as
        international, e.g. 34607062159 -> +34607062159."""
        self.ensure_one()
        number = (number or "").strip()
        if not number or not phonenumbers:
            return False
        digits = re.sub(r"\D", "", number)
        country = self.country_id or self.env.company.country_id
        candidates = []
        if country:
            candidates.append((number, country.code))
        # "00" is the international prefix: 0034... is +34...
        candidates.append(("+" + (digits if number.startswith("+") else digits.lstrip("0")), None))
        for value, region in candidates:
            try:
                parsed = phonenumbers.parse(value, region)
            except phonenumbers.NumberParseException:
                continue
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return False

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
