from odoo import models, fields
import secrets
import string


class AvaWebhookKey(models.Model):
    _name = 'ava.webhook.key'
    _description = 'Webhook Key'

    # noinspection PyMethodMayBeStatic
    def _generate_key(self):
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(64))

    key = fields.Char(string='Key', required=True, default=_generate_key)
    route_id = fields.Many2one('ava.webhook.route', string='Route', required=True)
