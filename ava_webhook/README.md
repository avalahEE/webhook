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

Security
--------

Please be advised that the Webhook Admin group (users who can define custom webhook logic) has full access to the entire Odoo via the webhook programming API.
Restrict this to users who are your Odoo admins.

Things to consider:
- If an execution user is not defined for a route, the route will execute with `sudo()` privileges.
- Configure IP allowlists to restrict access to specific IP ranges.
- Prefer python methods to customizations done in the web-editor.


Changelog
---------

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
