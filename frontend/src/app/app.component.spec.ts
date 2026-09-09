import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { AppComponent } from './app.component';
import { APP_CONFIG } from './app.config';
import { KeycloakAuthService } from './core/auth/keycloak-auth.service';

describe('AppComponent', () => {
  let expired: ReturnType<typeof signal<boolean>>;

  beforeEach(async () => {
    expired = signal(false);
    await TestBed.configureTestingModule({
      imports: [AppComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: '/api/v1', professionalId: 'prof_001', brand: 'Marca Test' } },
        {
          provide: KeycloakAuthService,
          useValue: {
            sessionExpired: expired,
            authenticated: signal(true),
            roles: signal(['entrenador']),
            displayName: () => 'entrenador',
            reauthenticate: () => Promise.resolve(),
          },
        },
      ],
    }).compileComponents();
  });

  it('shows the logo alone as the link home, with the brand as its accessible name', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const logo = el.querySelector<HTMLImageElement>('.brand img');
    expect(logo?.getAttribute('alt')).toBe('Marca Test');
    expect(el.querySelector('.brand-name')).toBeNull();
  });

  it('has one navigation entry: the API docs link is gone', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const links = fixture.nativeElement.querySelectorAll('nav a') as NodeListOf<HTMLAnchorElement>;
    expect(links.length).toBe(1);
    expect([...links].some((a) => (a.getAttribute('href') ?? '').includes('docs'))).toBeFalse();
  });

  it('says nothing about the session while it is alive', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.expired-backdrop')).toBeNull();
  });

  it('blocks the screen with one way back in when the session cannot be renewed', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expired.set(true);
    fixture.detectChanges();
    const backdrop: HTMLElement = fixture.nativeElement.querySelector('.expired-backdrop');
    expect(backdrop).not.toBeNull();
    expect(backdrop.getAttribute('role')).toBe('alertdialog');
    // The keys must exist: with TranslateModule.forRoot() and no dictionary, a missing key renders as the key itself.
    expect(backdrop.textContent).toContain('auth.expired.title');
    expect(backdrop.querySelectorAll('app-button').length).toBe(1);
  });
});
