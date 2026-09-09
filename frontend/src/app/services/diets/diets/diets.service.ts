import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { toSaveBody } from '@converters/proposal/proposal.converter';
import { Proposal } from '@models/diet';

import { DietFormat } from '@env/urls';

import { DietsApisService } from '../diets-apis/diets-apis.service';

@Injectable({ providedIn: 'root' })
export class DietsService {
  private readonly apis = inject(DietsApisService);

  propose(clientId: string, goal: string, k = 20): Observable<Proposal> {
    return this.apis.propose(clientId, goal, k);
  }

  /** Saves the edited proposal together with the untouched original so that the backend records the diff (S5). */
  save(edited: Proposal, original: Proposal | null): Observable<Proposal & { id: string }> {
    return this.apis.save(toSaveBody(edited, original));
  }

  get(id: string): Observable<Proposal & { id: string }> {
    return this.apis.get(id);
  }

  export(id: string, format: DietFormat): Observable<Blob> {
    return this.apis.export(id, format);
  }

  exportUrl(id: string, format: DietFormat): string {
    return this.apis.exportUrl(id, format);
  }

  pdfUrl(id: string): string {
    return this.apis.pdfUrl(id);
  }
}
