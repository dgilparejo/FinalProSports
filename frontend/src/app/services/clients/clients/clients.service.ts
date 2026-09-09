import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { toClient, toClients } from '@converters/client/client.converter';
import { Client, RegisterClient } from '@models/client';
import { ClientDiets } from '@models/diet';

import { ClientsApisService } from '../clients-apis/clients-apis.service';

/** Domain-facing clients service: applies the converters and the portfolio ordering (documented clients first). */
@Injectable({ providedIn: 'root' })
export class ClientsService {
  private readonly apis = inject(ClientsApisService);

  list(): Observable<Client[]> {
    return this.apis
      .list()
      .pipe(map((rows) => toClients(rows).sort((a, b) => (b.diet_count ?? 0) - (a.diet_count ?? 0) || (a.full_name ?? '').localeCompare(b.full_name ?? ''))));
  }

  get(id: string): Observable<Client> {
    return this.apis.get(id).pipe(map(toClient));
  }

  register(body: RegisterClient): Observable<Client> {
    return this.apis.register({ ...body, full_name: body.full_name.trim() }).pipe(map(toClient));
  }

  diets(id: string): Observable<ClientDiets> {
    return this.apis.diets(id);
  }
}
