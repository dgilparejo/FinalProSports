import { Component, computed, input } from '@angular/core';

import { EvidenceBarConstants } from '@models/components/evidence-bar';

/** «aparece en 19 de 20 casos»: a one-tone ramp of the accent (20 % -> 100 % opacity). It is a magnitude, not a category. */
@Component({
  selector: 'app-evidence-bar',
  template: `
    <div class="bar" [style.height.px]="HEIGHT_PX" [attr.aria-label]="text()">
      <div class="fill" [style.width.%]="share() * 100" [style.opacity]="opacity()"></div>
    </div>
    @if (showText()) {
      <span class="text small muted">{{ text() }}</span>
    }
  `,
  styles: `
    :host {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .bar {
      flex: 1 1 auto;
      min-width: 60px;
      background: var(--surface-alt);
      border-radius: 3px;
      overflow: hidden;
    }
    .fill {
      height: 100%;
      background: var(--evidence-100);
      border-radius: 3px;
    }
    .text {
      white-space: nowrap;
    }
  `,
})
export class EvidenceBarComponent extends EvidenceBarConstants {
  readonly support = input.required<number>();
  readonly cases = input<number | null>(null);
  readonly total = input<number | null>(null);
  readonly showText = input(true);
  readonly HEIGHT_PX = EvidenceBarConstants.HEIGHT_PX;
  readonly share = computed(() => Math.max(0, Math.min(1, this.support())));
  readonly opacity = computed(() => EvidenceBarConstants.MIN_OPACITY + (EvidenceBarConstants.MAX_OPACITY - EvidenceBarConstants.MIN_OPACITY) * this.share());
  readonly text = computed(() => {
    const c = this.cases();
    const t = this.total();
    if (c != null && t != null) return `aparece en ${c} de ${t} casos`;
    return `${Math.round(this.share() * 100)} % de los casos`;
  });
}
