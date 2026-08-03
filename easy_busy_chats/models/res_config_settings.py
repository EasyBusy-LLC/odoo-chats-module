from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    easy_busy_auto_link_partner_by_phone = fields.Boolean(
        related="company_id.easy_busy_auto_link_partner_by_phone",
        readonly=False,
    )
