import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { InputComponent } from './input.component';

@Component({ imports: [InputComponent], template: `<app-input label="Edad" type="number" [(value)]="age" suffix="años" />` })
class HostComponent {
  age = signal<number | string | null>(30);
}

describe('InputComponent', () => {
  it('binds the model two ways and converts numbers', async () => {
    TestBed.configureTestingModule({ imports: [HostComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    const input: HTMLInputElement = fixture.nativeElement.querySelector('input');
    expect(input.type).toBe('number');
    input.value = '41';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(fixture.componentInstance.age()).toBe(41);
    input.value = '';
    input.dispatchEvent(new Event('input'));
    expect(fixture.componentInstance.age()).toBeNull();
  });
});
