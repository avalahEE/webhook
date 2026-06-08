from odoo import http
from odoo.http import request
from odoo.release import version_info
from odoo.tools import config
from werkzeug.exceptions import Forbidden, NotFound, InternalServerError # noqa
import hmac

import logging
_logger = logging.getLogger(__name__)

JSON_CONTROLLER_TYPE = 'jsonrpc'
if version_info[:2] <= (18, 0):
    JSON_CONTROLLER_TYPE = 'json'


class AvaWebhookController(http.Controller):
    _endpoint = '/webhook'

    @staticmethod
    def _get_request_ip(httprequest):
        forwarded_for = httprequest.headers.get('X-Forwarded-For')
        if config.get('proxy_mode') and forwarded_for:
            return forwarded_for.split(',', 1)[0].strip()
        return httprequest.remote_addr

    @http.route(f'{_endpoint}/<string:route>/<string:key>', type=JSON_CONTROLLER_TYPE, auth='public', csrf=False)
    def hook(self, route, key):
        assert request.env
        record = request.env['ava.webhook.route'].sudo().search([
            ('route', '=', route), ('active', '=', True)
        ], limit=1)

        if not record or not any(
            hmac.compare_digest(k.key, key) for k in record.key_ids
        ):
            raise NotFound()

        if not record.is_ip_allowed(self._get_request_ip(request.httprequest)):
            raise Forbidden()

        try:
            record.execute(request.get_json_data(), dict(request.httprequest.headers))
        except Exception as err:
            _logger.error(f'webhook: {record.route} - error processing request')
            _logger.exception(err)
            raise InternalServerError()

        return dict(ok=True)
