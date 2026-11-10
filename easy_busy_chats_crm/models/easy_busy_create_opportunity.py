import ipaddress
import logging
import mimetypes
import os
import socket
from urllib.parse import unquote, urljoin, urlparse

import requests
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_html_empty, plaintext2html

_logger = logging.getLogger(__name__)

# Limits for copying files of the selected chat messages into the opportunity.
CHAT_FILE_MAX_COUNT = 30
CHAT_FILE_MAX_SIZE = 25 * 1024 * 1024
CHAT_FILES_MAX_TOTAL_SIZE = 100 * 1024 * 1024
CHAT_FILE_TIMEOUT = 15
CHAT_FILE_MAX_REDIRECTS = 3


def _is_public_url(url):
    """Only fetch http(s) URLs whose host resolves to public addresses: the
    URLs come from the browser, so internal hosts must not be reachable."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(parsed.hostname, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    return bool(infos) and all(
        ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos
    )


class EasyBusyCreateOpportunity(models.TransientModel):
    _name = "easy.busy.create.opportunity"
    _description = "Create Opportunity from EasyBusy Chat"

    name = fields.Char(string="Chat Title", readonly=True)
    conversion_action = fields.Selection(
        [
            ("convert", "Convert to opportunity"),
            ("merge", "Merge with existing opportunities"),
        ],
        required=True,
        compute="_compute_conversion_action",
        store=True,
        readonly=False,
    )
    chat_link_id = fields.Many2one(
        "easy.busy.chat.link",
        string="Easy Busy Chat Link",
        readonly=True,
        default=lambda self: self._default_chat_link_id(),
    )
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        domain="[('share', '=', False)]",
        required=True,
        default=lambda self: self._default_user_id(),
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Sales Team",
        default=lambda self: self._default_team_id(),
    )
    duplicated_lead_ids = fields.Many2many(
        "crm.lead",
        string="Opportunities",
        domain="[('type', '=', 'opportunity')]",
        context={"active_test": False},
    )
    customer_action = fields.Selection(
        [
            ("create", "Create a new customer"),
            ("exist", "Link to an existing customer"),
            ("nothing", "Do not link to a customer"),
        ],
        string="Customer",
        required=True,
        default=lambda self: self._default_customer_action(),
    )
    partner_id = fields.Many2one("res.partner", string="Customer")
    new_partner_name = fields.Char(string="Customer Name")
    opportunity_name = fields.Char(string="Opportunity Title", required=True)
    description = fields.Html(string="Internal Notes")
    contact_phone = fields.Char(string="Contact Phone")
    contact_email = fields.Char(string="Contact Email")

    @api.depends("duplicated_lead_ids")
    def _compute_conversion_action(self):
        for wizard in self:
            if wizard.conversion_action:
                continue
            wizard.conversion_action = (
                "merge" if len(wizard.duplicated_lead_ids) >= 2 else "convert"
            )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        payload = self.env.context.get("easy_busy_chat_link_payload") or {}
        partner_id = self.env.context.get("default_partner_id")
        contact_phone = res.get("contact_phone") or self.env.context.get("default_phone")
        contact_email = res.get("contact_email") or self.env.context.get("default_email_from")

        # The chat may not be linked yet: recognise the customer from its phone
        # number when the company allows it, so that the wizard shows the
        # existing customer instead of silently creating a duplicate.
        auto_partner_id = False
        if not partner_id:
            auto_partner_id = self._easy_busy_find_existing_partner_id(contact_phone)
            partner_id = auto_partner_id

        if "name" in fields_list:
            res["name"] = payload.get("chat_title")
        if "opportunity_name" in fields_list and not res.get("opportunity_name"):
            res["opportunity_name"] = payload.get("chat_title") or _("EasyBusy Opportunity")
        if "new_partner_name" in fields_list and not res.get("new_partner_name"):
            res["new_partner_name"] = payload.get("contact_user_name") or payload.get("chat_title")
        if "customer_action" in fields_list and "customer_action" not in res:
            res["customer_action"] = "exist" if partner_id else "create"
        if "customer_action" in fields_list and auto_partner_id:
            # the field default (and the context) were computed without knowing
            # about the customer we just recognised from the phone number
            res["customer_action"] = "exist"
        if "partner_id" in fields_list and partner_id:
            res["partner_id"] = partner_id
        if "contact_phone" in fields_list and not res.get("contact_phone"):
            res["contact_phone"] = contact_phone
        if "contact_email" in fields_list and not res.get("contact_email"):
            res["contact_email"] = contact_email
        if "description" in fields_list:
            res["description"] = self._default_description(res.get("description"))
        if "chat_link_id" in fields_list and not res.get("chat_link_id"):
            chat_link = self._find_chat_link_from_payload(payload, partner_id)
            if chat_link:
                res["chat_link_id"] = chat_link.id
        if "duplicated_lead_ids" in fields_list:
            duplicated_leads = self._get_duplicate_opportunities_for_values(
                partner_id=partner_id,
                phone=contact_phone,
                email=contact_email,
            )
            res["duplicated_lead_ids"] = [(6, 0, duplicated_leads.ids)]
            if "conversion_action" in fields_list:
                res["conversion_action"] = "merge" if len(duplicated_leads) >= 2 else "convert"
        return res

    @api.model
    def _easy_busy_find_existing_partner(self, phone):
        """Existing customer owning ``phone``, when the company allows linking.

        Returns an empty recordset when the setting is off, when nothing matches
        or when several customers share the number.
        """
        company = self.env.company
        if not company.sudo().easy_busy_auto_link_partner_by_phone:
            return self.env["res.partner"]
        return self.env["res.partner"]._easy_busy_find_partner_by_phone(
            phone, company=company,
        )

    @api.model
    def _easy_busy_find_existing_partner_id(self, phone):
        partner = self._easy_busy_find_existing_partner(phone)
        return partner.id if partner else False

    @api.onchange("contact_phone")
    def _onchange_contact_phone_find_partner(self):
        """Reuse an existing customer as soon as the phone number matches one.

        Declared before ``_onchange_duplicate_lead_ids`` so that the duplicate
        opportunity search below sees the partner set here.
        """
        for wizard in self:
            if wizard.customer_action != "create" or wizard.partner_id:
                continue
            existing = wizard._easy_busy_find_existing_partner(wizard.contact_phone)
            if existing:
                wizard.partner_id = existing
                wizard.customer_action = "exist"

    @api.model
    def _default_description(self, description):
        messages = self.env.context.get("easy_busy_chat_selected_messages")
        if messages and isinstance(messages, list):
            return self._render_chat_messages(messages)
        if description and not isinstance(description, Markup):
            # Plain text coming from the chat (e.g. its last message).
            return plaintext2html(description)
        return description

    @api.model
    def _render_chat_messages(self, messages):
        """Render messages selected in the chat (normalized by the chats
        client action) as HTML for the opportunity notes."""
        blocks = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            author = message.get("author") or (
                _("Customer") if message.get("is_income") else _("Manager")
            )
            header = Markup("<b>%s</b>") % author
            if message.get("date"):
                header += Markup(" <small>%s</small>") % message["date"]

            content = Markup()
            text = (message.get("text") or "").strip()
            if text:
                content += plaintext2html(text)

            images = []
            attachments = []
            for attachment in message.get("attachments") or []:
                if not isinstance(attachment, dict):
                    continue
                name = attachment.get("name") or _("File")
                url = attachment.get("url") or ""
                is_web_url = url.startswith(("http://", "https://"))
                if is_web_url and attachment.get("kind") == "image":
                    # URLs are replaced by the opportunity's own copies on confirm.
                    images.append(
                        Markup(
                            '<a href="%s" target="_blank" rel="noopener">'
                            '<img src="%s" alt="%s" class="img-fluid w-25"/></a>'
                        ) % (url, url, name)
                    )
                elif is_web_url:
                    attachments.append(
                        Markup('<a href="%s" target="_blank" rel="noopener">%s</a>') % (url, name)
                    )
                else:
                    attachments.append(Markup("%s") % name)
            if images:
                content += Markup("<p>%s</p>") % Markup(" ").join(images)
            if attachments:
                content += Markup("<p><i>%s</i> %s</p>") % (
                    _("Attachments:"),
                    Markup(", ").join(attachments),
                )

            blocks.append(Markup("<p>%s</p>%s") % (header, content))

        if not blocks:
            return False
        title = Markup("<p><b>%s</b></p>") % _("Chat messages")
        return title + Markup("").join(blocks)

    @api.model
    def _default_user_id(self):
        partner = self.env.context.get("default_partner_id")
        if partner:
            record = self.env["res.partner"].browse(partner)
            if record.user_id:
                return record.user_id.id
        return self.env.user.id

    @api.model
    def _default_team_id(self):
        user = self.env["res.users"].browse(self._default_user_id())
        team = self.env["crm.team"]._get_default_team_id(user_id=user.id, domain=None)
        return team.id if team else False

    def _default_chat_link_id(self):
        payload = self.env.context.get("easy_busy_chat_link_payload") or {}
        partner_id = self.env.context.get("default_partner_id")
        link = self._find_chat_link_from_payload(payload, partner_id)
        return link.id if link else False

    def _find_chat_link_from_payload(self, payload, partner_id):
        
        if (
            not payload
            or not payload.get("provider")
            or not payload.get("chat_id")
        ):
            return self.env["easy.busy.chat.link"]
        domain = [
            ("provider", "=", payload["provider"].lower()),
            ("chat_id", "=", payload["chat_id"]),
        ]
        if partner_id:
            domain.append(("partner_id", "=", partner_id))
        return self.env["easy.busy.chat.link"].sudo().search(domain, limit=1)

    @api.model
    def _default_customer_action(self):
        partner_id = self.env.context.get("default_partner_id")
        return "exist" if partner_id else "create"

    def action_confirm(self):
        self.ensure_one()
        if self.conversion_action == "merge":
            lead = self._action_merge()
        else:
            lead = self._action_convert()
        self._attach_chat_files(lead)
        return lead.redirect_lead_opportunity_view()

    def _get_chat_files(self):
        """Files of the selected chat messages, unique by URL."""
        files = {}
        for message in self.env.context.get("easy_busy_chat_selected_messages") or []:
            if not isinstance(message, dict):
                continue
            for attachment in message.get("attachments") or []:
                url = isinstance(attachment, dict) and attachment.get("url")
                if url and url.startswith(("http://", "https://")) and url not in files:
                    files[url] = attachment
        return list(files.values())[:CHAT_FILE_MAX_COUNT]

    @api.model
    def _download_chat_file(self, url):
        """Return ``(content, content_type)`` or ``None`` if the file can't be
        fetched safely. Redirects are followed manually so every hop is checked."""
        try:
            for _hop in range(CHAT_FILE_MAX_REDIRECTS + 1):
                if not _is_public_url(url):
                    return None
                with requests.get(
                    url, timeout=CHAT_FILE_TIMEOUT, stream=True, allow_redirects=False
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("Location", ""))
                        continue
                    if response.status_code != 200:
                        return None
                    if int(response.headers.get("Content-Length") or 0) > CHAT_FILE_MAX_SIZE:
                        return None
                    chunks, size = [], 0
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > CHAT_FILE_MAX_SIZE:
                            return None
                        chunks.append(chunk)
                    content_type = (response.headers.get("Content-Type") or "").split(";")[0]
                    return b"".join(chunks), content_type.strip()
        except (requests.RequestException, ValueError) as error:
            _logger.info("easy_busy_chats: failed to download chat file %s: %s", url, error)
        return None

    @staticmethod
    def _chat_file_name(attachment, url, mimetype):
        name = attachment.get("name") or ""
        if not os.path.splitext(name)[1]:
            url_name = unquote(os.path.basename(urlparse(url).path))
            if os.path.splitext(url_name)[1]:
                name = url_name
            else:
                name += mimetypes.guess_extension(mimetype or "") or ""
        return name or "file"

    def _attach_chat_files(self, lead):
        """Copy the files of the selected chat messages into ``lead``: post them
        in the chatter (opened in Odoo's file viewer) and point the notes at the
        stored copies, since chat file URLs may expire."""
        files = self._get_chat_files()
        if not lead or not files:
            return
        Attachment = self.env["ir.attachment"].sudo()
        attachments = Attachment
        local_urls = {}
        total_size = 0
        for attachment in files:
            url = attachment["url"]
            downloaded = self._download_chat_file(url)
            if not downloaded:
                continue
            content, content_type = downloaded
            total_size += len(content)
            if total_size > CHAT_FILES_MAX_TOTAL_SIZE:
                break
            mimetype = attachment.get("mimetype") or content_type or False
            record = Attachment.create(
                {
                    "name": self._chat_file_name(attachment, url, mimetype),
                    "raw": content,
                    "mimetype": mimetype,
                    "res_model": "crm.lead",
                    "res_id": lead.id,
                }
            )
            attachments |= record
            route = "image" if (record.mimetype or "").startswith("image/") else "content"
            local_urls[url] = "/web/%s/%s" % (route, record.id)

        if not attachments:
            return

        if not is_html_empty(lead.description):
            description = str(lead.description)
            for url, local_url in local_urls.items():
                description = description.replace(str(escape(url)), local_url)
                description = description.replace(url, local_url)
            lead.sudo().description = Markup(description)

        lead.sudo().message_post(
            body=_("Files from the chat"),
            attachment_ids=attachments.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    def _action_merge(self):
        if len(self.duplicated_lead_ids) < 2:
            raise UserError(_("Select at least two opportunities to merge."))
        to_merge = self.duplicated_lead_ids.with_context(active_test=False)
        result = to_merge.merge_opportunity(auto_unlink=False)
        result.action_unarchive()

        if result.type == "lead":
            result.convert_opportunity(result.partner_id, user_ids=False, team_id=False)

        if not result.user_id:
            result.write(
                {
                    "user_id": self.user_id.id,
                    "team_id": self.team_id.id,
                }
            )
        (to_merge - result).sudo().unlink()
        if not is_html_empty(self.description):
            result.description = (result.description or Markup()) + self.description
        return result

    def _action_convert(self):
        partner = self._resolve_partner()
        lead_vals = self._prepare_lead_vals(partner)
        lead = self.env["crm.lead"].sudo().create(lead_vals)
        return lead

    def _resolve_partner(self):
        payload = self.env.context.get("easy_busy_chat_link_payload")
        if self.customer_action == "exist":
            if not self.partner_id:
                raise UserError(_("Please choose a customer to link the opportunity to."))
            if payload:
                self.env["res.partner"]._create_easy_busy_chat_links_from_payload(
                    self.partner_id, payload
                )
            return self.partner_id

        if self.customer_action == "create":
            partner_name = (
                self.new_partner_name
                or self.env.context.get("default_contact_name")
                or self.opportunity_name
            )
            if not partner_name:
                raise UserError(_("Please provide the name of the customer to create."))

            # Safety net for submissions that never round-tripped an onchange
            # (RPC calls, tests): never duplicate a customer we could link to.
            existing = self._easy_busy_find_existing_partner(self.contact_phone)
            if existing:
                if payload:
                    self.env["res.partner"]._create_easy_busy_chat_links_from_payload(
                        existing, payload
                    )
                return existing
            partner_vals = {
                "name": partner_name,
                "phone": self.contact_phone,
                "mobile": self.contact_phone,
                "email": self.contact_email,
            }
            ctx = self.env.context.copy()
            if payload:
                ctx["easy_busy_chat_link_payload"] = payload
            return self.env["res.partner"].with_context(ctx).sudo().create(partner_vals)

        return False

    def _prepare_lead_vals(self, partner):
        payload = self.env.context.get("easy_busy_chat_link_payload") or {}
        description = (
            self.description
            if not is_html_empty(self.description)
            else plaintext2html(payload.get("chat_title") or _("Created from EasyBusy chat"))
        )
        lead_vals = {
            "name": self.opportunity_name,
            "type": "opportunity",
            "user_id": self.user_id.id,
            "team_id": self.team_id.id,
            "partner_id": partner.id if partner else False,
            "description": description,
            "phone": self.contact_phone,
            "mobile": self.contact_phone,
            "email_from": self.contact_email,
            "company_id": self.env.company.id,
        }
        return {key: val for key, val in lead_vals.items() if val}

    @api.onchange("partner_id", "contact_phone", "contact_email")
    def _onchange_duplicate_lead_ids(self):
        for wizard in self:
            wizard.duplicated_lead_ids = wizard._get_duplicate_opportunities()

    def _get_duplicate_opportunities(self):
        self.ensure_one()
        return self._get_duplicate_opportunities_for_values(
            partner_id=self.partner_id.id,
            phone=self.contact_phone,
            email=self.contact_email,
        )

    def _get_duplicate_opportunities_for_values(self, partner_id=False, phone=False, email=False):
        leads = self.env["crm.lead"]
        search = self.env["crm.lead"].with_context(active_test=False).sudo()

        if partner_id:
            leads |= search.search(
                [("type", "=", "opportunity"), ("partner_id", "=", partner_id)]
            )

        for phone_candidate in self._phone_search_candidates(phone):
            leads |= search.search(
                [
                    ("type", "=", "opportunity"),
                    "|",
                    ("phone", "=", phone_candidate),
                    ("mobile", "=", phone_candidate),
                ]
            )

        email = (email or "").strip()
        if email:
            leads |= search.search(
                [("type", "=", "opportunity"), ("email_from", "=ilike", email)]
            )

        return leads

    @staticmethod
    def _phone_search_candidates(phone):
        phone = (phone or "").strip()
        if not phone:
            return []
        compact = phone.replace(" ", "")
        return [phone] if compact == phone else [phone, compact]
