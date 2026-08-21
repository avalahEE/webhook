from odoo import models, api


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

    @api.model
    def webhook_response(self, data, headers, record, route_id):
        """
        This lets the handler dictate the reply. Return a (body, status_code)
        tuple, or None for the default ({'ok': True}, 200). It is not called when
        `transform` discarded the event, which always replies with the default.

        `data` is what `transform` returned, not the request body. A handler that
        needs to shape the reply from its own work therefore returns that work from
        `transform` and reads it back here.

        A status outside 200..599 is refused and becomes a 500 with the request
        rolled back. A non-2xx returned here without raising keeps the handler's
        records, unlike every other way of producing an error reply.
        """
        return None
