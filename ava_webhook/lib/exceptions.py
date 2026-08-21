import psycopg2.errors

from odoo import exceptions

# The concurrency errors Odoo's own `retrying` retries. A handler must let these
# escape untouched, or the transparent retry becomes a hard 500.
#
# Named here rather than imported from Odoo because the equivalent constant has moved
# and been renamed across supported versions, from
# odoo.service.model.PG_CONCURRENCY_ERRORS_TO_RETRY on 16.0 through 18.0 to
# odoo.sql_db.PG_CONCURRENCY_EXCEPTIONS_TO_RETRY on master.
#
# 19.0 added a fourth, and it is not a psycopg2 error: odoo.exceptions.ConcurrencyError
# is the documented way for application code to ask to be retried. It is absent on 16.0
# through 18.0, hence the lookup rather than a plain import.
_ODOO_CONCURRENCY_ERROR = getattr(exceptions, 'ConcurrencyError', None)

CONCURRENCY_EXCEPTIONS = tuple(klass for klass in (
    psycopg2.errors.LockNotAvailable,
    psycopg2.errors.SerializationFailure,
    psycopg2.errors.DeadlockDetected,
    _ODOO_CONCURRENCY_ERROR,
) if klass is not None)


class WebhookError(Exception):
    """Raised by a webhook handler to control the HTTP status code of the reply.

    Raising it rolls the request back, so a handler that has to keep a record
    despite the failure must write it on a cursor of its own.
    """

    def __init__(self, message, status_code=500, body=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body
