import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { provideNativeDateAdapter } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { DatepickerConstants } from '@models/components/datepicker';

import { BaseFormField } from '../base-form-field/base-form-field';

/** Date field whose model is an ISO date string (what the API exchanges); the picker works with Date objects internally. */
@Component({
  selector: 'app-datepicker',
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatDatepickerModule],
  providers: [provideNativeDateAdapter()],
  template: `
    <mat-form-field [appearance]="APPEARANCE" [subscriptSizing]="SUBSCRIPT" class="field">
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }
      <input
        matInput
        [matDatepicker]="picker"
        [ngModel]="asDate()"
        (ngModelChange)="onDate($event)"
        [disabled]="disabled()"
        [required]="required()"
        [placeholder]="placeholder()" />
      <mat-datepicker-toggle matIconSuffix [for]="picker"></mat-datepicker-toggle>
      <mat-datepicker #picker></mat-datepicker>
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
export class DatepickerComponent extends BaseFormField<string> {
  private cached: { iso: string | null; date: Date | null } = { iso: null, date: null };

  /** Same Date instance for the same ISO value: a fresh object on every change-detection pass would re-trigger ngModel writes. */
  asDate(): Date | null {
    const v = this.value();
    if (v !== this.cached.iso) this.cached = { iso: v, date: v ? new Date(v.slice(0, DatepickerConstants.ISO_LENGTH) + 'T00:00:00') : null };
    return this.cached.date;
  }

  onDate(d: Date | null): void {
    if (!d || Number.isNaN(d.getTime()) || d.getFullYear() < DatepickerConstants.MIN_YEAR) {
      this.set(null);
      return;
    }
    const pad = (n: number) => String(n).padStart(2, '0');
    this.set(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
  }
}
