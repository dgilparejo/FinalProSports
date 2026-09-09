import { Component, input, output } from '@angular/core';

import { FormConstants } from '@models/components/form';

/** Grid layout for form fields (8 px rhythm) with a submit hook; fields are projected. `.span-2` on a child spans two columns. */
@Component({
  selector: 'app-form',
  template: `
    <form
      class="form"
      [style.grid-template-columns]="'repeat(' + columns() + ', minmax(0, 1fr))'"
      [style.gap.px]="GAP_PX"
      (ngSubmit)="submitted.emit()"
      (submit)="$event.preventDefault(); submitted.emit()">
      <ng-content />
    </form>
  `,
  styles: `
    :host {
      display: block;
    }
    .form {
      display: grid;
      align-items: start;
    }
    ::ng-deep .form > .span-2 {
      grid-column: span 2;
    }
    ::ng-deep .form > .span-all {
      grid-column: 1 / -1;
    }
  `,
})
export class FormComponent extends FormConstants {
  readonly columns = input<(typeof FormConstants.COLUMNS)[number]>(FormConstants.DEFAULT_COLUMNS);
  readonly submitted = output<void>();
  readonly GAP_PX = FormConstants.GAP_PX;
}
