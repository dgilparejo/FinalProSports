import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { URLS } from '@env/urls';
import { Client, RegisterClient } from '@models/client';
import { ClientDiets } from '@models/diet';

import { ApiRestService } from '../../api-rest/api-rest.service';

/** Raw calls of the clients area (S1 portfolio: the case base is never listed here). */
@Injectable({ providedIn: 'root' })
export class ClientsApisService {
  private readonly api = inject(ApiRestService);

  list(): Observable<Client[]> {
    return this.api.get<Client[]>(URLS.clients);
  }

  get(id: string): Observable<Client> {
    return this.api.get<Client>(URLS.client(id));
  }

  register(body: RegisterClient): Observable<Client> {
    return this.api.post<Client>(URLS.clients, body);
  }

  diets(id: string): Observable<ClientDiets> {
    return this.api.get<ClientDiets>(URLS.clientDiets(id));
  }
}
