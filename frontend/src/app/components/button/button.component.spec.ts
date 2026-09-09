import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';

import { ButtonComponent } from './button.component';

@Component({
  imports: [ButtonComponent],
  template: `<app-button variant="primary" icon="save" (clicked)="n = n + 1">Guardar</app-button><app-button variant="icon" icon="close" ariaLabel="cerrar" />`,
})
class HostComponent {
  n = 0;
}

describe('ButtonComponent', () => {
  it('wraps the library button and re-emits clicks', () => {
    TestBed.configureTestingModule({ imports: [HostComponent], providers: [provideNoopAnimations()] });
    const fixture = TestBed.createComponent(HostComponent);
    fixture.detectChanges();
    const buttons = fixture.nativeElement.querySelectorAll('button');
    expect(buttons.length).toBe(2);
    expect(buttons[0].textContent).toContain('Guardar');
    buttons[0].click();
    expect(fixture.componentInstance.n).toBe(1);
    expect(buttons[1].getAttribute('aria-label')).toBe('cerrar');
  });
});
