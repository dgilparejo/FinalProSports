import { Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { InputConstants } from '@models/components/input';

import { BaseFormField } from '../base-form-field/base-form-field';

@Component({
  selector: 'app-input',
  host: { '[class.compact]': 'compact()' },
  imports: [FormsModule, MatFormFieldModule, MatInputModule],
  template: `
    <mat-form-field [appearance]="APPEARANCE" [subscriptSizing]="SUBSCRIPT" class="field" [class.compact]="compact()">
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }
      <input
        matInput
        [type]="type()"
        [ngModel]="value()"
        (ngModelChange)="onChange($event)"
        [placeholder]="placeholder()"
        [disabled]="disabled()"
        [required]="required()"
        [min]="min()"
        [max]="max()"
        [step]="type() === 'number' ? NUMBER_STEP : null"
        [class.num]="type() === 'number'" />
      @if (suffix()) {
        <span matTextSuffix class="muted small">{{ suffix() }}</span>
      }
      @if (hint()) {
        <mat-hint>{{ hint() }}</mat-hint>
      }
    </mat-form-field>
  `,
  styles: `
    :host {
      display: block;
    }
    .field {
      width: 100%;
    }
    :host(.compact),
    .compact {
      width: 120px;
      flex: 0 0 120px;
    }
  `,
})
export class InputComponent extends BaseFormField<string | number> {
  readonly type = input<(typeof InputConstants.TYPES)[number]>(InputConstants.DEFAULT_TYPE);
  readonly min = input<number | null>(null);
  readonly max = input<number | null>(null);
  readonly suffix = input<string | null>(null);
  readonly compact = input(false);
  readonly NUMBER_STEP = InputConstants.NUMBER_STEP;

  onChange(v: string | number | null): void {
    if (this.type() === 'number') {
      const n = v === '' || v === null || v === undefined ? null : Number(v);
      this.set(n === null || Number.isNaN(n) ? null : n);
    } else {
      this.set(v === '' ? null : v);
    }
  }
}
