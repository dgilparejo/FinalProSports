import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { SelectComponent } from './select.component';

@Component({ imports: [SelectComponent], template: `<app-select label="Objetivo" [options]="opts" [(value)]="goal" />` })
class HostComponent {
  opts = [
    { value: 'a', label: 'A' },
    { value: 'b', label: 'B' },
  ];
  goal = signal<string | string[] | null>('a');
}

describe('SelectComponent', () => {
  it('renders a Material select bound to the model', async () => {
    TestBed.configureTestingModule({ imports: [HostComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('mat-select')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('mat-label').textContent).toContain('Objetivo');
    expect(fixture.nativeElement.querySelector('.mat-mdc-select-value').textContent).toContain('A');
  });
});
