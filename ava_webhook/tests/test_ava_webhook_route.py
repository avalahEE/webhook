from odoo import exceptions
from odoo.tests import common
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config
from ..controllers.webhook import AvaWebhookController
from ..lib.exceptions import CONCURRENCY_EXCEPTIONS, WebhookError
from unittest.mock import patch
import psycopg2.errors
import textwrap


class TestAvaWebhookRoute(common.TransactionCase):
    def setUp(self):
        super().setUp()
        # Create a basic webhook route
        self.route = self.env['ava.webhook.route'].create({
            'route': 'test-route',
            'model': 'ava.webhook.payload',
            'store': True,
            'transform': """
                emit(input_data)
            """,
            'process': """
                log('Processing record', record)
            """
        })

    def _create_allowlist(self, active=True):
        return self.env['ava.webhook.ip.allowlist'].create({
            'name': 'Office',
            'active': active,
            'line_ids': [(0, 0, {'ip_range': '203.0.113.0/24'})],
        })

    def test_list_methods(self):
        """Test that list_methods returns appropriate model methods"""
        methods = self.route.with_context(resId=self.route.id).list_methods()
        self.assertIsInstance(methods, list)
        # Each method should be a tuple of (name, name)
        for method in methods:
            self.assertIsInstance(method, tuple)
            self.assertEqual(len(method), 2)
            self.assertEqual(method[0], method[1])

    def test_transform_discard(self):
        """Test that transform can discard records"""
        route = self.env['ava.webhook.route'].create({
            'route': 'test-discard',
            'model': 'ava.webhook.payload',
            'method_transform': False,
            'transform': textwrap.dedent("""
                log('discarding')
                discard()
            """),
        })

        test_headers = {'X-Test': 'test'}
        result = route._execute_transform(route._get_model(), {'test': 'data'}, test_headers)
        self.assertIsNone(result)

    def test_transform_emit(self):
        """Test that transform can emit data"""
        test_data = {'test': 'data'}
        test_headers = {'X-Test': 'test'}
        route = self.env['ava.webhook.route'].create({
            'route': 'test-emit',
            'model': 'ava.webhook.payload',
            'method_transform': False,
            'transform': textwrap.dedent("""
                emit(input_data)
            """),
        })

        result = route._execute_transform(route._get_model(), test_data, test_headers)
        self.assertEqual(result, test_data)

    def test_execute_uses_recordset_user(self):
        """Test that execute runs expressions with the recordset user"""
        user = self.env['res.users'].create({
            'name': 'Webhook Execution User',
            'login': 'webhook-execution-user',
            'email': 'webhook-execution-user@example.com',
        })
        route = self.env['ava.webhook.route'].create({
            'route': 'test-execution-user',
            'model': 'ava.webhook.payload',
            'execution_user_id': user.id,
            'method_transform': False,
            'method_process': False,
            'transform': textwrap.dedent("""
                emit({'uid': model.env.uid})
            """),
        })

        body, status_code = route.sudo().execute({'test': 'data'}, {'X-Test': 'test'})

        self.assertEqual((body, status_code), ({'ok': True}, 200))
        self.assertEqual(route.sudo()._execute_transform(route.sudo()._get_model(), {}, {}), {'uid': user.id})

    def test_route_allow_all_allows_any_ip(self):
        self.assertTrue(self.route.allow_all)
        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))

    def test_route_without_allow_all_and_without_allowlists_denies_any_ip(self):
        self.route.allow_all = False

        self.assertFalse(self.route.is_ip_allowed('203.0.113.10'))

    def test_route_allows_ip_from_allowlist(self):
        allowlist = self._create_allowlist()
        self.route.ip_allowlist_ids = [(6, 0, allowlist.ids)]

        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))
        self.assertFalse(self.route.is_ip_allowed('198.51.100.10'))

    def test_route_with_only_inactive_allowlists_denies_any_ip(self):
        allowlist = self._create_allowlist(active=False)
        self.route.write({'ip_allowlist_ids': [(6, 0, allowlist.ids)]})

        self.assertEqual(self.route.with_context(active_test=False).ip_allowlist_ids.ids, allowlist.ids)
        self.assertTrue(self.route.allow_all)
        self.assertFalse(self.route.is_ip_allowed('203.0.113.10'))

    def test_route_ignores_allow_all_with_attached_allowlists(self):
        allowlist = self._create_allowlist()
        self.route.ip_allowlist_ids = [(6, 0, allowlist.ids)]
        self.route.allow_all = True

        self.assertTrue(self.route.allow_all)
        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))
        self.assertFalse(self.route.is_ip_allowed('198.51.100.10'))

    def test_route_ignores_allow_all_with_inactive_attached_allowlists(self):
        allowlist = self._create_allowlist(active=False)
        self.route.ip_allowlist_ids = [(6, 0, allowlist.ids)]
        self.route.allow_all = True

        self.assertTrue(self.route.allow_all)
        self.assertFalse(self.route.is_ip_allowed('203.0.113.10'))

    def test_route_can_enable_allow_all_after_clearing_allowlists(self):
        allowlist = self._create_allowlist()
        self.route.ip_allowlist_ids = [(6, 0, allowlist.ids)]

        self.route.write({
            'ip_allowlist_ids': [(5, 0, 0)],
            'allow_all': True,
        })

        self.assertTrue(self.route.allow_all)
        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))

    def test_request_ip_uses_x_forwarded_for_in_proxy_mode(self):
        class HttpRequest:
            headers = {'X-Forwarded-For': '203.0.113.10, 198.51.100.20'}
            remote_addr = '198.51.100.10'

        proxy_mode = config.get('proxy_mode')
        config['proxy_mode'] = True
        try:
            self.assertEqual(AvaWebhookController._get_request_ip(HttpRequest), '203.0.113.10')
        finally:
            config['proxy_mode'] = proxy_mode

    def test_request_ip_ignores_x_forwarded_for_without_proxy_mode(self):
        class HttpRequest:
            headers = {'X-Forwarded-For': '203.0.113.10, 198.51.100.20'}
            remote_addr = '198.51.100.10'

        proxy_mode = config.get('proxy_mode')
        config['proxy_mode'] = False
        try:
            self.assertEqual(AvaWebhookController._get_request_ip(HttpRequest), '198.51.100.10')
        finally:
            config['proxy_mode'] = proxy_mode

    def test_request_ip_falls_back_to_remote_addr(self):
        class HttpRequest:
            headers = {}
            remote_addr = '198.51.100.10'

        self.assertEqual(AvaWebhookController._get_request_ip(HttpRequest), '198.51.100.10')

    def test_invalid_allowlist_ip_range(self):
        with self.assertRaises(ValidationError):
            self.env['ava.webhook.ip.allowlist'].create({
                'name': 'Invalid',
                'line_ids': [(0, 0, {'ip_range': 'not-an-ip'})],
            })

    def test_transform_error(self):
        """Test that transform errors are handled properly"""
        route = self.env['ava.webhook.route'].create({
            'route': 'test-error',
            'model': 'ava.webhook.payload',
            'method_transform': False,
            'transform': textwrap.dedent("""
                this_function_does_not_exist()
            """),
        })

        test_headers = {'X-Test': 'test'}
        with self.assertRaises(UserError):
            route.with_context(ava_suppress_error_log=True)._execute_transform(
                route._get_model(), {'test': 'data'}, test_headers)

    def test_process_method(self):
        """Test that process can use method"""
        route = self.env['ava.webhook.route'].create({
            'route': 'test-process-method',
            'model': 'ava.webhook.payload',
            'method_process': 'process'
        })

        test_data = {'test': 'data'}
        test_headers = {'X-Test': 'test'}
        test_record = self.env['ava.webhook.payload'].create({'data': test_data})
        route._execute_process(route._get_model(), test_data, test_headers, test_record)

    def test_process_expression(self):
        """Test that process expression works"""
        route = self.env['ava.webhook.route'].create({
            'route': 'test-process-expr',
            'model': 'ava.webhook.payload',
            'method_process': False,
            'process': textwrap.dedent("""
                log('processing record: %s', record)
            """),
        })

        test_data = {'test': 'data'}
        test_headers = {'X-Test': 'test'}
        test_record = self.env['ava.webhook.payload'].create({'data': test_data})
        route._execute_process(route._get_model(), test_data, test_headers, test_record)

    def test_process_error(self):
        """Test that process errors are handled properly"""
        route = self.env['ava.webhook.route'].create({
            'route': 'test-process-error',
            'model': 'ava.webhook.payload',
            'method_process': False,
            'process': textwrap.dedent("""
                this_function_does_not_exist()
            """),
        })

        test_data = {'test': 'data'}
        test_headers = {'X-Test': 'test'}
        test_record = self.env['ava.webhook.payload'].create({'data': test_data})
        with self.assertRaises(UserError):
            route.with_context(ava_suppress_error_log=True)._execute_process(
                route._get_model(), test_data, test_headers, test_record)

    def test_execute_defaults(self):
        body, status_code = self.route.execute({'test': 'data'}, {})

        self.assertEqual(body, {'ok': True})
        self.assertEqual(status_code, 200)

    def test_execute_uses_webhook_response(self):
        payload_model = type(self.env['ava.webhook.payload'])

        def webhook_response(self, data, headers, record, route_id):
            return {'quotationId': 42, 'echo': data}, 201

        with patch.object(payload_model, 'webhook_response', webhook_response):
            body, status_code = self.route.execute({'test': 'data'}, {})

        self.assertEqual(body, {'quotationId': 42, 'echo': {'test': 'data'}})
        self.assertEqual(status_code, 201)

    def test_execute_propagates_webhook_error(self):
        payload_model = type(self.env['ava.webhook.payload'])

        def store(self, data, headers, route_id):
            raise WebhookError('Company is not tagged Klient', status_code=422)

        with patch.object(payload_model, 'store', store):
            with self.assertRaises(WebhookError) as err:
                self.route.execute({'test': 'data'}, {})

        self.assertEqual(err.exception.status_code, 422)

    def test_execute_on_discarded_input(self):
        route = self.env['ava.webhook.route'].create({
            'route': 'test-discard-http',
            'model': 'ava.webhook.payload',
            'method_transform': False,
            'transform': textwrap.dedent("""
                discard()
            """),
        })

        body, status_code = route.execute({'test': 'data'}, {})

        self.assertEqual(body, {'ok': True})
        self.assertEqual(status_code, 200)

    def test_concurrency_tuple_covers_what_odoo_retries(self):
        """Odoo added odoo.exceptions.ConcurrencyError as a fourth retryable in 19.0.
        Missing a member means a handler that asks to be retried gets a 500 instead."""
        self.assertIn(psycopg2.errors.SerializationFailure, CONCURRENCY_EXCEPTIONS)
        self.assertIn(psycopg2.errors.DeadlockDetected, CONCURRENCY_EXCEPTIONS)
        self.assertIn(psycopg2.errors.LockNotAvailable, CONCURRENCY_EXCEPTIONS)

        odoo_error = getattr(exceptions, 'ConcurrencyError', None)
        if odoo_error is not None:
            self.assertIn(odoo_error, CONCURRENCY_EXCEPTIONS,
                          'this Odoo version retries ConcurrencyError, so it must be listed')

    def test_execute_resolves_the_model_once(self):
        """Transform, store, process and the reply must run on one model, resolved
        once. Odoo interns Environments so re-deriving it was not a correctness
        problem, but the single resolution is what makes that guarantee readable."""
        route_model = type(self.env['ava.webhook.route'])
        original = route_model._get_model
        calls = []

        def counting(self):
            calls.append(1)
            return original(self)

        with patch.object(route_model, '_get_model', counting):
            self.route.execute({'test': 'data'}, {})

        self.assertEqual(len(calls), 1)

    def test_execute_builds_a_fresh_default_body(self):
        """The default body must not be a constant shared between requests."""
        first, dummy = self.route.execute({'test': 'data'}, {})
        second, dummy = self.route.execute({'test': 'data'}, {})

        self.assertEqual(first, second)
        self.assertIsNot(first, second)
