from ..lib.dynamic_selection import DynamicSelection
from ..controllers.webhook import AvaWebhookController
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval
from odoo.release import version_info
import logging

_logger = logging.getLogger(__name__)

DEFAULT_TRANSFORM_EXPRESSION = """
# Available variables:
# ---------------------
# input_data          - the data received from the webhook
# model               - the data model of this route
#
# Available functions:
# ---------------------
# emit(data)          - emits the data to the next step
#                       last emit() will be the output of the transform
# discard()           - discards this webhook call and no further
#                       processing will be done
# log(message, *args) - logs a message
#
# Example:
# ---------------------
# if not input_data:
#     discard()
# else:
#     data = ... do something with input_data ...
#     emit(data)
""".strip()

DEFAULT_PROCESS_EXPRESSION = """
# Available variables:
# ---------------------
# record     - the record that was created after transform and store
# model      - the data model of this route
#
# Example:
# ---------------------
# if record:
#     log('Record created', record)
#     ... do something with record ...
""".strip()

API_MODEL_KEY = '_api_model'
SAFE_EVAL_DEFAULTS = {}

if version_info[:2] <= (18, 0):
    API_MODEL_KEY = '_api'
    SAFE_EVAL_DEFAULTS['nocopy'] = True


def is_api_model_method(model, method_name: str):
    method = getattr(model, method_name, None)
    if not method:
        return False
    if version_info[:2] <= (18, 0):
        return getattr(method, API_MODEL_KEY, None) == 'model'
    return getattr(method, API_MODEL_KEY, False) is True


# Extends UserError because `safe_eval` replaces any Exceptions by ValueError.
class DiscardException(UserError):
    pass


class AvaWebhookRoute(models.Model):
    _name = 'ava.webhook.route'
    _description = 'Avalah Webhook Route'
    _rec_name = 'route'
    _inherit = ['mail.thread']

    if version_info[:2] > (18, 0):
        _route_uniq = models.Constraint('unique (route)', 'Routes must be unique.')
    else:
        _sql_constraints = [
            ('route_uniq', 'unique (route)', 'Routes must be unique.'),
        ]

    url_preview = fields.Char(string='URL Preview', compute='_compute_url_preview')

    active = fields.Boolean(string='Active', default=True, tracking=True)

    route = fields.Char(
        string='Route', required=True, tracking=True,
        help='The route to listen to (e.g. my-route will listen on /webhook/my-route/<key>). Must be unique.',
    )

    store = fields.Boolean(
        string='Store', default=False, tracking=True,
        help='If true, the data will be stored in the database.',
    )

    model = fields.Selection(
        selection='_list_all_models', string='Model', required=True, tracking=True,
        help='The model to use for this route.',
    )

    execution_user_id = fields.Many2one(
        'res.users', string='Execution User',
        domain=[('share', '=', False)], tracking=True,
        help='The internal user used to execute webhook transform, store, and post-process operations.',
    )

    method_transform = DynamicSelection(selection_dynamic='list_methods', string='Transform Method', default='transform', tracking=True)
    method_process = DynamicSelection(selection_dynamic='list_methods', string='Post-process Method', default='process', tracking=True)

    transform = fields.Text(
        string='Transform',
        default=DEFAULT_TRANSFORM_EXPRESSION,
        help='This expression can be used to transform the data received from the webhook into the data that will be stored in the database.',
    )

    process = fields.Text(
        string='Post-process',
        default=DEFAULT_PROCESS_EXPRESSION,
        help='This expression is run after the data is stored in the database.',
    )

    key_ids = fields.One2many('ava.webhook.key', 'route_id', string='Keys')
    ip_allowlist_ids = fields.Many2many(
        'ava.webhook.ip.allowlist', 'ava_webhook_route_ip_allowlist_rel',
        'route_id', 'allowlist_id', string='IP Allowlists',
        help='If set, webhook requests for this route are accepted only from IPs matching at least one active allowlist.',
    )

    def is_ip_allowed(self, ip_address):
        self.ensure_one()
        active_allowlists = self.ip_allowlist_ids.filtered('active')
        if not active_allowlists:
            return True
        return any(allowlist.allows_ip(ip_address) for allowlist in active_allowlists)

    @api.model
    def _list_all_models(self):
        try:
            query = "SELECT model, COALESCE(name->>%s, name->>'en_US') as name FROM ir_model WHERE is_ava_webhook = true ORDER BY model"
            self.env.cr.execute(query, [self.env.lang or 'en_US'])
            options = self.env.cr.fetchall()
            return options
        except Exception as err:
            _logger.warning(f'webhook: _list_all_models() failed: {err}')
            return []

    @api.model
    def list_methods(self):
        res_id = self.env.context.get('resId', [])
        if not res_id:
            return []
        return [(attr, attr) for attr in self.get_allowed_methods(self.browse(res_id).model)]

    @api.model
    def get_allowed_methods(self, model_name):
        if model_name not in self.env:
            return []

        model = self.env[model_name]
        methods = []
        for attr in dir(model):
            if attr.startswith('_') or not callable(getattr(model, attr)):
                continue

            if is_api_model_method(model, attr):
                methods.append(attr)

        return sorted(methods)

    @api.onchange('model')
    def _onchange_model(self):
        if self.model:
            self.method_transform = 'transform'
            self.method_process = 'process'

    @api.constrains('method_transform', 'method_process')
    def _check_methods(self):
        for record in self:
            allowed = record.get_allowed_methods(record.model)
            if record.method_transform and record.method_transform not in allowed:
                raise ValidationError(_('Method "%s" is not allowed on model "%s"', record.method_transform, record.model))
            if record.method_process and record.method_process not in allowed:
                raise ValidationError(_('Method "%s" is not allowed on model "%s"', record.method_process, record.model))

    def execute(self, data, headers):
        self.ensure_one()
        _logger.info(f'webhook triggered: {self.route}')
        if not self.model:
            raise UserError(_('Route "%s": model is not set', self.route))
        if self.model not in self.env:
            raise UserError(_('Route "%s": model "%s" not found', self.route, self.model))

        transformed_data = self._execute_transform(data, headers)
        if transformed_data is None:
            _logger.info(f'webhook {self.route} discarded input data')
            return None

        record = None
        if self.store:
            model = self._get_model()
            record = model.store(transformed_data, headers, self.id)
        self._execute_process(transformed_data, headers, record)
        return record

    def _execute_transform(self, data, headers):
        model = self._get_model()
        if self.method_transform in self.get_allowed_methods(self.model):
            method_transform = getattr(model, self.method_transform)
            return method_transform(data, headers, self.id)

        transformed_data = None

        def emit(data):
            nonlocal transformed_data
            transformed_data = data

        def log(message, *args):
            message = f'[{self.route}] {message}'
            _logger.info(message, *args)

        def discard():
            raise DiscardException('discard')

        localdict = dict(
            input_data=data,
            headers=headers,
            model=model,
            emit=emit,
            log=log,
            discard=discard,
        )
        try:
            safe_eval(self.transform or '', localdict, mode='exec', **SAFE_EVAL_DEFAULTS)
            return transformed_data
        except DiscardException:
            return None
        except Exception as e:
            _logger.info(f'webhook: {self.route} - transform() raised an error: {e}')
            if not self.env.context.get('ava_suppress_error_log', False):
                _logger.exception(e)
            raise UserError(_('Route "%s": transform expression caused an internal error', self.route))

    def _execute_process(self, data, headers, record):
        assert self.model
        model = self._get_model()
        if self.method_process in self.get_allowed_methods(self.model):
            method_process = getattr(model, self.method_process)
            return method_process(data, headers, record, self.id)

        def log(message, *args):
            message = f'[{self.route}] {message}'
            _logger.info(message, *args)

        localdict = dict(
            input_data=data,
            record=record,
            model=model,
            headers=headers,
            log=log,
        )
        try:
            safe_eval(self.process or '', localdict, mode='exec', **SAFE_EVAL_DEFAULTS)
        except Exception as e:
            _logger.info(f'webhook: {self.route} - process() raised an error: {e}')
            if not self.env.context.get('ava_suppress_error_log', False):
                _logger.exception(e)
            raise UserError(_('Route "%s": post-process expression caused an internal error', self.route))

    def _get_model(self):
        self.ensure_one()
        assert self.model
        model = self.env[self.model]
        return model.with_user(self.execution_user_id) if self.execution_user_id else model

    def _compute_url_preview(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        for record in self:
            record.url_preview = f'{base_url}{AvaWebhookController._endpoint}/{record.route}/<key>'
