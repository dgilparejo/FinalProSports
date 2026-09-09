import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { Food, NewFood, Rule } from '@models/catalog';

import { AppStoreService } from '../../store/app-store.service';
import { CatalogApisService } from '../catalog-apis/catalog-apis.service';

/** Catalogue and rules, cached in the store (they change only when the professional adds a food). */
@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly apis = inject(CatalogApisService);
  private readonly store = inject(AppStoreService);

  loadFoods(): Observable<Food[]> {
    return this.apis.foods().pipe(tap((foods) => this.store.foods.set(foods)));
  }

  loadRules(): Observable<Rule[]> {
    return this.apis.rules().pipe(tap((rules) => this.store.rules.set(rules)));
  }

  addFood(body: NewFood): Observable<Food> {
    return this.apis.addFood(body).pipe(tap((food) => this.store.foods.update((fs) => [...fs, food])));
  }

  ensureLoaded(): void {
    if (!this.store.foods().length) this.loadFoods().subscribe();
    if (!this.store.rules().length) this.loadRules().subscribe();
  }
}
