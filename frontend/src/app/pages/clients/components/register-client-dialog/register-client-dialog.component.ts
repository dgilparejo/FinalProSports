import { Component, inject, signal } from '@angular/core';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from '@components/button/button.component';
import { DatepickerComponent } from '@components/datepicker/datepicker.component';
import { FormComponent } from '@components/form/form.component';
import { InputComponent } from '@components/input/input.component';
import { SelectComponent } from '@components/select/select.component';
import { RegisterClient } from '@models/client';
import { GOALS, Option, RESTRICTIONS } from '@models/common';

/** Registration BY NAME (S9): the identification block of the professional's sheet + what the engine needs. The key is a UUID the
 *  application assigns; the professional never types a code. The rest of the sheet comes next, on the intake page (S3). */
@Component({
  selector: 'app-register-client-dialog',
  imports: [MatDialogModule, TranslatePipe, ButtonComponent, DatepickerComponent, FormComponent, InputComponent, SelectComponent],
  template: `
    <h2 mat-dialog-title>{{ 'register.title' | translate }}</h2>
    <mat-dialog-content>
      <app-form [columns]="2">
        <app-input class="span-2" [label]="'register.name' | translate" [required]="true" [(value)]="fullName" />
        <app-datepicker [label]="'register.birth' | translate" [(value)]="birthDate" />
        <app-select [label]="'register.sex' | translate" [options]="sexes" [(value)]="sex" />
        <app-input [label]="'register.phone' | translate" type="tel" [(value)]="phone" />
        <app-input [label]="'register.email' | translate" type="email" [(value)]="email" />
        <app-input [label]="'register.height' | translate" type="number" [min]="120" [max]="220" suffix="cm" [(value)]="height" />
        <app-input
          [label]="'register.activity' | translate"
          type="number"
          [min]="1"
          [max]="6"
          [(value)]="activity"
          [hint]="'register.activityHint' | translate" />
        <app-select class="span-2" [label]="'register.goal' | translate" [options]="goals" [(value)]="goal" />
        <app-select class="span-2" [label]="'register.restrictions' | translate" [options]="restrictions" [multiple]="true" [(value)]="restrictionsValue" />
      </app-form>
      @if (!valid()) {
        <p class="muted small">{{ 'register.nameRequired' | translate }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <app-button variant="ghost" (clicked)="ref.close()">{{ 'common.cancel' | translate }}</app-button>
      <app-button variant="primary" icon="person_add" [disabled]="!valid()" (clicked)="submit()">{{ 'register.submit' | translate }}</app-button>
    </mat-dialog-actions>
  `,
})
export class RegisterClientDialogComponent {
  readonly ref = inject(MatDialogRef<RegisterClientDialogComponent>);
  readonly goals: Option[] = GOALS;
  readonly restrictions: Option[] = RESTRICTIONS;
  readonly sexes: Option[] = [
    { value: 'M', label: 'Hombre' },
    { value: 'F', label: 'Mujer' },
  ];
  readonly fullName = signal<string | number | null>('');
  readonly birthDate = signal<string | null>(null);
  readonly phone = signal<string | number | null>('');
  readonly email = signal<string | number | null>('');
  readonly sex = signal<string | string[] | null>('M');
  readonly height = signal<string | number | null>(null);
  readonly activity = signal<string | number | null>(4);
  readonly goal = signal<string | string[] | null>('volumen_masa');
  readonly restrictionsValue = signal<string | string[] | null>([]);

  valid(): boolean {
    return String(this.fullName() ?? '').trim().length >= 2;
  }

  submit(): void {
    const text = (v: string | number | null) => String(v ?? '').trim() || null;
    const form: RegisterClient = {
      full_name: String(this.fullName()).trim(),
      birth_date: this.birthDate() || null,
      phone: text(this.phone()),
      email: text(this.email()),
      sex: (this.sex() as 'M' | 'F' | null) ?? null,
      height_cm: this.height() == null ? null : Number(this.height()),
      activity_level: this.activity() == null ? null : Number(this.activity()),
      goal: (this.goal() as string | null) ?? null,
      restrictions: (this.restrictionsValue() as string[]) ?? [],
    };
    this.ref.close(form);
  }
}
