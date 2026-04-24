from datetime import datetime
from odoo import api, fields, models, _
from urllib.parse import urlencode


class EasyBusyChatLink(models.Model):
    _name = "easy.busy.chat.link"
    _description = "Easy Busy Chat Link"
    _rec_name = "chat_title"
    _order = "write_date desc"

    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="cascade",
    )
    provider = fields.Char(string="Provider", required=True, index=True)
    account_id = fields.Char(string="Account")
    chat_id = fields.Char(string="Chat ID", required=True, index=True)
    chat_title = fields.Char(string="Chat Title")
    contact_id = fields.Char(string="Contact ID", index=True)
    contact_user_name = fields.Char(string="User name")
    redirect_url = fields.Char(string="Chat URL", compute="_compute_redirect_url")

    _sql_constraints = [
        (
            "easy_busy_chat_link_unique",
            "unique(provider, chat_id, contact_id)",
            "The chat link already exists for this contact.",
        ),
    ]

    @staticmethod
    def _to_datetime(timestamp):
        if not timestamp:
            return False
        try:
            # timestamps are provided in milliseconds
            if isinstance(timestamp, (int, float)):
                dt = datetime.utcfromtimestamp(float(timestamp) / 1000.0)
            else:
                dt = fields.Datetime.to_datetime(timestamp)
            return fields.Datetime.to_string(dt)
        except Exception:  # noqa: broad-except
            return False

    def _compute_redirect_url(self):
        for record in self:
            if not record.provider or not record.chat_id:
                record.redirect_url = False
                continue
            params = {
                "provider": record.provider,
                "chatid": record.chat_id,
            }
            if record.account_id:
                params["accountid"] = record.account_id
            record.redirect_url = "/redirect/chats?" + urlencode(params)

    @api.model
    def upsert_from_payload(self, partner, chat_data, contact_data=None, extra=None):
        extra = extra or {}
        chat_data = chat_data or {}
        contact_data = contact_data or {}

        provider = extra.get("provider") or chat_data.get("provider")
        chat_id = chat_data.get("id")
        if not provider or not chat_id:
            return

        account_id = extra.get("accountId")

        title = chat_data.get("title")
        contact_user_name = contact_data.get("userName", chat_data.get("userName"))
        contact_id = contact_data.get("id", chat_data.get("id"))

        domain = [
            ("partner_id", "=", partner.id),
            ("provider", "=", provider),
            ("contact_id", "=", contact_id),
        ]

        values = {
            "partner_id": partner.id,
            "provider": provider,
            "chat_id": chat_id,
            "account_id": account_id or False,
            "chat_title": title,
            "contact_user_name": contact_user_name,
            "contact_id": contact_id,
        }

        link = self.search(domain, limit=1)
        if link and len(link)>0:
            link.write(values)
        else:
            self.create(values)

    def action_open_chat(self):
        self.ensure_one()
        if not self.redirect_url:
            return False
        return {
            "type": "ir.actions.act_url",
            "name": _("Go to Chat"),
            "url": self.redirect_url,
            "target": "self",
        }
