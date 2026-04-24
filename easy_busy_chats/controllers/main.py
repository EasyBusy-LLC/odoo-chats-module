from odoo import http
from odoo.http import request
from werkzeug.utils import redirect
import urllib.parse


class EasyBusyChatsController(http.Controller):
    
    @http.route('/redirect/chats', type='http', auth='user')
    def redirect_to_chat(self, **kwargs):
        provider = kwargs.get('provider', '')
        chatid = kwargs.get('chatid', '')
        account_id = kwargs.get('accountid', '')

        # Get the menu record by XML ID
        menu = request.env.ref('easy_busy_chats.menu_root_discuss', raise_if_not_found=False)
        menu_id = menu.id if menu else None

        # URL encode the parameters safely
        fragment_params = {
            'action': 'easy_busy_chats.action_chats',
            'provider': provider,
            'chatid': chatid,
            'menu_id': menu_id,
            'accountid': account_id
        }

        # Build /web#... style URL fragment
        url = '/web#' + urllib.parse.urlencode(fragment_params)
        
        redirect = request.redirect(url, 303)
        redirect.autocorrect_location_header = False
        return redirect  