from odoo import models, fields, api
from odoo.exceptions import ValidationError
import ipaddress


class AvaWebhookIpAllowlist(models.Model):
    _name = 'ava.webhook.ip.allowlist'
    _description = 'Webhook IP Allowlist'

    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    line_ids = fields.One2many('ava.webhook.ip.allowlist.line', 'allowlist_id', string='IP Ranges')

    def allows_ip(self, ip_address):
        self.ensure_one()
        if not self.active:
            return False
        return any(line.allows_ip(ip_address) for line in self.line_ids)


class AvaWebhookIpAllowlistLine(models.Model):
    _name = 'ava.webhook.ip.allowlist.line'
    _description = 'Webhook IP Allowlist Line'
    _rec_name = 'ip_range'

    allowlist_id = fields.Many2one(
        'ava.webhook.ip.allowlist',
        string='Allowlist', required=True, ondelete='cascade'
    )

    ip_range = fields.Char(
        string='IP / CIDR Range', required=True,
        help='Single IP address or CIDR range, for example 192.168.1.10 or 192.168.1.0/24.',
    )

    @api.constrains('ip_range')
    def _check_ip_range(self):
        for record in self:
            try:
                record._get_network()
            except ValueError:
                raise ValidationError('Invalid IP address or CIDR range: %s' % record.ip_range)

    def _get_network(self):
        self.ensure_one()
        return ipaddress.ip_network((self.ip_range or '').strip(), strict=False)

    def allows_ip(self, ip_address):
        self.ensure_one()
        try:
            return ipaddress.ip_address(ip_address) in self._get_network()
        except ValueError:
            return False
