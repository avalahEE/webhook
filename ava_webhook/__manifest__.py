# noinspection PyStatementEffect
{
    'name': 'Avalah Webhook',
    'version': '2.0.1',
    'author': 'Avatud Lahendused',
    'license': 'Other OSI approved license',
    'website': 'https://www.avalah.ee',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/security_18.xml',
        'security/ir.model.access.csv',
        'views/ava_webhook_route_17.xml',
        'views/ava_webhook_ip_allowlist_17.xml',
        'views/ava_webhook_payload_17.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ava_webhook/static/src/js/*.js',
        ],
    },
    'installable': True,
    'override': {
        '19.0': {
            'installable': True,
            'data': [
                'security/security.xml',
                'security/ir.model.access.csv',
                'views/ava_webhook_route.xml',
                'views/ava_webhook_ip_allowlist.xml',
                'views/ava_webhook_payload.xml',
            ],
        },
        '18.0': {
            'installable': True,
            'data': [
                'security/security_18.xml',
                'security/ir.model.access.csv',
                'views/ava_webhook_route.xml',
                'views/ava_webhook_ip_allowlist.xml',
                'views/ava_webhook_payload.xml',
            ],
        },
        '17.0': {
            'installable': True,
            'data': [
                'security/security_18.xml',
                'security/ir.model.access.csv',
                'views/ava_webhook_route_17.xml',
                'views/ava_webhook_ip_allowlist_17.xml',
                'views/ava_webhook_payload_17.xml',
            ],
            'assets': {
                'web.assets_backend': [
                    'ava_webhook/static/src/js/*.js',
                ],
            },
        },
        '16.0': {
            'installable': True,
            'data': [
                'security/security_18.xml',
                'security/ir.model.access.csv',
                'views/ava_webhook_route_16.xml',
                'views/ava_webhook_ip_allowlist_16.xml',
                'views/ava_webhook_payload_16.xml',
            ],
            'assets': {
                'web.assets_backend': [
                    'ava_webhook/static/src/js/16/*.js',
                ],
            },
        },
    },
}
