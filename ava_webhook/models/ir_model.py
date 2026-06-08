from odoo import models, fields
import logging

_logger = logging.getLogger(__name__)


class IrModel(models.Model):
    _inherit = 'ir.model'
    _order = 'is_ava_webhook DESC, name ASC'

    is_ava_webhook = fields.Boolean(
        string="Is Avalah Webhook Model", default=False,
    )

    def _reflect_model_params(self, model):
        vals = super(IrModel, self)._reflect_model_params(model)
        vals['is_ava_webhook'] = model._name != 'ava.webhook.mixin' and isinstance(model, self.pool['ava.webhook.mixin'])
        return vals
