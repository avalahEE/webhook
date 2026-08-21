from odoo.tests import common, tagged
from odoo.tools import mute_logger
from ..lib.exceptions import WebhookError
from unittest.mock import patch
import psycopg2
import textwrap

WEBHOOK_LOGGER = 'odoo.addons.ava_webhook.controllers.webhook'

# odoo.service.model on 16.0 through 19.0 and odoo.http on master
RETRY_LOGGERS = ('odoo.service.model', 'odoo.http')


@tagged('post_install', '-at_install')
class TestAvaWebhookEndpoint(common.HttpCase):
    def setUp(self):
        super().setUp()
        self.route = self.env['ava.webhook.route'].create({
            'route': 'test-endpoint',
            'model': 'ava.webhook.payload',
            'store': True,
            'method_transform': False,
            'method_process': False,
            'transform': textwrap.dedent("""
                emit(input_data)
            """),
        })
        self.key = self.env['ava.webhook.key'].create({'route_id': self.route.id}).key

    def _post(self, url, body='{}', content_type='application/json'):
        return self.url_open(url, data=body, headers={'Content-Type': content_type})

    def test_endpoint_accepts_valid_request(self):
        response = self._post(f'/webhook/test-endpoint/{self.key}', '{"hello": "world"}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_wrong_key(self):
        response = self._post('/webhook/test-endpoint/wrong-key')

        self.assertEqual(response.status_code, 403)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_unknown_route(self):
        response = self._post(f'/webhook/no-such-route/{self.key}')

        self.assertEqual(response.status_code, 403)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_malformed_body(self):
        response = self._post(f'/webhook/test-endpoint/{self.key}', 'not json')

        self.assertEqual(response.status_code, 400)

    def test_endpoint_rejects_denied_ip(self):
        self.route.allow_all = False

        with self.assertLogs(WEBHOOK_LOGGER, level='WARNING') as captured:
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 403)
        self.assertIn('is not allowed', '\n'.join(captured.output))

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_maps_webhook_error_status(self):
        payload_model = type(self.env['ava.webhook.payload'])

        def store(self, data, headers, route_id):
            raise WebhookError('Product not found', status_code=422)

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {'ok': False, 'error': 'Product not found'})

    def test_endpoint_success_commits_the_handler_writes(self):
        """The mirror of the rollback tests: a 200 must keep its records."""
        payload = self.env['ava.webhook.payload']
        before = payload.search_count([('route_id', '=', self.route.id)])

        response = self._post(f'/webhook/test-endpoint/{self.key}', '{"hello": "world"}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload.search_count([('route_id', '=', self.route.id)]), before + 1)

    def test_endpoint_handler_chosen_status_keeps_its_records(self):
        """The one documented asymmetry: a non-2xx returned rather than raised
        is a deliberate choice, so the handler's writes stand."""
        payload_model = type(self.env['ava.webhook.payload'])
        marker = 'test-endpoint-kept-marker'

        def webhook_response(self, data, headers, record, route_id):
            self.env['ava.webhook.route'].create({'route': marker, 'model': 'ava.webhook.payload'})
            return {'ok': False, 'error': 'not ready'}, 409

        with patch.object(payload_model, 'webhook_response', webhook_response):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.env['ava.webhook.route'].search([('route', '=', marker)]))

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_a_non_ascii_key(self):
        """hmac.compare_digest raises TypeError on non-ASCII str, so the key
        comparison has to run on bytes. Otherwise this leaks a traceback."""
        response = self._post('/webhook/test-endpoint/võti')

        self.assertEqual(response.status_code, 403)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_a_same_length_wrong_key(self):
        """A wrong key of the right length is the case a plain == would still
        get right but not in constant time, so it must stay covered."""
        wrong = 'x' * len(self.key)
        self.assertNotEqual(wrong, self.key)

        response = self._post(f'/webhook/test-endpoint/{wrong}')

        self.assertEqual(response.status_code, 403)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_a_nul_byte_in_the_route(self):
        """psycopg2 cannot adapt a NUL, so without the guard an unauthenticated
        caller gets a 500 and a logged traceback."""
        response = self._post(f'/webhook/%00x/{self.key}')

        self.assertEqual(response.status_code, 403)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_forbidden_replies_are_indistinguishable(self):
        """An unknown route, a bad key and a denied IP must not be told apart by
        the caller, otherwise a 403 confirms the key was accepted."""
        unknown_route = self._post(f'/webhook/no-such-route/{self.key}')
        wrong_key = self._post('/webhook/test-endpoint/wrong-key')

        self.route.allow_all = False
        denied_ip = self._post(f'/webhook/test-endpoint/{self.key}')

        for other in (wrong_key, denied_ip):
            self.assertEqual(unknown_route.status_code, other.status_code)
            self.assertEqual(unknown_route.content, other.content)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_error_reply_carries_no_traceback(self):
        payload_model = type(self.env['ava.webhook.payload'])

        def store(self, data, headers, route_id):
            raise ValueError('boom')

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.headers['Content-Type'].startswith('application/json'))
        self.assertEqual(response.json(), {'ok': False, 'error': 'Internal Server Error'})

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_error_rolls_the_transaction_back(self):
        payload_model = type(self.env['ava.webhook.payload'])
        marker = 'test-endpoint-error-marker'

        def store(self, data, headers, route_id):
            self.env['ava.webhook.route'].create({'route': marker, 'model': 'ava.webhook.payload'})
            raise ValueError('boom')

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.env['ava.webhook.route'].search([('route', '=', marker)]))

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_webhook_error_rolls_the_transaction_back(self):
        payload_model = type(self.env['ava.webhook.payload'])
        marker = 'test-endpoint-webhook-error-marker'

        def store(self, data, headers, route_id):
            self.env['ava.webhook.route'].create({'route': marker, 'model': 'ava.webhook.payload'})
            raise WebhookError('Company is not tagged Klient', status_code=422)

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.env['ava.webhook.route'].search([('route', '=', marker)]))

    @mute_logger(WEBHOOK_LOGGER, 'odoo.sql_db')
    def test_endpoint_deferred_constraint_violation_replies_json(self):
        """A constraint that only fires at flush must still produce the JSON
        contract, not a werkzeug HTML page."""
        self.env['ava.webhook.route'].create({
            'route': 'test-endpoint-duplicate',
            'model': 'ava.webhook.payload',
        })
        payload_model = type(self.env['ava.webhook.payload'])

        def store(self, data, headers, route_id):
            self.env['ava.webhook.route'].browse(route_id).route = 'test-endpoint-duplicate'

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.headers['Content-Type'].startswith('application/json'))
        self.assertEqual(response.json(), {'ok': False, 'error': 'Internal Server Error'})

    @mute_logger(*RETRY_LOGGERS)
    def test_endpoint_serialisation_failure_is_left_for_odoo_to_retry(self):
        """A concurrency error must escape the controller so Odoo's own retry
        sees it. Swallowing it turns a transparent retry into a hard 500."""
        payload_model = type(self.env['ava.webhook.payload'])
        calls = []

        class SerializationFailure(psycopg2.errors.SerializationFailure):
            # A hand-built psycopg2 error has pgcode None. 16.0 through 18.0 decide
            # retryability by pgcode, 19.0 and master by isinstance, so the fixture
            # satisfies both.
            pgcode = '40001'

        def store(self, data, headers, route_id):
            calls.append(1)
            if len(calls) == 1:
                raise SerializationFailure('could not serialize access')

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}', '{"hello": "world"}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2, 'the request should have been retried once')

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_non_retryable_database_error_replies_json(self):
        """Only serialisation failures are re-raised for Odoo's own retry.
        Every other OperationalError must still come back as the JSON contract,
        not as a werkzeug HTML page."""
        payload_model = type(self.env['ava.webhook.payload'])

        class TooManyConnections(psycopg2.OperationalError):
            pgcode = '53300'

        def store(self, data, headers, route_id):
            raise TooManyConnections('too many connections')

        with patch.object(payload_model, 'store', store):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.headers['Content-Type'].startswith('application/json'))
        self.assertEqual(response.json(), {'ok': False, 'error': 'Internal Server Error'})

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_an_invalid_handler_status(self):
        """An unusable status must become a 500 with its writes rolled back,
        never a 200."""
        payload_model = type(self.env['ava.webhook.payload'])
        marker = 'test-endpoint-invalid-status-marker'

        def webhook_response(self, data, headers, record, route_id):
            self.env['ava.webhook.route'].create({'route': marker, 'model': 'ava.webhook.payload'})
            return {'ok': True}, None

        with patch.object(payload_model, 'webhook_response', webhook_response):
            response = self._post(f'/webhook/test-endpoint/{self.key}')

        self.assertEqual(response.status_code, 500)
        self.assertFalse(self.env['ava.webhook.route'].search([('route', '=', marker)]))

    def test_endpoint_ignores_query_string_arguments(self):
        """The http dispatcher merges the query string into the endpoint
        arguments; the JSON-RPC one did not."""
        response = self._post(f'/webhook/test-endpoint/{self.key}?retry=2&csrf_token=x', '{"hello": "world"}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    def test_endpoint_accepts_a_non_json_content_type(self):
        response = self._post(f'/webhook/test-endpoint/{self.key}', '{"hello": "world"}',
                              content_type='text/plain')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_rejects_a_form_encoded_body(self):
        """werkzeug drains the stream while parsing the form, so nothing is
        left for get_json_data."""
        response = self._post(f'/webhook/test-endpoint/{self.key}', 'hello=world',
                              content_type='application/x-www-form-urlencoded')

        self.assertEqual(response.status_code, 400)

    @mute_logger(WEBHOOK_LOGGER)
    def test_endpoint_refuses_a_route_without_keys(self):
        """A keyless route must never be open; any() over an empty recordset
        is the only thing preventing that."""
        self.env['ava.webhook.route'].create({
            'route': 'test-endpoint-keyless',
            'model': 'ava.webhook.payload',
        })

        response = self._post(f'/webhook/test-endpoint-keyless/{self.key}')

        self.assertEqual(response.status_code, 403)

    def test_endpoint_accepts_any_of_several_keys(self):
        second_key = self.env['ava.webhook.key'].create({'route_id': self.route.id}).key

        for key in (self.key, second_key):
            response = self._post(f'/webhook/test-endpoint/{key}', '{"hello": "world"}')
            self.assertEqual(response.status_code, 200)
