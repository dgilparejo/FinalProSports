import { Component, input, output } from '@angular/core';
import { MatChipsModule } from '@angular/material/chips';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

import { ChipsConstants } from '@models/components/chips';

export interface Chip {
  label: string;
  tone?: (typeof ChipsConstants.TONES)[number];
  icon?: string | null;
  tooltip?: string | null;
  value?: unknown;
  removable?: boolean;
}

/** Semantic chips: neutral / accent / ok (rule satisfied) / warn (forced change) / danger (vetoed) / rotated (rotated item). */
@Component({
  selector: 'app-chips',
  imports: [MatChipsModule, MatIconModule, MatTooltipModule],
  template: `
    <mat-chip-set>
      @for (c of chips(); track $index) {
        <mat-chip
          [class]="'tone-' + (c.tone ?? DEFAULT_TONE)"
          [matTooltip]="c.tooltip ?? ''"
          (click)="picked.emit(c)"
          [class.clickable]="clickable()"
          [class.selected]="c.value !== undefined && c.value === selected()">
          @if (c.icon) {
            <mat-icon matChipAvatar>{{ c.icon }}</mat-icon>
          }
          {{ c.label }}
          @if (c.removable) {
            <mat-icon matChipRemove (click)="removed.emit(c); $event.stopPropagation()">cancel</mat-icon>
          }
        </mat-chip>
      }
      @if (!chips().length && emptyLabel()) {
        <span class="muted small empty">{{ emptyLabel() }}</span>
      }
    </mat-chip-set>
  `,
  styles: `
    :host {
      display: block;
    }
    /* El envoltorio de Material lleva un margen izquierdo de -8 px y cada chip lo compensa con el suyo; este texto
       no, así que quedaba 8 px a la izquierda del resto del contenido. Medido en el navegador, no estimado.
       (Sin acentos graves en este comentario: está dentro de un template literal y lo cerrarían.) */
    .empty {
      margin-left: 8px;
    }
    mat-chip {
      --mat-chip-elevated-container-color: var(--surface-alt);
      --mat-chip-label-text-color: var(--text);
      border: 1px solid var(--border);
    }
    mat-chip.tone-accent {
      --mat-chip-label-text-color: var(--accent);
      border-color: var(--accent);
    }
    mat-chip.tone-ok {
      --mat-chip-label-text-color: var(--ok);
      border-color: var(--ok);
    }
    mat-chip.tone-warn {
      --mat-chip-label-text-color: var(--warn);
      border-color: var(--warn);
    }
    mat-chip.tone-danger {
      --mat-chip-label-text-color: var(--danger);
      border-color: var(--danger);
    }
    mat-chip.tone-rotated {
      --mat-chip-label-text-color: var(--rotated);
      border-color: var(--rotated);
    }
    mat-chip.clickable {
      cursor: pointer;
    }
    mat-chip.selected {
      --mat-chip-elevated-container-color: var(--accent);
      --mat-chip-label-text-color: var(--accent-ink);
    }
    mat-icon[matChipAvatar] {
      font-size: 16px;
    }
  `,
})
export class ChipsComponent extends ChipsConstants {
  readonly chips = input.required<Chip[]>();
  readonly clickable = input(false);
  readonly selected = input<unknown>(undefined);
  readonly emptyLabel = input<string | null>(null);
  readonly picked = output<Chip>();
  readonly removed = output<Chip>();
  readonly DEFAULT_TONE = ChipsConstants.DEFAULT_TONE;
}
