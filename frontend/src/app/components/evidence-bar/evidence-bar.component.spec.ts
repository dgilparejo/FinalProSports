import { TestBed } from '@angular/core/testing';

import { EvidenceBarComponent } from './evidence-bar.component';

describe('EvidenceBarComponent', () => {
  it('fills proportionally with a one-tone opacity ramp and narrates the cases', () => {
    TestBed.configureTestingModule({ imports: [EvidenceBarComponent] });
    const fixture = TestBed.createComponent(EvidenceBarComponent);
    fixture.componentRef.setInput('support', 0.95);
    fixture.componentRef.setInput('cases', 19);
    fixture.componentRef.setInput('total', 20);
    fixture.detectChanges();
    const fill: HTMLElement = fixture.nativeElement.querySelector('.fill');
    expect(fill.style.width).toBe('95%');
    expect(Number(fill.style.opacity)).toBeCloseTo(0.2 + 0.8 * 0.95, 3);
    expect(fixture.nativeElement.textContent).toContain('aparece en 19 de 20 casos');
    fixture.componentRef.setInput('cases', null);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('95 % de los casos');
  });
});
