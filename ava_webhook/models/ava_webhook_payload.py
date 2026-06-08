from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)


class AvaWebhookPayload(models.Model):
    _name = 'ava.webhook.payload'
    _inherit = ['ava.webhook.mixin']
    _description = 'Webhook Payload'
    _rec_name = 'display_name'

    display_name = fields.Char(string='Display Name', compute='_compute_display_name')
    data_display = fields.Text(string='Data Display', compute='_compute_data_display')

    data = fields.Json(string='Data')
    route_id = fields.Many2one('ava.webhook.route', string='Route', ondelete='set null')

    def _compute_display_name(self):
        for record in self:
            route = record.route_id.route if record.route_id else 'unknown'
            record.display_name = f'[{route}] {record.create_date}'

    def _compute_data_display(self):
        for record in self:
            try:
                record.data_display = json.dumps(record.data, indent=4)
            except Exception as err:
                _logger.error(f'_compute_data_display() failed: {err}')
                record.data_display = 'Invalid JSON'

    @api.model
    def store(self, data, headers, route_id):
        return self.env['ava.webhook.payload'].create([{
            'data': data,
            'route_id': route_id
        }])
