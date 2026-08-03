import logging
import re

from odoo import fields, models
from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)

# stripped when building the "compact" variant of a formatted number
PHONE_SEPARATORS = re.compile(r"[\s\-()./]")


class ResCompany(models.Model):
    _inherit = "res.company"

    easy_busy_auto_link_partner_by_phone = fields.Boolean(
        string="Automatically link the contact to the phone number if the contact exists in partners",
        default=False,
        help="When a chat is opened and it is not linked to any contact yet, look for an existing "
             "contact having the same phone number and link the chat to it automatically. "
             "The chat then offers 'View Contact' instead of 'Create Contact'.",
    )

    # ------------------------------------------------------------------
    # Phone normalisation helpers
    # ------------------------------------------------------------------

    def _easy_busy_format_phone(self, number, force_format="INTERNATIONAL"):
        """Format ``number`` according to the country of this company.

        Returns the number unchanged when it cannot be parsed or when the
        ``phonenumbers`` library is not available.
        """
        self.ensure_one()
        number = (number or "").strip()
        if not number:
            return number

        country_code = self.country_id.code or None
        try:
            parsed = phone_validation.phone_parse(number, country_code)
            formatted = phone_validation.phone_format(
                number,
                country_code,
                parsed.country_code,
                force_format=force_format,
                raise_exception=True,  # do not get the original number returned
            )
            if formatted:  # otherwise the library is not installed
                return formatted
        except Exception:  # noqa: BLE001 - never break chat opening on a bad number
            _logger.debug(
                "easy_busy_chats: cannot format %r as %s for company %s",
                number, force_format, self.id, exc_info=True,
            )
        return number

    def _easy_busy_phone_candidate_groups(self, number):
        """Representations of ``number`` to look for, by decreasing confidence.

        Partner phone numbers are not normalised in the database, so a single
        exact match is unreliable: the very same subscriber may be stored as
        ``+380441234567``, ``+380 44 123 4567``, ``380441234567`` or
        ``0441234567``.

        Returns a list of lists; each inner list can be fed to an ``in`` domain
        leaf. Callers are expected to try the groups in order so that a strict
        match always wins over a looser one.
        """
        self.ensure_one()
        raw = (number or "").strip()
        if not raw:
            return []

        groups = []
        seen = set()

        def variants(value):
            value = (value or "").strip()
            if not value:
                return []
            out = [value]
            compact = PHONE_SEPARATORS.sub("", value)
            if compact and compact != value:
                out.append(compact)
            return out

        def add_group(values):
            group = []
            for value in values:
                if value and value not in seen:
                    seen.add(value)
                    group.append(value)
            if group:
                groups.append(group)

        # strictest: the canonical E164 form
        add_group(variants(self._easy_busy_format_phone(raw, force_format="E164")))
        # looser: locale formats and whatever the messenger actually sent
        add_group(
            variants(self._easy_busy_format_phone(raw, force_format="INTERNATIONAL"))
            + variants(self._easy_busy_format_phone(raw, force_format="NATIONAL"))
            + variants(raw)
        )
        return groups

    def _easy_busy_phone_candidates(self, number):
        """Flat, de-duplicated candidate list across all confidence levels."""
        return [
            value
            for group in self._easy_busy_phone_candidate_groups(number)
            for value in group
        ]
