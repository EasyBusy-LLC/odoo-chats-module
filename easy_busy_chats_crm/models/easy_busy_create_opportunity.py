from odoo import _, api, fields, models
from odoo.exceptions import UserError


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
    description = fields.Text(string="Internal Notes")
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
        return lead.redirect_lead_opportunity_view()

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
            or payload.get("chat_title")
            or _("Created from EasyBusy chat")
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
