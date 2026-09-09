import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { BreadcrumbService } from './breadcrumb.service';

@Component({ template: '' })
class Blank {}

describe('BreadcrumbService', () => {
  let harness: RouterTestingHarness;
  let breadcrumb: BreadcrumbService;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: '', component: Blank },
          { path: 'clients/:id', component: Blank },
          { path: 'clients/:id/intake', component: Blank },
          { path: 'diets/:id', component: Blank },
        ]),
      ],
    });
    breadcrumb = TestBed.inject(BreadcrumbService);
    harness = await RouterTestingHarness.create();
  });

  it('renders nothing on the list, which has nothing above it', async () => {
    await harness.navigateByUrl('/');
    expect(breadcrumb.trail()).toEqual([]);
  });

  it('walks clients / name / screen, and the current page is never a link', async () => {
    await harness.navigateByUrl('/clients/abc/intake');
    breadcrumb.set('Nora Ficticia Demo');
    const trail = breadcrumb.trail();
    expect(trail.map((c) => c.key)).toEqual(['nav.clients', null, 'intake.title']);
    expect(trail[1].text).toBe('Nora Ficticia Demo');
    expect(trail[1].link).toBe('/clients/abc');
    expect(trail.at(-1)!.link).toBeNull();
  });

  it('drops the published name on navigation so a stale one cannot be shown', async () => {
    await harness.navigateByUrl('/clients/abc');
    breadcrumb.set('Nora Ficticia Demo');
    await harness.navigateByUrl('/clients/xyz');
    expect(breadcrumb.trail()[1].text).toBe('…');
  });

  it('sends a saved diet back to its own client', async () => {
    await harness.navigateByUrl('/diets/xyz::e01');
    breadcrumb.set('Teo Ficticio Demo', '/clients/xyz');
    expect(breadcrumb.trail().map((c) => c.link)).toEqual(['/', '/clients/xyz', null]);
  });
});
