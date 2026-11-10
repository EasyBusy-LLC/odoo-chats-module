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

        provider = (extra.get("provider", None) or chat_data.get("provider", "")).lower()
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
            ("chat_id", "=", chat_id),
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
        if link:
            link.write(values)
        else:
            self.create(values)

    def action_open_chat(self):
        """Open this chat in a dialog over the current view (conversation view
        of the chats plugin). Without an account the plugin can't target the
        chat, so the full chats page is opened instead."""
        self.ensure_one()
        if not self.provider or not self.chat_id:
            return False
        if not self.account_id:
            return self.action_open_all_chats()
        return {
            "type": "ir.actions.client",
            "tag": "easy_busy_chats.open_conversation",
            "params": {
                "provider": self.provider,
                "chatid": self.chat_id,
                "accountid": self.account_id,
                "link_id": self.id,
            },
        }

    def action_unlink_from_contact(self):
        """Remove the link between the chat and the contact (the chat itself
        stays in EasyBusy Chats)."""
        self.unlink()
        return True

    def action_open_all_chats(self):
        """Go to the chats page with this chat selected."""
        self.ensure_one()
        menu = self.env.ref("easy_busy_chats.menu_root_discuss", raise_if_not_found=False)
        params = {}
        if self.provider and self.chat_id:
            params = {
                "selectedProvider": self.provider,
                "selectedChatId": self.chat_id,
                "selectedAccountId": self.account_id or False,
            }
        return {
            "type": "ir.actions.client",
            "tag": "easy_busy_chats.action_chats",
            "name": _("Go to Chat"),
            "params": params,
            "context": {"menu_id": menu.id} if menu else {},
        }
