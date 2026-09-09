import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { APP_CONFIG } from '../../app.config';

import { ClientIntakeComponent } from './client-intake.component';

const VIEW = {
  client: {
    id: 'c1',
    full_name: 'Nora Ficticia Demo',
    sex: 'F',
    age: 34,
    height_cm: 166,
    activity_level: 3,
    goal: 'definicion_grasa',
    restrictions: ['contains_lactose'],
    sport: null,
    disliked_foods: [],
    supplements_owned: [],
  },
  record: { identification: { full_name: null, birth_date: null, phone: null, email: null } },
  measurements: [],
  latest_weight_kg: null,
  body_composition: { body_fat_pct: null, method: null, note: 'faltan medidas', bmi: null, frame_index: null, somatotype_hint: null },
  completeness: {
    algorithm: { ratio: 0.67, present: [], missing: [{ key: 'sport', label: 'deporte' }], total: 9 },
    record: { ratio: 0.1, present: [], missing: [], total: 25 },
    note: 'nota',
  },
};

describe('ClientIntakeComponent', () => {
  it('loads the record view and the labs, patches blocks immutably and saves', () => {
    TestBed.configureTestingModule({
      imports: [ClientIntakeComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(ClientIntakeComponent);
    fixture.componentRef.setInput('id', 'c1');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('http://api/v1/clients/c1/record').flush(VIEW);
    http.expectOne('http://api/v1/clients/c1/lab-results').flush({ rows: [], results: [], out_of_range: 0, total_rows: 0 });
    fixture.detectChanges();
    const c = fixture.componentInstance;
    expect(c.missingAlgorithm().map((x) => x.label)).toEqual(['deporte']);
    const before = c.record();
    c.patch('sports', 'sports', 'running');
    expect(c.record().sports.sports).toBe('running');
    expect(before.sports.sports).toBeNull();
    c.save();
    const put = http.expectOne('http://api/v1/clients/c1/record');
    expect(put.request.method).toBe('PUT');
    expect((put.request.body as { sports: { sports: string } }).sports.sports).toBe('running');
    put.flush({ ...VIEW, matching: { disliked_foods: { matched: [], unmatched: [] }, supplements_owned: { matched: [], unmatched: [] } } });
    expect(c.savedAt()).toBeTruthy();
    expect(c.statusTone('alto')).toBe('danger');
    expect(c.range({ ref_low: 70, ref_high: null } as never)).toBe('70 – —');
  });
});
