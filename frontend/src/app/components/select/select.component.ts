import { Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';

import { Option } from '@models/common';
import { SelectConstants } from '@models/components/select';

import { BaseFormField } from '../base-form-field/base-form-field';

@Component({
  selector: 'app-select',
  imports: [FormsModule, MatFormFieldModule, MatSelectModule],
  template: `
    <mat-form-field [appearance]="APPEARANCE" [subscriptSizing]="SUBSCRIPT" class="field">
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }
      <mat-select
        [ngModel]="value()"
        (ngModelChange)="set($event)"
        [multiple]="multiple()"
        [disabled]="disabled()"
        [required]="required()"
        [placeholder]="placeholder()">
        @if (allowEmpty() && !multiple()) {
          <mat-option [value]="null">{{ EMPTY_LABEL }}</mat-option>
        }
        @for (o of options(); track o.value) {
          <mat-option [value]="o.value">{{ o.label }}</mat-option>
        }
      </mat-select>
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
  `,
})
export class SelectComponent<T = string> extends BaseFormField<T | T[]> {
  readonly options = input.required<Option<T>[]>();
  readonly multiple = input(false);
  readonly allowEmpty = input(false);
  readonly EMPTY_LABEL = SelectConstants.EMPTY_LABEL;
}
