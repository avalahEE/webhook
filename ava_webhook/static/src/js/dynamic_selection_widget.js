/** @odoo-module **/
// noinspection DuplicatedCode

import {useState} from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { SelectionField, selectionField } from "@web/views/fields/selection/selection_field";

export class DynamicSelectionField extends SelectionField {
    async setup() {
        this.state = useState({
            dynamicOptions: [],
        });

        this.type = this.props.record.fields[this.props.name].type;

        const selection = this.props.record.fields[this.props.name].selection;
        if (!selection || selection.length !== 1) {
            return;
        }

        const [ magic, method ] = selection[0];
        if (magic !== 'selection_dynamic') {
            return;
        }

        this.state.dynamicOptions = await this.props.record.model.orm.call(
            this.props.record.resModel,
            method,
            [],
            {
                context: {
                    ...this.props.record.context,
                    resId: this.props.record.resId,
                    resIds: this.props.record.resIds,
                },
            },
        );
    }

    get options() {
        return this.state.dynamicOptions;
    }
}

export const dynamicSelectionField = {
    ...selectionField,
    component: DynamicSelectionField,
    displayName: _t("Dynamic Selection"),
    supportedTypes: ["selection"],
};

registry.category("fields").add("dynamic-selection", dynamicSelectionField);
