import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { URLS } from '@env/urls';
import { Food, NewFood, Rule } from '@models/catalog';

import { ApiRestService } from '../../api-rest/api-rest.service';

@Injectable({ providedIn: 'root' })
export class CatalogApisService {
  private readonly api = inject(ApiRestService);

  foods(): Observable<Food[]> {
    return this.api.get<Food[]>(URLS.foods);
  }

  addFood(body: NewFood): Observable<Food> {
    return this.api.post<Food>(URLS.foods, body);
  }

  rules(): Observable<Rule[]> {
    return this.api.get<Rule[]>(URLS.rules);
  }
}
