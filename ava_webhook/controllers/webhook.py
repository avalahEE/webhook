from odoo import http, _
from odoo.http import request
from odoo.tools import config
import hmac
from ..lib.exceptions import CONCURRENCY_EXCEPTIONS, WebhookError

import logging
_logger = logging.getLogger(__name__)


class AvaWebhookController(http.Controller):
    _endpoint = '/webhook'

    @staticmethod
    def _get_request_ip(httprequest):
        forwarded_for = httprequest.headers.get('X-Forwarded-For')
        if config.get('proxy_mode') and forwarded_for:
            return forwarded_for.split(',', 1)[0].strip()
        return httprequest.remote_addr

    def _find_route(self, route, key):
        if '\x00' in route or '\x00' in key:
            # psycopg2 refuses to adapt a string holding a NUL, so this would
            # raise on the way to the database rather than simply not match.
            return None

        record = request.env['ava.webhook.route'].sudo().search([
            ('route', '=', route), ('active', '=', True)
        ], limit=1)

        if not record or not any(
            hmac.compare_digest((k.key or '').encode(), key.encode()) for k in record.key_ids
        ):
            return None
        return record

    @http.route(f'{_endpoint}/<string:route>/<string:key>', type='http', auth='public', csrf=False, methods=['POST'], save_session=False)
    def hook(self, route, key, **kwargs):
        """
        Reply with real HTTP status codes so a caller that retries on non-2xx can.

        Handlers select their own status by raising `WebhookError` or by implementing
        `webhook_response`. Everything except a status the handler returned itself
        rolls the transaction back, and the reply never carries a server traceback.

        `**kwargs` absorbs the query string, form fields and uploads that the http
        dispatcher merges into the endpoint arguments. They are ignored, as they were
        by the JSON-RPC endpoint this replaces.
        """
        return self._dispatch(route, key)

    def _dispatch(self, route, key):
        try:
            record = self._find_route(route, key)
            if not record:
                _logger.warning('webhook: %r - refused, unknown route or bad key', route)
                return self._forbidden()

            ip_address = self._get_request_ip(request.httprequest)
            if not record.is_ip_allowed(ip_address):
                _logger.warning('webhook: %r - refused, ip %r is not allowed', route, ip_address)
                return self._forbidden()

            try:
                data = request.get_json_data()
            except Exception as err:
                raise WebhookError(_('Request body is not valid JSON'), 400) from err

            body, status_code = record.execute(data, dict(request.httprequest.headers))
            request.env.cr.flush()
            return self._reply(body, status_code, rollback=False)

        except CONCURRENCY_EXCEPTIONS:
            # Let Odoo's own `retrying` see it: it rolls back and retries a
            # serialisation failure five times. Swallowing it here would turn a
            # transparent retry into an immediate 500. Any other database error
            # falls through to the generic handler below.
            raise
        except WebhookError as err:
            _logger.warning('webhook: %r - %r', route, err.message)
            body = err.body if err.body is not None else dict(ok=False, error=err.message)
            return self._reply(body, err.status_code)
        except Exception:
            _logger.exception('webhook: %r - error processing request', route)
            return self._reply(self._server_error(), 500)

    def _forbidden(self):
        """An unknown route, a bad key and a denied IP all reply identically.

        Only the log tells them apart, so a caller cannot use the reply to learn
        whether a route exists or whether its key was accepted.
        """
        return self._reply(dict(ok=False, error='Forbidden'), 403)

    @staticmethod
    def _server_error():
        return dict(ok=False, error='Internal Server Error')

    def _reply(self, body, status_code, rollback=True):
        """Build the reply, rolling the request back unless told otherwise.

        Rolling back is the default so a refusal added later cannot commit by
        forgetting to ask. Only the success path opts out, and only because the
        status came back from the handler.
        """
        if not isinstance(status_code, int) or not 200 <= status_code <= 599:
            _logger.error('webhook: handler returned an unusable status %r', status_code)
            body, status_code, rollback = self._server_error(), 500, True

        try:
            if rollback:
                request.env.cr.rollback()
            return request.make_json_response(body, status=status_code)
        except Exception:
            _logger.exception('webhook: could not build the reply')
            request.env.cr.rollback()
            return request.make_json_response(self._server_error(), status=500)
