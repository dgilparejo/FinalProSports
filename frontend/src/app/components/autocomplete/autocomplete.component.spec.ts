import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { AutocompleteComponent } from './autocomplete.component';

describe('AutocompleteComponent', () => {
  it('filters options by prefix first, then by content, accent-insensitively', () => {
    TestBed.configureTestingModule({ imports: [AutocompleteComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(AutocompleteComponent<number>);
    fixture.componentRef.setInput('options', [
      { value: 1, label: 'pollo', hint: 'ave · Proteína' },
      { value: 2, label: 'plátano', hint: 'fruta · Fruta' },
      { value: 3, label: 'pavo', hint: 'ave · Proteína' },
    ]);
    fixture.detectChanges();
    const c = fixture.componentInstance;
    c.query.set('pla');
    expect(c.filtered().map((o) => o.value)).toEqual([2]);
    c.query.set('ave');
    expect(c.filtered().map((o) => o.value)).toEqual([1, 3]);
    c.query.set('');
    expect(c.filtered().length).toBe(3);
  });
});
