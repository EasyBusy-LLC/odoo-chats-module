{
    'name': 'EasyBusy Chats',
    'version': '18.0.3.0.0',
    'category': 'Services/Chats',
    'summary': 'Unified messenger inbox in Odoo with contact linking and chat history.',
    'keywords': ['telegram', 'instagram', 'whatsapp', 'viber', 'webchat', 'messenger', 'facebook'],
    'images': ['static/description/banner.gif'],
    'description': """
EasyBusy Chats for Odoo
=======================

EasyBusy Chats adds a dedicated chats workspace to Odoo so teams can manage
customer conversations from multiple messenger channels in one place.

Supported channels
------------------
* Telegram
* WhatsApp
* Viber
* Facebook Messenger
* Instagram
* Website chats

Key features
------------
* Open the EasyBusy chat workspace inside Odoo from a dedicated menu.
* Connect each Odoo user with an EasyBusy access token and company.
* Link chats to existing contacts or create a new contact from a conversation.
* Store linked messenger chats on the partner form.
* Open the original conversation directly from Odoo.
* Restrict access with the dedicated EasyBusy Chats user group.

Getting started
---------------
1. Install the module.
2. Open user preferences and retrieve an EasyBusy access token.
3. Select the EasyBusy company for the current user.
4. Open the **Chats** menu and start working with linked conversations.
    """,
    'author': 'EasyBusyLLC',
    'license': 'LGPL-3',
    'website': 'https://easy-busy.chat',
    'depends': ['base_setup'],
    'data': [
        'security/easy_busy_chats_security.xml',
        'security/ir.model.access.csv',
        'views/easy_busy_chats_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/easy_busy_link_contact_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'easy_busy_chats/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
