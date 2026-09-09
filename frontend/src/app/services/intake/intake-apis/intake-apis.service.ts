import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { URLS } from '@env/urls';
import { ClientRecord, LabResultsResponse, NewLabResult, RecordView } from '@models/client';

import { ApiRestService } from '../../api-rest/api-rest.service';

/** Raw calls of the intake area (S3 record + body composition, S4 lab results). */
@Injectable({ providedIn: 'root' })
export class IntakeApisService {
  private readonly api = inject(ApiRestService);

  record(id: string): Observable<RecordView> {
    return this.api.get<RecordView>(URLS.record(id));
  }

  saveRecord(id: string, record: ClientRecord): Observable<RecordView> {
    return this.api.put<RecordView>(URLS.record(id), record);
  }

  importScale(id: string, dump: { users: unknown[]; history: unknown[] }): Observable<RecordView & { measurements_added: number; users_seen: number }> {
    return this.api.post<RecordView & { measurements_added: number; users_seen: number }>(URLS.bodyCompositionImport(id), dump);
  }

  addMeasurement(id: string, body: Record<string, unknown>): Observable<RecordView> {
    return this.api.post<RecordView>(URLS.bodyComposition(id), body);
  }

  labs(id: string): Observable<LabResultsResponse> {
    return this.api.get<LabResultsResponse>(URLS.labResults(id));
  }

  addLabs(id: string, results: NewLabResult[]): Observable<LabResultsResponse> {
    return this.api.post<LabResultsResponse>(URLS.labResults(id), { results });
  }

  importLabs(id: string, content: string, measuredAt: string | null): Observable<LabResultsResponse> {
    return this.api.post<LabResultsResponse>(URLS.labResultsImport(id), { content, measured_at: measuredAt });
  }

  deleteLab(clientId: string, resultId: number): Observable<LabResultsResponse> {
    return this.api.delete<LabResultsResponse>(URLS.labResult(clientId, resultId));
  }
}
