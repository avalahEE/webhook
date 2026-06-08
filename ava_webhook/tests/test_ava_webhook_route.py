from odoo.tests import common
from odoo.exceptions import UserError, ValidationError
from odoo.tools import config
from ..controllers.webhook import AvaWebhookController
import textwrap
import logging

_logger = logging.getLogger(__name__)


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
        result = route._execute_transform({'test': 'data'}, test_headers)
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

        result = route._execute_transform(test_data, test_headers)
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

        record = route.sudo().execute({'test': 'data'}, {'X-Test': 'test'})

        self.assertFalse(record)
        self.assertEqual(route.sudo()._execute_transform({}, {}), {'uid': user.id})

    def test_route_without_allowlists_allows_any_ip(self):
        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))

    def test_route_allows_ip_from_allowlist(self):
        allowlist = self.env['ava.webhook.ip.allowlist'].create({
            'name': 'Office',
            'line_ids': [(0, 0, {'ip_range': '203.0.113.0/24'})],
        })
        self.route.ip_allowlist_ids = [(6, 0, allowlist.ids)]

        self.assertTrue(self.route.is_ip_allowed('203.0.113.10'))
        self.assertFalse(self.route.is_ip_allowed('198.51.100.10'))

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
            route.with_context(ava_suppress_error_log=True)._execute_transform({'test': 'data'}, test_headers)


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
        route._execute_process(test_data, test_headers, test_record)

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
        route._execute_process(test_data, test_headers, test_record)

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
            route.with_context(ava_suppress_error_log=True)._execute_process(test_data, test_headers, test_record)
