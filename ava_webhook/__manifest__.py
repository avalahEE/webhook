# noinspection PyStatementEffect
{
    'name': 'Avalah Webhook',
    'version': '1.4.0',
    'author': 'Avatud Lahendused',
    'license': 'Other proprietary',
    'website': 'https://www.avalah.ee',
    'depends': [
        'base',
        'mail',
    ],
    'data': [
        'security/security_18.xml',
        'security/ir.model.access.csv',
        'views/ava_webhook_route.xml',
        'views/ava_webhook_ip_allowlist.xml',
        'views/ava_webhook_payload.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ava_webhook/static/src/js/*.js',
        ],
    },
    'installable': True,
    'override': {
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
            'installable': False,
        },
    },
}
