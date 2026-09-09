import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { ChipsComponent } from './chips.component';

describe('ChipsComponent', () => {
  it('renders one chip per entry with its semantic tone', () => {
    TestBed.configureTestingModule({ imports: [ChipsComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(ChipsComponent);
    fixture.componentRef.setInput('chips', [{ label: 'Lactosa', tone: 'danger' }, { label: 'agua_2.5L', tone: 'ok' }, { label: 'neutro' }]);
    fixture.detectChanges();
    const chips = fixture.nativeElement.querySelectorAll('mat-chip');
    expect(chips.length).toBe(3);
    expect(chips[0].classList).toContain('tone-danger');
    expect(chips[2].classList).toContain('tone-neutral');
  });
});
