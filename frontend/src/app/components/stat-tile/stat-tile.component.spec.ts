import { TestBed } from '@angular/core/testing';

import { StatTileComponent } from './stat-tile.component';

describe('StatTileComponent', () => {
  it('shows label, value, unit and tone', () => {
    TestBed.configureTestingModule({ imports: [StatTileComponent] });
    const fixture = TestBed.createComponent(StatTileComponent);
    fixture.componentRef.setInput('label', 'IMC');
    fixture.componentRef.setInput('value', 23.4);
    fixture.componentRef.setInput('unit', 'kg/m²');
    fixture.componentRef.setInput('tone', 'ok');
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelector('.label')?.textContent).toBe('IMC');
    expect(el.querySelector('.value')?.textContent).toContain('23.4');
    expect(el.querySelector('.tile')?.classList).toContain('tone-ok');
  });
});
