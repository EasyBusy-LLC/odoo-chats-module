from odoo import models


class EasyBusyChats(models.Model):
    _inherit = 'easy.busy.chats'

    def _collect_allowed_actions(self, chat_data, partner_exists):
        ids = super()._collect_allowed_actions(chat_data, partner_exists)
        if "create_opportunity" not in ids:
            ids.insert(0, "create_opportunity")
        return ids
