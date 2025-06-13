# -*- coding: utf-8 -*-
{
    'name': 'ONSC CV Digital IA',
    'version': '15.0.0.0.1',
    'summary': 'ONSC CV Digital IA',
    'sequence': 10,
    'description': """
ONSC CV Digital
====================
    """,
    'category': 'ONSC',
    'depends': ['base', 'web', 'onsc_cv_digital'],
    'data': [        
        'security/ir.model.access.csv',
        'views/onsc_cv_digital_ia_views.xml',
        
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
}
