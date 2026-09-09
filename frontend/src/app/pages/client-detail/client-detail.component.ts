import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from '@components/button/button.component';
import { Chip, ChipsComponent } from '@components/chips/chips.component';
import { LoadingComponent } from '@components/loading/loading.component';
import { StatTileComponent } from '@components/stat-tile/stat-tile.component';
import { displayName, sexLabel, versionLabel } from '@converters/client/client.converter';
import { Client, RecordView } from '@models/client';
import { restrictionLabel } from '@models/common';
import { ClientDiets, HistoryItem } from '@models/diet';
import { GoalLabelPipe } from '@pipes/goal-label/goal-label.pipe';
import { SlotLabelPipe } from '@pipes/slot-label/slot-label.pipe';
import { BreadcrumbService } from '@services/breadcrumb/breadcrumb.service';
import { ClientsService } from '@services/clients/clients/clients.service';
import { IntakeService } from '@services/intake/intake/intake.service';

/** Client file: profile, completeness (record vs algorithm), saved versions (the history the rotation starts from) and quick actions. */
@Component({
  selector: 'app-client-detail',
  imports: [RouterLink, TranslatePipe, MatExpansionModule, ButtonComponent, ChipsComponent, LoadingComponent, StatTileComponent, GoalLabelPipe, SlotLabelPipe],
  templateUrl: './client-detail.component.html',
  styleUrl: './client-detail.component.sass',
})
export class ClientDetailComponent implements OnInit {
  readonly id = input.required<string>();
  private readonly clients = inject(ClientsService);
  private readonly intake = inject(IntakeService);
  private readonly breadcrumb = inject(BreadcrumbService);

  readonly client = signal<Client | null>(null);
  readonly diets = signal<ClientDiets | null>(null);
  readonly view = signal<RecordView | null>(null);
  readonly sexLabel = sexLabel;
  readonly displayName = displayName;
  readonly versionLabel = versionLabel;
  readonly restrictionChips = computed<Chip[]>(() => {
    const c = this.client();
    if (!c) return [];
    const chips: Chip[] = c.restrictions.map((r) => ({ label: restrictionLabel(r), tone: 'danger', icon: 'block' }));
    if (c.has_medical_restrictions) chips.push({ label: 'restricción médica en el expediente', tone: 'warn' });
    return chips;
  });
  readonly dislikedChips = computed<Chip[]>(() =>
    (this.view()?.client.disliked_foods ?? []).map((f) => ({ label: f.canonical_name ?? String(f.food_id), tone: 'warn' })),
  );
  readonly missingAlgorithmText = computed(() => (this.view()?.completeness.algorithm.missing ?? []).map((m) => m.label).join(', '));
  readonly supplementChips = computed<Chip[]>(() =>
    (this.view()?.client.supplements_owned ?? []).map((f) => ({ label: f.canonical_name ?? String(f.food_id), tone: 'accent' })),
  );

  ngOnInit(): void {
    this.clients.get(this.id()).subscribe((c) => {
      this.client.set(c);
      this.breadcrumb.set(displayName(c));
    });
    this.clients.diets(this.id()).subscribe((d) => this.diets.set(d));
    this.intake.record(this.id()).subscribe((v) => this.view.set(v));
  }

  describe(items: HistoryItem[]): string {
    const groups = new Map<string, string[]>();
    items.forEach((i, idx) => {
      const k = i.alternative_group ?? `p${idx}`;
      const text = i.quantity != null ? `${i.quantity} ${i.unit} ${i.canonical_name ?? i.text}`.trim() : (i.canonical_name ?? i.text);
      groups.set(k, [...(groups.get(k) ?? []), text]);
    });
    return [...groups.values()].map((g) => [...new Set(g)].join(' / ')).join(' · ');
  }

  /** Birth date · phone · e-mail, whatever is present (the identity block of the record, S9). */
  contactLine(c: Client): string {
    return [c.birth_date, c.phone, c.email].filter((x): x is string => !!x).join(' · ');
  }

  pct(v: number | null | undefined): string {
    return v == null ? '—' : `${Math.round(v * 100)} %`;
  }
}
