import { Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatAutocompleteModule, MatAutocompleteSelectedEvent } from '@angular/material/autocomplete';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

import { AutocompleteConstants } from '@models/components/autocomplete';

export interface AutocompleteOption<T = number> {
  value: T;
  label: string;
  hint?: string | null;
}

/** Text box with a filtered option list (catalogue foods with family and group). Emits the chosen option; the text is only a filter. */
@Component({
  selector: 'app-autocomplete',
  imports: [FormsModule, MatFormFieldModule, MatInputModule, MatAutocompleteModule],
  template: `
    <mat-form-field appearance="outline" subscriptSizing="dynamic" class="field">
      @if (label()) {
        <mat-label>{{ label() }}</mat-label>
      }
      <input matInput [ngModel]="query()" (ngModelChange)="query.set($event)" [matAutocomplete]="auto" [placeholder]="placeholder()" [disabled]="disabled()" />
      <mat-autocomplete #auto (optionSelected)="pick($event)" [displayWith]="display">
        @for (o of filtered(); track o.value) {
          <mat-option [value]="o"
            ><span>{{ o.label }}</span>
            @if (o.hint) {
              <span class="hint muted small">{{ o.hint }}</span>
            }
          </mat-option>
        }
      </mat-autocomplete>
    </mat-form-field>
  `,
  styles: `
    :host {
      display: block;
    }
    .field {
      width: 100%;
    }
    .hint {
      margin-left: 8px;
    }
  `,
})
export class AutocompleteComponent<T = number> extends AutocompleteConstants {
  readonly options = input.required<AutocompleteOption<T>[]>();
  readonly label = input('');
  readonly placeholder = input('');
  readonly disabled = input(false);
  readonly selected = output<AutocompleteOption<T>>();
  readonly query = signal('');
  readonly filtered = computed(() => {
    const q = this.normalise(this.query());
    if (q.length < AutocompleteConstants.MIN_CHARS) return this.options().slice(0, AutocompleteConstants.MAX_OPTIONS);
    const starts = this.options().filter((o) => this.normalise(o.label).startsWith(q));
    const contains = this.options().filter((o) => !starts.includes(o) && (this.normalise(o.label).includes(q) || this.normalise(o.hint ?? '').includes(q)));
    return [...starts, ...contains].slice(0, AutocompleteConstants.MAX_OPTIONS);
  });
  readonly display = (o: AutocompleteOption<T> | string | null): string => (typeof o === 'string' ? o : (o?.label ?? ''));

  pick(e: MatAutocompleteSelectedEvent): void {
    this.selected.emit(e.option.value as AutocompleteOption<T>);
    this.query.set('');
  }

  normalise(s: string): string {
    return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  }
}
