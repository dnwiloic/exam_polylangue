# -*- coding: utf-8 -*-
{
    'name': "Polylanguee Exam",
    'summary': """""",
    'description': """""",
    'author': "Loic DNJOMOU",
    'website': "https://digitalexpertize.com",
    'category': 'Uncategorized',
    'version': '16.0.1',
    'depends': ['base', 'gestion_formation','edof_data'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/menu.xml',
        'views/inscription.xml',
        'views/session.xml',
        'views/folder.xml',
        'data/mail_template_data.xml'
    ],
    "license": "OPL-1",
    'installable': True,
    'application': True,
    'auto_install': False,
}
