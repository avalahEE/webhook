from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AvaWebhookMixin(models.AbstractModel):
    _name = 'ava.webhook.mixin'
    _description = 'Avalah Webhook Mixin'

    @api.model
    def store(self, data, headers, route_id):
        pass

    @api.model
    def transform(self, data, headers, route_id):
        """
        This is called before the data is stored and allows for customization of transformation.
        A good example is to transform the data into a format that is easier to store
        (e.g. values to pass to create/write).

        This method should return the transformed data or None to discard the event.
        """
        return data

    @api.model
    def process(self, data, headers, record, route_id):
        """
        This is called after the data is stored and allows for customization of post-processing
        (e.g. send a notification).
        """
        pass
