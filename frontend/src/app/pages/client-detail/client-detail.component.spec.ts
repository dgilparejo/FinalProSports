import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { APP_CONFIG } from '../../app.config';

import { ClientDetailComponent } from './client-detail.component';

describe('ClientDetailComponent', () => {
  it('loads the client, its saved versions and the record view', () => {
    TestBed.configureTestingModule({
      imports: [ClientDetailComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(ClientDetailComponent);
    fixture.componentRef.setInput('id', 'c3');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http
      .expectOne('http://api/v1/clients/c3')
      .flush({ id: 'c3', full_name: 'Enzo Ficticio Demo', sex: 'M', age: 41, restrictions: [], has_medical_restrictions: true });
    http.expectOne('http://api/v1/clients/c3/diets').flush({
      versions: [],
      saved: [
        {
          id: 'c3::e01',
          created_at: '2026-08-26T10:00:00',
          goal: 'ayuno_intermitente',
          strategy: 'case_based_composer',
          edited: false,
          edit_ratio: 0.1,
        },
      ],
    });
    http.expectOne('http://api/v1/clients/c3/record').flush({
      client: {
        id: 'c3',
        full_name: 'Enzo Ficticio Demo',
        sport: 'ciclismo',
        disliked_foods: [{ food_id: 1, canonical_name: 'hígado' }],
        supplements_owned: [],
      },
      record: { identification: { full_name: 'Enzo Ficticio Demo' } },
      measurements: [],
      latest_weight_kg: 84,
      body_composition: { bmi: 27.1, body_fat_pct: null },
      completeness: { algorithm: { ratio: 1, present: [], missing: [], total: 9 }, record: { ratio: 0.8, present: [], missing: [], total: 25 } },
    });
    fixture.detectChanges();
    const c = fixture.componentInstance;
    expect(c.restrictionChips().map((x) => x.tone)).toEqual(['warn']);
    expect(c.dislikedChips()[0].label).toBe('hígado');
    expect(
      c.describe([
        { food_id: 1, canonical_name: 'pollo', text: '', quantity: 200, unit: 'g', alternative_group: 'a' },
        { food_id: 2, canonical_name: 'pavo', text: '', quantity: 200, unit: 'g', alternative_group: 'a' },
      ]),
    ).toBe('200 g pollo / 200 g pavo');
    expect(fixture.nativeElement.textContent).toContain('Enzo Ficticio Demo');
    expect(fixture.nativeElement.textContent).toContain('e01'); // the saved diet is listed by version, never by key
    expect(fixture.nativeElement.textContent).not.toContain('c3::e01');
  });
});
