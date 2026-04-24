from odoo import fields, models


class EasyBusyCompany(models.TransientModel):
    _name = 'easy.busy.company'
    _description = 'Easy Busy Company'
    _order = 'name'
    _transient_max_hours = 24

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
    )
    external_id = fields.Char(string='Company ID', required=True, index=True)
    name = fields.Char(string='Company Name', required=True)
