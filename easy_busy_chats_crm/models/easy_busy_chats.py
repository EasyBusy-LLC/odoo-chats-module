from odoo import api, models


class EasyBusyChats(models.Model):
    _inherit = 'easy.busy.chats'

    def _collect_allowed_actions(self, chat_data, partner_exists):
        ids = super()._collect_allowed_actions(chat_data, partner_exists)
        if "create_opportunity" not in ids:
            ids.insert(0, "create_opportunity")
        return ids

    @api.model
    def on_open_chat(self, payload):
        result = super().on_open_chat(payload)
        partner = self.env["res.partner"].browse(result.get("contact_partner_id") or [])
        deals, deals_count = self._get_partner_deals(partner)
        if deals:
            result["allowed_action_ids"].append("deals")
        result.update({"deals": deals, "deals_count": deals_count})
        return result

    @api.model
    def _get_partner_deals(self, partner, limit=20):
        """Latest opportunities of the chat's contact (and its children), for
        the "Deals" select of the chat actions."""
        Lead = self.env["crm.lead"]
        if not partner or not Lead.has_access("read"):
            return [], 0
        domain = [
            ("type", "=", "opportunity"),
            ("partner_id", "child_of", partner.id),
        ]
        deals = Lead.search(domain, order="create_date desc, id desc", limit=limit)
        count = len(deals) if len(deals) < limit else Lead.search_count(domain)
        return [{"id": deal.id, "name": deal.name} for deal in deals], count
