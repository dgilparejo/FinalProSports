import { Injectable, computed, signal } from '@angular/core';

import { Food, Rule } from '@models/catalog';

/** Signal store of the reference data every page needs (catalogue, rules). Pages read computed views; services write. */
@Injectable({ providedIn: 'root' })
export class AppStoreService {
  readonly foods = signal<Food[]>([]);
  readonly rules = signal<Rule[]>([]);

  readonly foodById = computed(() => new Map(this.foods().map((f) => [f.id, f])));
  readonly ruleById = computed(() => new Map(this.rules().map((r) => [r.id, r])));
  readonly families = computed(() =>
    [
      ...new Set(
        this.foods()
          .map((f) => f.family)
          .filter((f): f is string => !!f),
      ),
    ].sort(),
  );

  foodName(id: number | null | undefined): string {
    return (id != null && this.foodById().get(id)?.canonical_name) || '';
  }

  ruleText(id: string): string {
    return this.ruleById().get(id)?.statement ?? '';
  }
}
