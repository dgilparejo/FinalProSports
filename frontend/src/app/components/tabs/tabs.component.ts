import { Component, input, model } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { TabsConstants } from '@models/components/tabs';

/** Own tab strip (segmented control): the intake page needs seven sections and Material's paginated tab header froze the renderer
 *  on the last one in Chrome 151; a strip of buttons plus `@switch` in the page is simpler and keeps the pages library-free. */
@Component({
  selector: 'app-tabs',
  imports: [TranslatePipe],
  template: `
    <div class="strip" role="tablist">
      @for (t of tabs(); track t; let i = $index) {
        <button type="button" role="tab" class="tab" [class.active]="i === selected()" [attr.aria-selected]="i === selected()" (click)="selected.set(i)">
          {{ t | translate }}
        </button>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .strip {
      display: flex;
      gap: 2px;
      border-bottom: 1px solid var(--border);
      overflow-x: auto;
      /* Siete secciones no caben en un móvil: la tira se desplaza. Barra fina para que no se coma una línea. */
      scrollbar-width: thin;
      -webkit-overflow-scrolling: touch;
    }
    .strip::-webkit-scrollbar {
      height: 4px;
    }
    .strip::-webkit-scrollbar-thumb {
      background: var(--border);
      border-radius: 2px;
    }
    .tab {
      background: none;
      border: 0;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      font: inherit;
      font-weight: 500;
      padding: 8px 14px;
      cursor: pointer;
      white-space: nowrap;
    }
    .tab:hover {
      color: var(--text);
    }
    .tab.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }
    .tab:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: -2px;
    }
  `,
})
export class TabsComponent extends TabsConstants {
  readonly tabs = input.required<string[]>();
  readonly selected = model<number>(TabsConstants.DEFAULT_INDEX);
}
