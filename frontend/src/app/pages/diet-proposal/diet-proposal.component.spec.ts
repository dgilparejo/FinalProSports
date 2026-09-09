import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { newOption } from '@converters/proposal/proposal.converter';
import { Proposal } from '@models/diet';

import { APP_CONFIG } from '../../app.config';

import { DietProposalComponent } from './diet-proposal.component';

const PROPOSAL: Proposal = {
  profile: { client_code: 'c1', goal: 'definicion_grasa' },
  client: { id: 'c1', full_name: 'Nora Ficticia Demo' },
  strategy: 'case_based_composer',
  parameters: { k: 20, plausibility: { applied: true, changes: [] } },
  retrieved_case_ids: ['C::v01', 'C::v02'],
  meals: [
    {
      slot: 'COMIDA',
      groups: [
        { position: 0, options: [{ ...newOption(1, 'pollo', 200, 'g'), evidence: { support: 0.9, cases: ['C::v01', 'C::v02'], rules: [] } }] },
        { position: 1, options: [{ ...newOption(2, 'arroz', 150, 'g'), evidence: { support: 0.5, cases: ['C::v01'], rules: [] } }] },
      ],
    },
    { slot: 'CENA', groups: [{ position: 0, options: [{ ...newOption(3, 'salmón', 180, 'g'), evidence: { support: 0.6, cases: ['C::v02'], rules: [] } }] }] },
  ],
  notes: ['Beber 2,5 litros de agua'],
  validation: { compliance: 0.9, rules: [{ rule_id: 'agua_2.5L', applicable: true, satisfied: true, enforced: false }], forced_changes: [], warnings: [] },
  routing: {
    code: 'cold_start',
    label: 'Sin historial',
    strategy: 'case_based_composer',
    previous_version: null,
    rotated_items: null,
    renewal_applied: null,
    renewal_target: null,
    degradation: 'none',
    k_effective: 20,
    same_goal_cases: 20,
  },
  gap: null,
  owned_supplements: [],
  context: { lab_results: { results: [], out_of_range: 0, total_rows: 0 } },
};

describe('DietProposalComponent', () => {
  let http: HttpTestingController;

  function setup() {
    TestBed.configureTestingModule({
      imports: [DietProposalComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
      ],
    });
    const fixture = TestBed.createComponent(DietProposalComponent);
    fixture.componentRef.setInput('id', 'c1');
    fixture.detectChanges();
    http = TestBed.inject(HttpTestingController);
    http.expectOne('http://api/v1/catalog/foods').flush([
      {
        id: 9,
        canonical_name: 'brócoli',
        family: 'verdura',
        group: 'VEGETABLE',
        secondary_group: null,
        flags: {},
        created_by_professional: false,
        synonyms: [],
      },
    ]);
    http.expectOne('http://api/v1/rules?include_low_confidence=true').flush([]);
    http
      .expectOne('http://api/v1/clients/c1')
      .flush({ id: 'c1', full_name: 'Nora Ficticia Demo', sex: 'F', age: 34, goal: 'definicion_grasa', restrictions: ['contains_lactose'] });
    http.expectOne('http://api/v1/clients/c1/diets').flush({ versions: [], saved: [] });
    fixture.detectChanges();
    return fixture;
  }

  it('generates, edits in line without touching the original, and saves original + edited', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    expect(c.goal()).toBe('definicion_grasa');
    c.generate();
    const propose = http.expectOne('http://api/v1/diets/propose');
    expect((propose.request.body as { client_id: string }).client_id).toBe('c1'); // S9: the key travels, the name never enters the engine
    propose.flush(PROPOSAL);
    fixture.detectChanges();
    expect(c.itemCount()).toBe(3);
    c.setQuantity('COMIDA', 0, 0, 180);
    c.removeOption('COMIDA', 1, 0);
    c.moveOption('CENA', 0, 0, 'MERIENDA');
    c.addFood('CENA', { value: 9, label: 'brócoli' });
    c.addNote();
    c.newNote.set('Masticar despacio');
    c.addNote();
    const p = c.proposal()!;
    expect(p.meals.find((m) => m.slot === 'COMIDA')!.groups[0].options[0].quantity).toBe(180);
    expect(p.meals.find((m) => m.slot === 'COMIDA')!.groups.length).toBe(1);
    expect(p.meals.map((m) => m.slot)).toEqual(['COMIDA', 'MERIENDA', 'CENA']);
    expect(c.isAddition(p.meals.find((m) => m.slot === 'CENA')!.groups[0].options[0], 'CENA')).toBeTrue();
    expect(p.notes).toEqual(['Beber 2,5 litros de agua', 'Masticar despacio']);
    expect(c.original()!.meals[0].groups[0].options[0].quantity).toBe(200); // untouched: the diff needs it
    c.save();
    const req = http.expectOne('http://api/v1/diets');
    const body = req.request.body as { edited: boolean; original: { meals: unknown[] } | null; meals: unknown[] };
    expect(body.edited).toBeTrue();
    expect(body.original!.meals.length).toBe(2);
    expect(body.meals.length).toBe(3);
    req.flush({ ...PROPOSAL, id: 'c1::e01' });
  });

  it('adds a food as an ALTERNATIVE of an existing row, not as a new row', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    c.generate();
    http.expectOne('http://api/v1/diets/propose').flush(PROPOSAL);
    fixture.detectChanges();

    const comida = () => c.proposal()!.meals.find((m) => m.slot === 'COMIDA')!;
    expect(comida().groups.length).toBe(2);

    // Group 0 is «200 g pollo». The broccoli joins THAT row instead of opening a third one.
    c.addFood('COMIDA', { value: 9, label: 'brócoli' }, 0);

    expect(comida().groups.length).toBe(2); // no new row
    expect(comida().groups[0].options.map((o) => o.canonical_name)).toEqual(['pollo', 'brócoli']);
    expect(comida().groups[1].options.map((o) => o.canonical_name)).toEqual(['arroz']); // the other row is untouched
    expect(c.isAddition(comida().groups[0].options[1], 'COMIDA')).toBeTrue();
    expect(c.itemCount()).toBe(4);
  });

  it('without a target group it keeps opening a new row: the two ways stay distinct', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    c.generate();
    http.expectOne('http://api/v1/diets/propose').flush(PROPOSAL);
    fixture.detectChanges();

    c.addFood('COMIDA', { value: 9, label: 'brócoli' });
    const comida = c.proposal()!.meals.find((m) => m.slot === 'COMIDA')!;
    expect(comida.groups.length).toBe(3);
    expect(comida.groups[2].options.map((o) => o.canonical_name)).toEqual(['brócoli']);
  });

  it('opens the finder on one target at a time and closes it on a second press', () => {
    const fixture = setup();
    const c = fixture.componentInstance;

    c.toggleAdder('COMIDA');
    expect(c.isAdding('COMIDA', null)).toBeTrue();
    expect(c.isAdding('COMIDA', 0)).toBeFalse(); // the slot finder is not the row finder

    c.toggleAdder('COMIDA', 0);
    expect(c.isAdding('COMIDA', 0)).toBeTrue();
    expect(c.isAdding('COMIDA', null)).toBeFalse();

    c.toggleAdder('COMIDA', 0);
    expect(c.isAdding('COMIDA', 0)).toBeFalse();
  });

  it('closes the finder once the food has been placed', () => {
    const fixture = setup();
    const c = fixture.componentInstance;
    c.generate();
    http.expectOne('http://api/v1/diets/propose').flush(PROPOSAL);
    fixture.detectChanges();
    c.toggleAdder('COMIDA', 0);
    c.addFood('COMIDA', { value: 9, label: 'brócoli' }, 0);
    expect(c.addingTo()).toBeNull();
  });
});
