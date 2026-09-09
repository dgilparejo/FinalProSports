import { TestBed } from '@angular/core/testing';

import { LayoutService, NARROW_MAX_WIDTH_PX } from './layout.service';

describe('LayoutService', () => {
  let listener: ((e: MediaQueryListEvent) => void) | null;
  let asked: string;
  let matches: boolean;

  // Un solo espía para todo el fichero: `spyOn` no se puede aplicar dos veces al mismo método, y lo que cambia
  // entre casos es el ANCHO de la ventana, no la forma de preguntarlo.
  beforeEach(() => {
    listener = null;
    asked = '';
    matches = false;
    spyOn(window, 'matchMedia').and.callFake(
      (q: string) =>
        ({
          get matches() {
            return matches;
          },
          media: q,
          addEventListener: (_: string, fn: (e: MediaQueryListEvent) => void) => {
            asked = q;
            listener = fn;
          },
          removeEventListener: () => (listener = null),
        }) as unknown as MediaQueryList,
    );
  });

  function create(narrow: boolean): LayoutService {
    matches = narrow;
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    return TestBed.inject(LayoutService);
  }

  it('asks for the same breakpoint the stylesheet uses', () => {
    create(false);
    expect(asked).toBe(`(max-width: ${NARROW_MAX_WIDTH_PX}px)`);
    expect(NARROW_MAX_WIDTH_PX).toBe(720);
  });

  it('starts from the window it is created in', () => {
    expect(create(true).narrow()).toBeTrue();
    expect(create(false).narrow()).toBeFalse();
  });

  it('follows a resize or a rotation instead of reading the width once', () => {
    const layout = create(false);
    listener!({ matches: true } as MediaQueryListEvent);
    expect(layout.narrow()).toBeTrue();
    listener!({ matches: false } as MediaQueryListEvent);
    expect(layout.narrow()).toBeFalse();
  });
});
