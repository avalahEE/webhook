Avalah Webhook
==============

This module provides a way to receive webhook notifications from other applications.

Basics
------

- Webhooks are managed in the Webhooks app in the main menu.
- Each webhook has a route which is the URL that the webhook will be sent to. A preview of the full URL is shown in the webhook's view.

Usage
-----

See https://github.com/avalahEE/avalah-webhook for more documentation.

Endpoint
--------

`POST /webhook/<route>/<key>` replies with real HTTP status codes, so a caller that retries on non-2xx can.

| Situation | Status |
| --- | --- |
| handled | `200`, or whatever the handler chose |
| malformed body | `400` |
| unknown route, bad key, or IP not allowed | `403` |
| handler error | `500` |

The three refusals reply identically on purpose: a caller must not be able to learn whether a route exists or whether its key was accepted. Only the server log tells them apart. The replies are identical, the response *times* are not, so this hides the answer rather than making it unobservable.

A handler controls its own reply in two ways:

- implement `webhook_response(data, headers, record, route_id)` on the model and return a `(body, status_code)` tuple. Its `data` is what `transform` returned, not the request body, so a handler shapes the reply by returning its work from `transform` and reading it back here
- raise `WebhookError(message, status_code=..., body=...)` from `ava_webhook.lib.exceptions` anywhere in `transform`, `store` or `process`

A status outside `200..599` is refused and becomes a `500`.

Transactions
------------

**A status *returned* from `webhook_response` keeps the handler's records; everything else rolls them back.** That covers the three refusals, `WebhookError` even though the handler chose its status, an unhandled exception, an unusable status, and a reply that cannot be serialised.

So a handler that must keep a record even when the request fails has to write it on a cursor of its own. Bear in mind that a write committed that way is not undone if the request fails afterwards, which is the point, but also means it can outlive the records it refers to.

Serialisation failures are re-raised so Odoo's own retry can see them; do not catch bare `Exception` around database work in a handler, or that retry is lost.

Security
--------

Please be advised that the Webhook Admin group (users who can define custom webhook logic) has full access to the entire Odoo via the webhook programming API.
Restrict this to users who are your Odoo admins.

Things to consider:
- If an execution user is not defined for a route, the route will execute with `sudo()` privileges.
- Configure IP allowlists to restrict access to specific IP ranges if possible.
- If the `proxy_mode` Odoo config option is enabled ensure that your reverse proxy strips or explicitly sets the `X-Forwarded-For` header.
- Prefer python methods to customizations done in the web-editor.
- This module does not provide rate or body size limiting - apply this at the edge instead.


Changelog
---------

- 2.0.2
  - License type "MIT" not supported
- 2.0.0
  - Add support for 16.0
  - `POST /webhook/<route>/<key>` now replies with real HTTP status codes instead of wrapping every error in a `200` JSON-RPC envelope
  - Add `webhook_response` mixin method and `WebhookError` for handler-controlled replies
  - Export `CONCURRENCY_EXCEPTIONS` from `ava_webhook.lib.exceptions` so a handler can let Odoo's retry see a concurrency failure instead of swallowing it.
  - Resolve the handler model once per request and hand it to each step, rather than re-deriving it four times
  - Fix: the reply no longer carries a server traceback. Previously any handler error returned `serialize_exception`'s `debug` key to the caller
  - Fix: a non-ASCII key no longer raises inside `hmac.compare_digest`. That was an unauthenticated traceback leak needing only a known route name
  - Fix: an unknown route, a bad key and a denied IP now reply identically. The old `404`/`403` split confirmed to a caller that its key was valid
  - Fix: a failed request no longer commits partial writes

  **BREAKING.** Callers of `POST /webhook/<route>/<key>` must be checked:
  - the success body is no longer a JSON-RPC envelope. `result.ok` is now `ok` at the root
  - handled errors no longer arrive as `200`. They are `400`, `403` and `500`
  - an unknown route or bad key is `403`, previously reported as `404` inside the envelope
  - `ava.webhook.route.execute()` returns a `(body, status_code)` tuple, no longer the stored record
  - `ava.webhook.route.execute_http()` is removed; `execute()` does the same thing
- 1.4.1
  - Fix: fail closed when deactivating or removing IP allowlists
- 1.4.0
  - Add IP allowlists support
  - When proxy mode is enabled, use `X-Forwarded-For` header for request IP detection
- 1.3.1
  - Fix `ava.webhook.payload` display name computation for orphaned records (route is deleted)
  - Fix `ava.webhook.payload` JSON display string computation when re-serialization fails
- 1.3.0
  - Add an option to execute webhooks with a non-sudo user
- 1.2.2
  - Error handling improvements
  - Fix `@api.model` method detection for 19.0 and above
- 1.2.1
  - Fix: do not expose internal error details in webhook responses
- 1.2.0
  - Add tracking to route fields (adds `mail.thread` dependency)
  - Fix logging and indent issues in tests
  - Disable installation for 16.0 (not supported)
- 1.1.1
  - Fix timing attack on key validation
  - Replace key generation with a more cryptographically secure method
  - Fix logging of internal errors in route execution
  - Prevent setting transform and post-process methods to non-allowed methods
  - Corrected `process` and `transform` field types to `Text`
  - Fix deprecated reference to `self._cr`
- 1.1.0
  - Support for 19.0 and above user permissions
  - Remove no longer necessary expand and string attributes from `group` by filters
- 1.0.3
  - Add support for odoo 17
- 1.0.2
  - Support 18.0 sql constraints
- 1.0.1
  - Add key generation
- 1.0.0
  - Initial version
