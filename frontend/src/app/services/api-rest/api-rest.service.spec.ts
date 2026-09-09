import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { APP_CONFIG } from '../../app.config';

import { ApiRestService } from './api-rest.service';

describe('ApiRestService', () => {
  let service: ApiRestService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: APP_CONFIG, useValue: { apiBaseUrl: 'http://api/v1/', professionalId: 'p', brand: 'b' } },
      ],
    });
    service = TestBed.inject(ApiRestService);
    http = TestBed.inject(HttpTestingController);
  });

  it('builds URLs from the configured base without double slashes', () => {
    expect(service.getUrl('/clients')).toBe('http://api/v1/clients');
    expect(service.getUrl('clients/X/record')).toBe('http://api/v1/clients/X/record');
  });

  it('isOkResponse accepts 2xx only', () => {
    expect(service.isOkResponse({ status: 201 })).toBeTrue();
    expect(service.isOkResponse({ status: 404 })).toBeFalse();
  });

  it('performs a GET through HttpClient', () => {
    service.get<string[]>('clients').subscribe((v) => expect(v).toEqual(['a']));
    http.expectOne('http://api/v1/clients').flush(['a']);
    http.verify();
  });
});
