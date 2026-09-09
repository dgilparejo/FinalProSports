import { DestroyRef, Injectable, inject, signal } from '@angular/core';

/**
 * El punto de corte del CSS, disponible también en TypeScript.
 *
 * Casi toda la adaptación a móvil se hace con `@media`, que es donde debe estar. Hay un caso que el CSS no resuelve:
 * la lista de clientes tiene SIETE columnas, y en un móvil la solución no es apretarlas ni esconderlas — es dejar de
 * ser una tabla. Un listado de clientes no se lee comparando columnas, se usa para buscar a alguien y entrar. Ese
 * cambio es de PLANTILLA, y una plantilla necesita saber el ancho.
 *
 * 720 px, EL MISMO literal que `styles.sass`. Dos definiciones del mismo umbral que se separan dejan un hueco en el
 * que no se ve bien ni la tabla ni las tarjetas, así que `backend/tests/architecture/test_breakpoint_is_single.py`
 * comprueba que sigan coincidiendo.
 */
export const NARROW_MAX_WIDTH_PX = 720;

@Injectable({ providedIn: 'root' })
export class LayoutService {
  private readonly query = window.matchMedia(`(max-width: ${NARROW_MAX_WIDTH_PX}px)`);
  /** `true` cuando la ventana está por debajo del corte. Se actualiza al girar el móvil o redimensionar. */
  readonly narrow = signal(this.query.matches);

  constructor() {
    const update = (e: MediaQueryListEvent) => this.narrow.set(e.matches);
    this.query.addEventListener('change', update);
    inject(DestroyRef).onDestroy(() => this.query.removeEventListener('change', update));
  }
}
