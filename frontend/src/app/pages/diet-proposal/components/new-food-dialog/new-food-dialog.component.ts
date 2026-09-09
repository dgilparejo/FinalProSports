import { Component, computed, inject, signal } from '@angular/core';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { TranslatePipe } from '@ngx-translate/core';

import { AutocompleteComponent } from '@components/autocomplete/autocomplete.component';
import { ButtonComponent } from '@components/button/button.component';
import { FormComponent } from '@components/form/form.component';
import { InputComponent } from '@components/input/input.component';
import { SelectComponent } from '@components/select/select.component';
import { NewFood } from '@models/catalog';
import { ALLERGEN_FLAGS, FLAG_LABELS, FOOD_GROUPS, RULE_FLAGS } from '@models/common';
import { AppStoreService } from '@services/store/app-store.service';

/** Register a food the catalogue lacks (S5): canonical name, family, group(s) and the 14 mandatory flags — every flag is an explicit choice. */
@Component({
  selector: 'app-new-food-dialog',
  imports: [MatDialogModule, MatCheckboxModule, TranslatePipe, AutocompleteComponent, ButtonComponent, FormComponent, InputComponent, SelectComponent],
  template: `
    <h2 mat-dialog-title>{{ 'newFood.title' | translate }}</h2>
    <mat-dialog-content>
      <p class="muted small">{{ 'newFood.hint' | translate }}</p>
      <app-form [columns]="2">
        <app-input [label]="'newFood.name' | translate" [(value)]="name" placeholder="tempeh" />
        <app-input [label]="'newFood.family' | translate" [(value)]="family" [hint]="'newFood.familyHint' | translate" />
        <app-autocomplete class="span-2" [label]="'newFood.familyPick' | translate" [options]="familyOptions()" (selected)="family.set($event.label)" />
        <app-select [label]="'newFood.group' | translate" [options]="groups" [(value)]="group" />
        <app-select [label]="'newFood.secondary' | translate" [options]="groups" [allowEmpty]="true" [(value)]="secondary" />
        <app-input class="span-2" [label]="'newFood.synonyms' | translate" [(value)]="synonyms" [hint]="'newFood.synonymsHint' | translate" />
      </app-form>
      <h3>{{ 'newFood.allergens' | translate }}</h3>
      <div class="flags">
        @for (f of allergenFlags; track f) {
          <mat-checkbox [checked]="flags()[f]" (change)="toggle(f, $event.checked)">{{ labels[f] }}</mat-checkbox>
        }
      </div>
      <h3>{{ 'newFood.ruleFlags' | translate }}</h3>
      <div class="flags">
        @for (f of ruleFlags; track f) {
          <mat-checkbox [checked]="flags()[f]" (change)="toggle(f, $event.checked)">{{ labels[f] }}</mat-checkbox>
        }
      </div>
      <p class="faint small">{{ 'newFood.flagsNote' | translate }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <app-button variant="ghost" (clicked)="ref.close()">{{ 'common.cancel' | translate }}</app-button>
      <app-button variant="primary" icon="add" [disabled]="!valid()" (clicked)="submit()">{{ 'newFood.submit' | translate }}</app-button>
    </mat-dialog-actions>
  `,
  styles: `
    .flags {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 0 12px;
    }
    h3 {
      margin: 12px 0 4px;
    }
  `,
})
export class NewFoodDialogComponent {
  readonly ref = inject(MatDialogRef<NewFoodDialogComponent>);
  private readonly store = inject(AppStoreService);
  readonly groups = FOOD_GROUPS;
  readonly labels = FLAG_LABELS;
  readonly allergenFlags = ALLERGEN_FLAGS;
  readonly ruleFlags = RULE_FLAGS;
  readonly name = signal<string | number | null>('');
  readonly family = signal<string | number | null>('');
  readonly group = signal<string | string[] | null>('PROTEIN');
  readonly secondary = signal<string | string[] | null>(null);
  readonly synonyms = signal<string | number | null>('');
  readonly flags = signal<Record<string, boolean>>(Object.fromEntries([...ALLERGEN_FLAGS, ...RULE_FLAGS].map((f) => [f, false])));
  readonly familyOptions = computed(() => this.store.families().map((f, i) => ({ value: i, label: f })));

  toggle(flag: string, checked: boolean): void {
    this.flags.update((f) => ({ ...f, [flag]: checked }));
  }

  valid(): boolean {
    return String(this.name() ?? '').trim().length >= 2 && String(this.family() ?? '').trim().length >= 2 && !!this.group();
  }

  submit(): void {
    const body: NewFood = {
      canonical_name: String(this.name()).trim().toLowerCase(),
      family: String(this.family()).trim().toLowerCase(),
      group: String(this.group()),
      secondary_group: (this.secondary() as string | null) || null,
      flags: this.flags(),
      synonyms: String(this.synonyms() ?? '')
        .split(/[,;]/)
        .map((s) => s.trim())
        .filter(Boolean),
    };
    this.ref.close(body);
  }
}
