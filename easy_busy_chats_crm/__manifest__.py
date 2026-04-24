{
    'name': 'EasyBusy Chats CRM',
    'version': '18.0.1.3.0',
    'category': 'Sales/CRM',
    'summary': 'Create and merge CRM opportunities directly from EasyBusy chats.',
    'description': """
EasyBusy Chats CRM
==================

EasyBusy Chats CRM extends the EasyBusy chat integration with CRM
opportunity management tools.

Main features
-------------
* Create a CRM opportunity from an EasyBusy conversation.
* Link the opportunity to an existing customer or create a new one.
* Detect possible duplicate opportunities by customer, phone, or email.
* Merge existing opportunities instead of creating duplicates.
* Keep the opportunity creation flow inside the chat panel.

Dependencies
------------
* ``easy_busy_chats``
* ``crm``
    """,
    'author': 'EasyBusyLLC',
    'license': 'LGPL-3',
    'website': 'https://easy-busy.chat',
    'depends': ['easy_busy_chats', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/easy_busy_create_opportunity_views.xml',
    ],
    'installable': True,
    'auto_install': True,
}
