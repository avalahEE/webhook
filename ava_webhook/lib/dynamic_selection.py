from odoo import fields
from odoo.release import version_info

if version_info[:2] < (18, 0):
    # noinspection PyPep8Naming,PyUnresolvedReferences
    from odoo.fields import Default as SENTINEL
else:
    # noinspection PyProtectedMember
    from odoo.tools.misc import SENTINEL

import logging
logger = logging.getLogger(__name__)


class DynamicSelection(fields.Selection):
    def __init__(self, selection_dynamic=SENTINEL, string=SENTINEL, **kwargs):
        super(DynamicSelection, self).__init__(
            selection=[('selection_dynamic', selection_dynamic)],
            selection_dynamic=selection_dynamic,
            string=string,
            **kwargs)
        self.selection_dynamic = selection_dynamic

    def convert_to_cache(self, value, record, validate=True):
        if not validate:
            return value or None
        if value and self.column_type[0] == 'int4':
            value = int(value)
        if not value:
            return None
        return value
