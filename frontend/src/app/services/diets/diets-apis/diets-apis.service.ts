import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { DietFormat, URLS } from '@env/urls';
import { Proposal, SaveDietBody } from '@models/diet';

import { ApiRestService } from '../../api-rest/api-rest.service';

@Injectable({ providedIn: 'root' })
export class DietsApisService {
  private readonly api = inject(ApiRestService);

  propose(clientId: string, goal: string, k: number): Observable<Proposal> {
    return this.api.post<Proposal>(URLS.propose, { client_id: clientId, goal, k });
  }

  save(body: SaveDietBody): Observable<Proposal & { id: string }> {
    return this.api.post<Proposal & { id: string }>(URLS.diets, body);
  }

  get(id: string): Observable<Proposal & { id: string }> {
    return this.api.get<Proposal & { id: string }>(URLS.diet(id));
  }

  /** The document as a blob. NOT a URL: a URL opened by the browser carries no token (see ApiRestService.getBlob). */
  export(id: string, format: DietFormat): Observable<Blob> {
    return this.api.getBlob(URLS.dietExport(id, format));
  }

  exportUrl(id: string, format: DietFormat): string {
    return this.api.getUrl(URLS.dietExport(id, format));
  }

  pdfUrl(id: string): string {
    return this.api.getUrl(URLS.dietPdf(id));
  }
}
