# Avalah Webhook

This module provides a way to receive webhook notifications from other applications.


## Basics

- Webhooks are managed in the Webhooks app in the main menu.
- Each webhook has a route which is the URL that the webhook will be sent to. A preview of the full URL is shown in the webhook's view.


## Usage

We provide two ways of setting up webhooks:

- Using the `Webhook Payload` model to just start receiving data
    - This allows simply storing the data and/or executing custom logic.
    - You can write custom transform and post-process methods by:
        - setting "Transform method" and "Post-process method" to nothing;
        - or extending the `ava.webhook.payload` model and overriding the `transform` and `process` methods.
    - Each hook can control whether to store the data or just perform custom logic.

- To make any model be populatable by a webhook you can inherit the `ava.webhook.mixin` model and implement the interface below:

```python
class MyWebhookModel(models.Model):
    _name = 'my.webhook.model'
    _inherit = ['ava.webhook.mixin']

    @api.model
    def store(self, data, headers, route_id):
        """
        This is called when the received data has to be stored.
        This method should return the created record of the same type as this model.
        """
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
```
