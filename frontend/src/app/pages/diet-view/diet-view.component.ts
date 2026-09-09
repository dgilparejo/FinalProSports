import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from '@components/button/button.component';
import { Chip, ChipsComponent } from '@components/chips/chips.component';
import { LoadingComponent } from '@components/loading/loading.component';
import { StatTileComponent } from '@components/stat-tile/stat-tile.component';
import { versionLabel } from '@converters/client/client.converter';
import { ROUTING_LABELS, reasonLabel } from '@models/common';
import { Proposal } from '@models/diet';
import { GoalLabelPipe } from '@pipes/goal-label/goal-label.pipe';
import { QuantityPipe } from '@pipes/quantity/quantity.pipe';
import { SlotLabelPipe } from '@pipes/slot-label/slot-label.pipe';
import { BreadcrumbService } from '@services/breadcrumb/breadcrumb.service';
import { CatalogService } from '@services/catalog/catalog/catalog.service';
import { DietFormat } from '@env/urls';

import { DietsService } from '@services/diets/diets/diets.service';
import { AppStoreService } from '@services/store/app-store.service';

/** A saved diet: what the professional delivered, the diff against the engine's proposal (S5), validation, evidence, lab context and the PDF. */
@Component({
  selector: 'app-diet-view',
  imports: [RouterLink, TranslatePipe, ButtonComponent, ChipsComponent, LoadingComponent, StatTileComponent, GoalLabelPipe, QuantityPipe, SlotLabelPipe],
  templateUrl: './diet-view.component.html',
  styleUrl: './diet-view.component.sass',
})
export class DietViewComponent implements OnInit {
  readonly id = input.required<string>();
  private readonly diets = inject(DietsService);
  private readonly breadcrumb = inject(BreadcrumbService);
  private readonly catalog = inject(CatalogService);
  readonly store = inject(AppStoreService);

  readonly diet = signal<(Proposal & { id: string }) | null>(null);
  readonly reasonLabel = reasonLabel;
  readonly routingChips = computed<Chip[]>(() => {
    const d = this.diet();
    if (!d) return [];
    const chips: Chip[] = [
      { label: ROUTING_LABELS[d.routing.code] ?? d.routing.code, tone: d.routing.code === 'same_goal' ? 'rotated' : 'accent' },
      { label: d.strategy },
    ];
    if (d.edited) chips.push({ label: 'editada por el profesional', tone: 'warn' });
    return chips;
  });
  readonly ruleChips = computed<Chip[]>(() =>
    (this.diet()?.validation?.rules ?? [])
      .filter((c) => c.applicable)
      .map((c) => ({
        label: c.rule_id + (c.enforced ? ' (forzada)' : ''),
        tone: c.satisfied === true ? 'ok' : c.satisfied === false ? 'danger' : 'neutral',
        icon: c.satisfied ? 'check' : 'close',
        tooltip: this.store.ruleText(c.rule_id),
      })),
  );

  ngOnInit(): void {
    this.catalog.ensureLoaded();
    this.diets.get(this.id()).subscribe((d) => {
      this.diet.set(d);
      this.breadcrumb.set(this.clientName(), this.clientId() ? `/clients/${this.clientId()}` : null);
    });
  }

  /** Back link: the client's key (S9: the response carries it in `client`; the engine's profile keeps it as `client_code`). */
  clientId(): string {
    return this.diet()?.client?.id ?? String(this.diet()?.profile['client_code'] ?? '');
  }

  clientName(): string {
    return this.diet()?.client?.full_name ?? '';
  }

  version(): string {
    return versionLabel(this.diet()?.id);
  }

  goal(): string {
    return String(this.diet()?.profile['goal'] ?? '');
  }

  /** The document in the format the professional picks: the PDF to hand over, the .odt to keep editing.
   *
   * Se descarga por HttpClient y se guarda desde un blob, NO con un `<a href>` a la API. Un enlace es una navegacion
   * del navegador: no pasa por el interceptor, no lleva el token, y la API contesta 401 `unauthenticated`. Era lo que
   * pasaba con «Exportar PDF» y con «Descargar .odt», los dos.
   */
  downloading = signal<DietFormat | null>(null);
  exportError = signal(false);

  download(format: DietFormat): void {
    if (this.downloading()) return;
    this.downloading.set(format);
    this.exportError.set(false);
    this.diets.export(this.id(), format).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = this.fileName(format);
        a.click();
        URL.revokeObjectURL(url); // sin esto el blob se queda en memoria mientras viva la pestana
        this.downloading.set(null);
      },
      error: () => {
        this.exportError.set(true);
        this.downloading.set(null);
      },
    });
  }

  exportUrl(format: DietFormat): string {
    return this.diets.exportUrl(this.id(), format);
  }

  fileName(format: DietFormat): string {
    const who = (this.clientName() || 'cliente').replace(/[^\p{L}\p{N}]+/gu, '_');
    return `dieta_${who}_${this.version()}.${format}`;
  }

  pdfUrl(): string {
    return this.diets.pdfUrl(this.id());
  }

  pct(v: number | null | undefined): string {
    return v == null ? '—' : `${Math.round(v * 100)} %`;
  }
}
