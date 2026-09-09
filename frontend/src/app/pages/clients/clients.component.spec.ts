import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { LayoutService } from '@services/layout/layout.service';

import { APP_CONFIG } from '../../app.config';

import { ClientsComponent } from './clients.component';

describe('ClientsComponent', () => {
  let narrow: ReturnType<typeof signal<boolean>>;

  beforeEach(() => {
    narrow = signal(false);
    TestBed.configureTestingModule({
      imports: [ClientsComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1', professionalId: 'p', brand: 'b' } },
        { provide: LayoutService, useValue: { narrow } },
      ],
    });
  });

  const TWO = [
    { id: 'c1', full_name: 'Nora Ficticia Demo', sex: 'F', age: 34, goal: 'definicion_grasa', restrictions: ['contains_lactose'], diet_count: 0 },
    { id: 'c3', full_name: 'Enzo Ficticio Demo', sex: 'M', age: 41, goal: 'volumen_masa', restrictions: [], diet_count: 3 },
  ];

  function loaded() {
    const fixture = TestBed.createComponent(ClientsComponent);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController).expectOne('http://api/v1/clients').flush(TWO);
    fixture.detectChanges();
    return fixture;
  }

  it('shows the empty state when the portfolio is empty (S1)', () => {
    const fixture = TestBed.createComponent(ClientsComponent);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController).expectOne('http://api/v1/clients').flush([]);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.empty-state')).toBeTruthy();
  });

  it('lists the portfolio by name and filters by name (S9)', () => {
    const fixture = TestBed.createComponent(ClientsComponent);
    fixture.detectChanges();
    TestBed.inject(HttpTestingController)
      .expectOne('http://api/v1/clients')
      .flush([
        { id: 'c1', full_name: 'Nora Ficticia Demo', sex: 'F', age: 34, restrictions: ['contains_lactose'], diet_count: 0 },
        { id: 'c3', full_name: 'Enzo Ficticio Demo', sex: 'M', age: 41, restrictions: [], diet_count: 3 },
      ]);
    fixture.detectChanges();
    expect(fixture.componentInstance.rows().length).toBe(2);
    expect(fixture.componentInstance.rows()[0]['id']).toBe('c3'); // documented clients first
    expect(fixture.nativeElement.textContent).toContain('Enzo Ficticio Demo');
    expect(fixture.nativeElement.textContent).not.toContain('c3'); // the key is never shown
    fixture.componentInstance.filter.set('nora');
    expect(fixture.componentInstance.rows().length).toBe(1);
  });

  it('uses the table on a wide window', () => {
    const el: HTMLElement = loaded().nativeElement;
    expect(el.querySelector('app-table')).toBeTruthy();
    expect(el.querySelector('.cards')).toBeNull();
  });

  it('uses cards on a narrow one, one per client', () => {
    narrow.set(true);
    const el: HTMLElement = loaded().nativeElement;
    expect(el.querySelector('app-table')).toBeNull();
    expect(el.querySelectorAll('.cards .card').length).toBe(2);
  });

  it('the cards hide NO column: the restrictions are the reason they exist', () => {
    narrow.set(true);
    const el: HTMLElement = loaded().nativeElement;
    const first = el.querySelector('.cards .card')!;
    // c3 first (documented clients first): name, sex, age, goal, saved diets and the restrictions block.
    expect(first.querySelector('.card-name')!.textContent).toContain('Enzo Ficticio Demo');
    expect(first.querySelector('.card-facts')!.textContent).toContain('Hombre');
    expect(first.querySelector('.card-facts')!.textContent).toContain('41');
    expect(first.querySelector('.card-diets')!.textContent).toContain('3');
    expect(first.querySelector('app-chips')).toBeTruthy();
    expect(first.querySelectorAll('.card-actions a').length).toBe(2);
  });

  it('the cards never show the internal key either', () => {
    narrow.set(true);
    const el: HTMLElement = loaded().nativeElement;
    expect(el.querySelector('.cards')!.textContent).not.toContain('c3');
  });

  it('the filter feeds the cards, not only the table', () => {
    narrow.set(true);
    const fixture = loaded();
    fixture.componentInstance.filter.set('nora');
    fixture.detectChanges();
    const cards = fixture.nativeElement.querySelectorAll('.cards .card');
    expect(cards.length).toBe(1);
    expect(cards[0].textContent).toContain('Nora Ficticia Demo');
  });

  it('switches layout when the window is resized, without reloading', () => {
    const fixture = loaded();
    expect(fixture.nativeElement.querySelector('app-table')).toBeTruthy();
    narrow.set(true);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-table')).toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.cards .card').length).toBe(2);
  });
});
