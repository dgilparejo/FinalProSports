import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { APP_CONFIG } from '../../app.config';

/** The only place that knows the API base URL. Every <area>-apis service builds its URLs through getUrl(). */
@Injectable({ providedIn: 'root' })
export class ApiRestService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(APP_CONFIG);

  getUrl(path: string): string {
    return `${this.config.apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
  }

  isOkResponse(response: HttpResponse<unknown> | { status: number }): boolean {
    return response.status >= 200 && response.status < 300;
  }

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(this.getUrl(path));
  }

  /**
   * Binary download THROUGH HttpClient, which is the whole point: the auth interceptor only sees requests that go
   * through it. A plain `<a href>` to the API is a browser navigation, carries no Authorization header, and the API
   * answers 401 `unauthenticated` — which is exactly what «Exportar PDF» and «Descargar .odt» were doing.
   */
  getBlob(path: string): Observable<Blob> {
    return this.http.get(this.getUrl(path), { responseType: 'blob' });
  }

  post<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(this.getUrl(path), body);
  }

  put<T>(path: string, body: unknown): Observable<T> {
    return this.http.put<T>(this.getUrl(path), body);
  }

  delete<T>(path: string): Observable<T> {
    return this.http.delete<T>(this.getUrl(path));
  }
}
