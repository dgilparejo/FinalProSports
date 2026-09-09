import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { APP_CONFIG } from '../../app.config';

import { DietViewComponent } from './diet-view.component';

describe('DietViewComponent', () => {
  it('renders the saved diet with its routing chips, rules and diff', () => {
    TestBed.configureTestingModule({
      imports: [DietViewComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(DietViewComponent);
    fixture.componentRef.setInput('id', 'c3::e03');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('http://api/v1/catalog/foods').flush([]);
    http.expectOne('http://api/v1/rules?include_low_confidence=true').flush([]);
    http.expectOne('http://api/v1/diets/c3%3A%3Ae03').flush({
      id: 'c3::e03',
      edited: true,
      profile: { client_code: 'c3', goal: 'ayuno_intermitente' },
      client: { id: 'c3', full_name: 'Enzo Ficticio Demo' },
      strategy: 'rotation_composer',
      parameters: {},
      retrieved_case_ids: ['C::v01'],
      meals: [
        {
          slot: 'COMIDA',
          groups: [
            {
              position: 0,
              options: [
                {
                  food_id: 1,
                  canonical_name: 'pollo',
                  normalized_key: 'pollo',
                  text: '',
                  quantity: 200,
                  unit: 'g',
                  alternative_group: null,
                  note: null,
                  evidence: { support: 1, cases: ['C::v01'], rules: [] },
                },
              ],
            },
          ],
        },
      ],
      notes: ['nota'],
      validation: { compliance: 0.8, rules: [{ rule_id: 'agua_2.5L', applicable: true, satisfied: true, enforced: false }], forced_changes: [], warnings: [] },
      routing: {
        code: 'same_goal',
        label: 'Mismo objetivo',
        strategy: 'rotation_composer',
        previous_version: 'c3::e02',
        rotated_items: 3,
        renewal_applied: 0.3,
        renewal_target: 0.27,
        degradation: null,
        k_effective: 20,
        same_goal_cases: 20,
      },
      gap: null,
      diff: {
        items_added: [],
        items_removed: [],
        items_changed: [],
        items_moved: [],
        slots_added: [],
        slots_removed: [],
        notes_added: [],
        notes_removed: [],
        proposed_items: 10,
        kept_unchanged: 9,
        edit_ratio: 0.1,
        is_edited: true,
        summary: { added: 0, removed: 0, changed: 1, moved: 0 },
      },
    });
    fixture.detectChanges();
    const c = fixture.componentInstance;
    expect(c.routingChips().map((x) => x.tone)).toEqual(['rotated', undefined, 'warn']);
    expect(c.ruleChips()[0].tone).toBe('ok');
    expect(c.pdfUrl()).toBe('http://api/v1/diets/c3%3A%3Ae03/pdf');
    expect(fixture.nativeElement.textContent).toContain('200 g pollo');
    expect(c.clientId()).toBe('c3');
    expect(fixture.nativeElement.textContent).toContain('Enzo Ficticio Demo · e03');
    expect(fixture.nativeElement.textContent).not.toContain('c3::e03'); // the key is never shown
  });

  it('exporta el documento POR HttpClient, no con un enlace a la API', () => {
    // El defecto que arregla: los botones eran `<a href>` a la API. Una navegacion del navegador NO pasa por el
    // interceptor de autenticacion, asi que iba sin token y la API contestaba 401 `unauthenticated`. Pasaba con los
    // dos formatos. Aqui se exige que la descarga sea una PETICION, que es lo unico que el interceptor puede firmar.
    TestBed.configureTestingModule({
      imports: [DietViewComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(DietViewComponent);
    fixture.componentRef.setInput('id', 'c3::e03');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('http://api/v1/catalog/foods').flush([]);
    http.expectOne('http://api/v1/rules?include_low_confidence=true').flush([]);
    http.expectOne('http://api/v1/diets/c3%3A%3Ae03').flush({
      id: 'c3::e03',
      profile: { client_code: 'c3', goal: 'volumen_masa' },
      client: { id: 'c3', full_name: 'Enzo Ficticio Demo' },
      strategy: 'case_based_composer',
      parameters: {},
      routing: { code: 'cold_start' },
      retrieved_case_ids: [],
      meals: [],
      notes: [],
    });
    fixture.detectChanges();
    const c = fixture.componentInstance;

    for (const format of ['pdf', 'odt'] as const) {
      c.download(format);
      const req = http.expectOne(`http://api/v1/diets/c3%3A%3Ae03/export?format=${format}`);
      expect(req.request.method).toBe('GET');
      expect(req.request.responseType).toBe('blob'); // sin esto el PDF llegaria como texto y se corromperia
      req.flush(new Blob(['x']));
      expect(c.downloading()).toBeNull();
    }
    expect(c.exportError()).toBeFalse();
  });

  it('marca el error si la descarga falla, en vez de dejar el boton bloqueado', () => {
    TestBed.configureTestingModule({
      imports: [DietViewComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(DietViewComponent);
    fixture.componentRef.setInput('id', 'c3::e03');
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('http://api/v1/catalog/foods').flush([]);
    http.expectOne('http://api/v1/rules?include_low_confidence=true').flush([]);
    http.expectOne('http://api/v1/diets/c3%3A%3Ae03').flush({
      id: 'c3::e03',
      profile: { client_code: 'c3', goal: 'volumen_masa' },
      client: { id: 'c3', full_name: 'Enzo Ficticio Demo' },
      strategy: 'case_based_composer',
      parameters: {},
      routing: { code: 'cold_start' },
      retrieved_case_ids: [],
      meals: [],
      notes: [],
    });
    fixture.detectChanges();
    const c = fixture.componentInstance;
    c.download('pdf');
    http.expectOne('http://api/v1/diets/c3%3A%3Ae03/export?format=pdf').flush(null, { status: 500, statusText: 'x' });
    expect(c.exportError()).toBeTrue();
    expect(c.downloading()).toBeNull(); // el boton vuelve a estar disponible
  });
});
