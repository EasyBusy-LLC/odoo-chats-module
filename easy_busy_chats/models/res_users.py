import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


_EASY_BUSY_USER_FIELDS = [
    'easy_busy_access_token',
    'easy_busy_company_id',
    'easy_busy_company_name',
]

EASY_BUSY_CONSOLE_URL = 'https://console.easy-busy.chat'
EASY_BUSY_COMPANIES_URL = 'https://api.easy-busy.chat/chats/v1/companies'

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    easy_busy_access_token = fields.Char(string='Easy Busy Access Token', copy=False)
    easy_busy_company_id = fields.Selection(
        selection='_get_easy_busy_company_selection',
        string='Easy Busy Company',
        copy=False,
        validate=False,
    )
    easy_busy_company_name = fields.Char(string='Easy Busy Company Name', copy=False)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + _EASY_BUSY_USER_FIELDS

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + _EASY_BUSY_USER_FIELDS

    def _get_easy_busy_company_selection(self):
        user = self[:1] if self else self.env.user
        companies = self.env['easy.busy.company'].sudo().search(
            [('user_id', '=', user.id)],
            order='name',
        )
        selection = [(company.external_id, company.name) for company in companies]

        # The selected company is stored on res.users, but the fetched option
        # list lives in a transient model and may already be gone during an
        # onchange. Keep the stored value selectable so the form stays valid.
        if user.easy_busy_company_id and user.easy_busy_company_id not in dict(selection):
            selection.append((
                user.easy_busy_company_id,
                user.easy_busy_company_name or user.easy_busy_company_id,
            ))

        return selection

    @api.onchange('easy_busy_access_token')
    def _onchange_easy_busy_access_token(self):
        for user in self:
            user.easy_busy_company_id = False
            user.easy_busy_company_name = False

    @api.onchange('easy_busy_company_id')
    def _onchange_easy_busy_company_id(self):
        self._sync_easy_busy_company_name()

    def _sync_easy_busy_company_name(self):
        for user in self:
            company = self.env['easy.busy.company'].sudo().search([
                ('user_id', '=', user.id),
                ('external_id', '=', user.easy_busy_company_id),
            ], limit=1)
            user.easy_busy_company_name = company.name if company else False

    def _select_easy_busy_company(self, companies, preferred_company_id=False):
        self.ensure_one()
        selected_company = next(
            (company for company in companies if company['external_id'] == preferred_company_id),
            None,
        )
        selected_company = selected_company or (companies[0] if companies else None)
        self.sudo().write({
            'easy_busy_company_id': selected_company['external_id'] if selected_company else False,
            'easy_busy_company_name': selected_company['name'] if selected_company else False,
        })

    def _easy_busy_fetch_companies(self):
        self.ensure_one()
        token = self.sudo().easy_busy_access_token
        if not token:
            raise UserError(_("Add your Easy Busy access token first."))
        try:
            response = requests.get(
                EASY_BUSY_COMPANIES_URL,
                headers={'Authorization': f'Bearer {token}'},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json() or []
        except Exception as ex:
            _logger.warning("Could not fetch Easy Busy companies for user %s: %s", self.id, ex)
            raise UserError(_("Could not load Easy Busy companies. Verify the access token and try again."))
        companies = [
            {
                'external_id': company['id'],
                'name': company.get('name') or company['id'],
            }
            for company in data
            if isinstance(company, dict) and company.get('id')
        ]
        if not companies:
            raise UserError(_("No Easy Busy companies were found for this token."))
        return companies

    def action_easy_busy_load_companies(self):
        self.ensure_one()
        previous_company_id = self.sudo().easy_busy_company_id

        # Clear existing companies in a separate transaction so they stay
        # cleared even if the fetch below raises (e.g. invalid token).
        with self.pool.cursor() as clear_cr:
            clear_env = self.env(cr=clear_cr)
            clear_env['easy.busy.company'].sudo().search([('user_id', '=', self.id)]).unlink()
        self.env['easy.busy.company'].invalidate_model()

        companies = self._easy_busy_fetch_companies()
        self.env['easy.busy.company'].sudo().create([
            {
                'user_id': self.id,
                **company,
            }
            for company in companies
        ])
        self._select_easy_busy_company(companies, previous_company_id)

    def action_easy_busy_get_token(self):
        return {
            'type': 'ir.actions.act_url',
            'url': EASY_BUSY_CONSOLE_URL,
            'target': 'new',
        }

    def action_open_easy_busy_chats_settings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Easy Busy Chats Settings'),
            'res_model': 'res.users',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(
                self.env.ref('easy_busy_chats.view_users_form_easy_busy_chats_dialog').id,
                'form',
            )],
            'target': 'new',
            'context': {
                **self.env.context,
                'form_view_initial_mode': 'edit',
            },
        }

    def write(self, vals):
        vals = dict(vals)
        token_changed = 'easy_busy_access_token' in vals
        company_changed = 'easy_busy_company_id' in vals
        previous_company_ids = {
            user.id: user.easy_busy_company_id for user in self
        } if token_changed else {}

        if token_changed:
            vals.update({
                'easy_busy_company_id': False,
                'easy_busy_company_name': False,
            })
        elif company_changed:
            self.ensure_one()
            company = self.env['easy.busy.company'].sudo().search([
                ('user_id', '=', self.id),
                ('external_id', '=', vals['easy_busy_company_id']),
            ], limit=1)
            vals.update({
                'easy_busy_company_name': company.name if company else False,
            })

        result = super().write(vals)

        if token_changed:
            # Clear existing companies in a separate transaction so they stay
            # cleared even if the fetch below raises (e.g. invalid token).
            with self.pool.cursor() as clear_cr:
                clear_env = self.env(cr=clear_cr)
                clear_env['easy.busy.company'].sudo().search([
                    ('user_id', 'in', self.ids),
                ]).unlink()
            self.env['easy.busy.company'].invalidate_model()

            company_model = self.env['easy.busy.company'].sudo()
            for user in self:
                try:
                    companies = user._easy_busy_fetch_companies()
                except UserError as ex:
                    _logger.warning(
                        "Could not auto-load Easy Busy companies for user %s: %s",
                        user.id, ex,
                    )
                    continue
                company_model.create([
                    {'user_id': user.id, **company}
                    for company in companies
                ])
                user._select_easy_busy_company(
                    companies,
                    previous_company_ids.get(user.id),
                )

        return result
