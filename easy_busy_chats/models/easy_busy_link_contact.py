from odoo import _, fields, models
from odoo.exceptions import UserError


class EasyBusyLinkContact(models.TransientModel):
    _name = "easy.busy.link.contact"
    _description = "Link chat with existing contact"

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        domain="[('type', 'in', ['contact', False])]",
        help="Pick the existing contact that should be linked to this chat.",
    )

    def action_link_contact(self):
        self.ensure_one()
        payload = self.env.context.get("easy_busy_chat_link_payload")
        if not payload:
            raise UserError(_("Missing chat payload to link with the contact."))

        partner = self.partner_id.sudo()
        self.env["res.partner"]._create_easy_busy_chat_links_from_payload(partner, payload)
 
        return {"type": "ir.actions.act_window_close"}
