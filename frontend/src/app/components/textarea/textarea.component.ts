import { TextFieldModule } from '@angular/cdk/text-field';
import { Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { TextareaConstants } from '@models/components/textarea';

import { BaseFormField } from '../base-form-field/base-form-field';

@Component({
  selector: 'app-textarea',
  imports: [FormsModule, MatFormFieldModule, MatInputModule, TextFieldModule],
  template: `
    <mat-form-field [appearance]="APPEARANCE" [subscriptSizing]="SUBSCRIPT" class="field">
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }
      <textarea
        matInput
        cdkTextareaAutosize
        [cdkAutosizeMinRows]="rows()"
        [cdkAutosizeMaxRows]="MAX_ROWS"
        [ngModel]="value()"
        (ngModelChange)="set($event === '' ? null : $event)"
        [placeholder]="placeholder()"
        [disabled]="disabled()"
        [required]="required()"
        [maxlength]="MAX_LENGTH"></textarea>
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
export class TextareaComponent extends BaseFormField<string> {
  readonly rows = input(TextareaConstants.MIN_ROWS);
  readonly MAX_ROWS = TextareaConstants.MAX_ROWS;
  readonly MAX_LENGTH = TextareaConstants.MAX_LENGTH;
}
