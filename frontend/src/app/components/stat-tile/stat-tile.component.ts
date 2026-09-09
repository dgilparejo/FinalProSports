import { Component, input } from '@angular/core';

import { StatTileConstants } from '@models/components/stat-tile';

/** Label + value + hint. Tabular figures so columns of numbers line up; tone colours the value only. */
@Component({
  selector: 'app-stat-tile',
  template: `
    <div class="tile" [class]="'tile tone-' + tone()">
      <span class="label">{{ label() }}</span>
      <span class="value num"
        >{{ value() }}
        @if (unit()) {
          <span class="unit">{{ unit() }}</span>
        }
      </span>
      @if (hint()) {
        <span class="hint">{{ hint() }}</span>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .tile {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 8px 12px;
      background: var(--surface-alt);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      min-width: 120px;
    }
    .label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
    }
    .value {
      font-size: 20px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.1;
    }
    .unit {
      font-size: 12px;
      font-weight: 400;
      color: var(--text-muted);
      margin-left: 4px;
    }
    .hint {
      font-size: 12px;
      color: var(--text-faint);
    }
    .tone-accent .value {
      color: var(--accent);
    }
    .tone-ok .value {
      color: var(--ok);
    }
    .tone-warn .value {
      color: var(--warn);
    }
    .tone-danger .value {
      color: var(--danger);
    }
  `,
})
export class StatTileComponent extends StatTileConstants {
  readonly label = input.required<string>();
  readonly value = input.required<string | number>();
  readonly unit = input<string | null>(null);
  readonly hint = input<string | null>(null);
  readonly tone = input<(typeof StatTileConstants.TONES)[number]>(StatTileConstants.DEFAULT_TONE);
}
