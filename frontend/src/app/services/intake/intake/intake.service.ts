import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ClientRecord, LabResultsResponse, NewBodyMeasurement, NewLabResult, RecordView } from '@models/client';

import { IntakeApisService } from '../intake-apis/intake-apis.service';

/** Domain-facing intake service: parses the scale file and cleans lab rows before calling the APIs. */
@Injectable({ providedIn: 'root' })
export class IntakeService {
  private readonly apis = inject(IntakeApisService);

  record(id: string): Observable<RecordView> {
    return this.apis.record(id);
  }

  saveRecord(id: string, record: ClientRecord): Observable<RecordView> {
    return this.apis.saveRecord(id, record);
  }

  /** The scale export: a JSON object {users, history} or a JSON array of users; anything else is rejected before the call. */
  importScale(id: string, content: string): Observable<RecordView & { measurements_added: number; users_seen: number }> {
    const parsed = JSON.parse(content) as unknown;
    const dump = Array.isArray(parsed) ? { users: parsed, history: [] } : (parsed as { users?: unknown[]; history?: unknown[] });
    return this.apis.importScale(id, { users: dump.users ?? [], history: dump.history ?? [] });
  }

  /** Only the magnitudes the professional actually filled in travel: an empty field is not a zero. */
  addMeasurement(id: string, reading: NewBodyMeasurement): Observable<RecordView> {
    const body = Object.fromEntries(Object.entries(reading).filter(([, v]) => v !== null && v !== undefined && v !== ''));
    return this.apis.addMeasurement(id, body);
  }

  labs(id: string): Observable<LabResultsResponse> {
    return this.apis.labs(id);
  }

  addLabs(id: string, rows: NewLabResult[]): Observable<LabResultsResponse> {
    return this.apis.addLabs(
      id,
      rows.filter((r) => r.marker.trim() && r.value !== null).map((r) => ({ ...r, marker: r.marker.trim(), measured_at: r.measured_at || null })),
    );
  }

  importLabs(id: string, content: string, measuredAt: string | null): Observable<LabResultsResponse> {
    return this.apis.importLabs(id, content, measuredAt);
  }

  deleteLab(clientId: string, resultId: number): Observable<LabResultsResponse> {
    return this.apis.deleteLab(clientId, resultId);
  }
}
