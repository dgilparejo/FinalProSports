import { TestBed } from '@angular/core/testing';

import { AppStoreService } from './app-store.service';

describe('AppStoreService', () => {
  it('indexes foods and rules and lists families', () => {
    const store = TestBed.inject(AppStoreService);
    store.foods.set([
      { id: 1, canonical_name: 'pollo', family: 'ave', group: 'PROTEIN', secondary_group: null, flags: {}, created_by_professional: false, synonyms: [] },
      { id: 2, canonical_name: 'arroz', family: 'arroz', group: 'CARB', secondary_group: null, flags: {}, created_by_professional: false, synonyms: [] },
    ]);
    store.rules.set([
      {
        id: 'agua_2.5L',
        statement: 'Beber 2,5 litros',
        scope: 'global',
        status: 'kept',
        confidence: 'high',
        n_support: 1,
        lift: null,
        adjusted: null,
        enabled: true,
      },
    ]);
    expect(store.foodName(2)).toBe('arroz');
    expect(store.foodName(99)).toBe('');
    expect(store.families()).toEqual(['arroz', 'ave']);
    expect(store.ruleText('agua_2.5L')).toBe('Beber 2,5 litros');
  });
});
