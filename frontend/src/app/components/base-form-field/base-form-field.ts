import { Directive, input, model } from '@angular/core';

import { BaseFormFieldConstants } from '@models/components/base-form-field';

/** Shared contract of every form control wrapper: label, hint, disabled/required flags and a two-way `value` model (signals). */
@Directive()
export abstract class BaseFormField<T> extends BaseFormFieldConstants {
  readonly label = input<string>('');
  readonly hint = input<string | null>(null);
  readonly placeholder = input<string>('');
  readonly disabled = input(false);
  readonly required = input(false);
  readonly value = model<T | null>(null);
  readonly APPEARANCE = BaseFormFieldConstants.APPEARANCE;
  readonly SUBSCRIPT = BaseFormFieldConstants.SUBSCRIPT;

  protected set(v: T | null): void {
    this.value.set(v);
  }
}
