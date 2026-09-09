import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { AutocompleteComponent, AutocompleteOption } from '@components/autocomplete/autocomplete.component';
import { ButtonComponent } from '@components/button/button.component';
import { Chip, ChipsComponent } from '@components/chips/chips.component';
import { ConfirmModalService } from '@components/confirm-modal/confirm-modal.component';
import { EvidenceBarComponent } from '@components/evidence-bar/evidence-bar.component';
import { InputComponent } from '@components/input/input.component';
import { LoadingComponent } from '@components/loading/loading.component';
import { SelectComponent } from '@components/select/select.component';
import { StatTileComponent } from '@components/stat-tile/stat-tile.component';
import { TextareaComponent } from '@components/textarea/textarea.component';
import { displayName, sexLabel, versionLabel } from '@converters/client/client.converter';
import { cloneProposal, itemCount, newOption } from '@converters/proposal/proposal.converter';
import { NewFood } from '@models/catalog';
import { Client } from '@models/client';
import { GOALS, ROUTING_LABELS, SLOTS, UNITS, groupLabel, reasonLabel, restrictionLabel } from '@models/common';
import { Proposal, ProposedGroup, ProposedMeal, ProposedOption } from '@models/diet';
import { SlotLabelPipe } from '@pipes/slot-label/slot-label.pipe';
import { CatalogService } from '@services/catalog/catalog/catalog.service';
import { BreadcrumbService } from '@services/breadcrumb/breadcrumb.service';
import { ClientsService } from '@services/clients/clients/clients.service';
import { DietsService } from '@services/diets/diets/diets.service';
import { AppStoreService } from '@services/store/app-store.service';

import { NewFoodDialogComponent } from './components/new-food-dialog/new-food-dialog.component';

/** The screen to take care of: the diet by slots in the centre, editable in line (S5); the right rail with the evidence of the selected food;
 *  the band on top with the strategy indicator and the validation summary. The original proposal is kept untouched for the diff. */
@Component({
  selector: 'app-diet-proposal',
  imports: [
    RouterLink,
    TranslatePipe,
    AutocompleteComponent,
    ButtonComponent,
    ChipsComponent,
    EvidenceBarComponent,
    InputComponent,
    LoadingComponent,
    SelectComponent,
    StatTileComponent,
    TextareaComponent,
    SlotLabelPipe,
  ],
  templateUrl: './diet-proposal.component.html',
  styleUrl: './diet-proposal.component.sass',
})
export class DietProposalComponent implements OnInit {
  readonly id = input.required<string>();
  readonly auto = input<string | undefined>(); // ?auto=1 generates on load (demo / deep link)
  // eslint-disable-next-line @angular-eslint/no-input-rename -- the deep link is ?select=<food_id>|kept|rotated; select() is the action
  readonly selectParam = input<string | undefined>(undefined, { alias: 'select' });
  // eslint-disable-next-line @angular-eslint/no-input-rename -- the deep link is ?goal=<value>; the signal 'goal' is the form state
  readonly goalParam = input<string | undefined>(undefined, { alias: 'goal' });
  private readonly clients = inject(ClientsService);
  private readonly breadcrumb = inject(BreadcrumbService);
  private readonly diets = inject(DietsService);
  private readonly catalog = inject(CatalogService);
  private readonly dialog = inject(MatDialog);
  private readonly confirm = inject(ConfirmModalService);
  private readonly router = inject(Router);
  readonly store = inject(AppStoreService);

  readonly goals = GOALS;
  readonly units = UNITS;
  readonly slots = SLOTS;
  readonly client = signal<Client | null>(null);
  readonly versionLabel = versionLabel;
  readonly goal = signal<string | string[] | null>(null);
  readonly k = signal<string | number | null>(20);
  readonly busy = signal(false);
  readonly saving = signal(false);
  readonly original = signal<Proposal | null>(null);
  readonly proposal = signal<Proposal | null>(null);
  readonly selected = signal<{ option: ProposedOption; slot: string } | null>(null);
  /**
   * A qué apunta el buscador de alimentos: a una franja (grupo `null`, crea fila nueva) o a un GRUPO concreto, y
   * entonces el alimento entra como ALTERNATIVA de esa fila. Antes era solo la franja, así que no había forma de
   * pedir lo segundo aunque `addFood` ya supiera hacerlo.
   */
  readonly addingTo = signal<{ slot: string; group: number | null } | null>(null);
  readonly newSlot = signal<string | string[] | null>(null);
  readonly newNote = signal<string | null>(null);
  readonly sexLabel = sexLabel;
  readonly reasonLabel = reasonLabel;
  readonly restrictionLabel = restrictionLabel;
  /** Options the professional added by hand in this session (slot|food_id): rotated items also carry empty evidence, so a flag is kept here. */
  readonly added = signal<Set<string>>(new Set());
  isAddition = (o: ProposedOption, slot?: string): boolean =>
    slot ? this.added().has(`${slot}|${o.food_id}`) : [...this.added()].some((k) => k.endsWith(`|${o.food_id}`));

  readonly itemCount = computed(() => itemCount(this.proposal()?.meals ?? []));
  readonly foodOptions = computed<AutocompleteOption<number>[]>(() =>
    this.store.foods().map((f) => ({ value: f.id, label: f.canonical_name, hint: `${f.family ?? ''} · ${groupLabel(f.group)}` })),
  );
  readonly slotOptions = computed(() => SLOTS.filter((s) => !(this.proposal()?.meals ?? []).some((m) => m.slot === s.value)));
  readonly routingChips = computed<Chip[]>(() => {
    const p = this.proposal();
    if (!p) return [];
    const chips: Chip[] = [
      { label: ROUTING_LABELS[p.routing.code] ?? p.routing.code, tone: p.routing.code === 'same_goal' ? 'rotated' : 'accent' },
      { label: p.strategy },
    ];
    if (p.routing.degradation && p.routing.degradation !== 'none') chips.push({ label: `degradación: ${p.routing.degradation}`, tone: 'warn' });
    if (p.gap) chips.push({ label: `demanda no cubierta: ${p.gap.triggered.join(', ')}`, tone: 'danger', icon: 'warning' });
    return chips;
  });
  readonly ruleChips = computed<Chip[]>(() =>
    (this.proposal()?.validation?.rules ?? [])
      .filter((c) => c.applicable)
      .map((c) => ({
        label: c.rule_id + (c.enforced ? ' (forzada)' : ''),
        tone: c.satisfied === true ? 'ok' : c.satisfied === false ? 'danger' : 'neutral',
        icon: c.satisfied ? 'check' : 'close',
        tooltip: this.store.ruleText(c.rule_id),
      })),
  );
  readonly selectedRuleChips = computed<Chip[]>(() =>
    (this.selected()?.option.evidence.rules ?? []).map((r) => ({
      label: `${r.rule_id} · ${r.prevalence != null ? Math.round(r.prevalence * 100) + ' %' : '—'} · lift ${r.lift != null ? r.lift.toFixed(2) : '—'}`,
      tone: 'accent',
      tooltip: this.store.ruleText(r.rule_id),
    })),
  );
  readonly plausibility = computed(() => this.proposal()?.parameters.plausibility?.changes ?? []);
  readonly ownedChips = computed<Chip[]>(() =>
    (this.proposal()?.owned_supplements ?? []).map((f) => ({ label: f.canonical_name ?? String(f.food_id), tone: 'accent' })),
  );

  ngOnInit(): void {
    this.catalog.ensureLoaded();
    if (this.goalParam()) this.goal.set(this.goalParam()!);
    this.clients.get(this.id()).subscribe((c) => {
      this.client.set(c);
      this.breadcrumb.set(displayName(c));
      if (!this.goal()) this.goal.set(c.goal);
      if (this.auto() === '1') this.generate();
    });
    this.clients.diets(this.id()).subscribe((d) => {
      const last = d.versions.at(-1);
      if (last && !this.goal()) this.goal.set(last.goal);
    });
  }

  // ------------------------------------------------------------------------------------------------------ generate / save
  generate(): void {
    const goal = this.goal();
    if (!goal || Array.isArray(goal)) return;
    this.busy.set(true);
    this.selected.set(null);
    this.added.set(new Set());
    this.diets.propose(this.id(), goal, Number(this.k() ?? 20)).subscribe({
      next: (p) => {
        this.original.set(p);
        this.proposal.set(cloneProposal(p));
        this.busy.set(false);
        this.preselect(p);
      },
      error: () => this.busy.set(false),
    });
  }

  save(): void {
    const p = this.proposal();
    if (!p) return;
    this.saving.set(true);
    this.diets.save(p, this.original()).subscribe({
      next: (saved) => {
        this.saving.set(false);
        this.router.navigate(['/diets', saved.id]);
      },
      error: () => this.saving.set(false),
    });
  }

  // ------------------------------------------------------------------------------------------------------ editing (immutable updates of the signal)
  private update(fn: (p: Proposal) => void): void {
    this.proposal.update((p) => {
      if (!p) return p;
      const copy = cloneProposal(p);
      fn(copy);
      return copy;
    });
  }

  select(option: ProposedOption, slot: string): void {
    this.selected.set({ option, slot });
  }

  private preselect(p: Proposal): void {
    const want = this.selectParam();
    if (!want) return;
    for (const m of p.meals) {
      for (const o of m.groups.flatMap((g) => g.options)) {
        const rotated = !!p.routing.previous_version && o.evidence.support === 0;
        const kept = !!p.routing.previous_version && o.evidence.support === 1 && o.evidence.cases.length === 1;
        if ((want === 'rotated' && rotated) || (want === 'kept' && kept) || String(o.food_id) === want) {
          this.select(o, m.slot);
          return;
        }
      }
    }
  }

  /** Clicks on the quantity / unit / tools inside an option edit, they do not select. */
  onOptionClick(event: Event, option: ProposedOption, slot: string): void {
    if ((event.target as HTMLElement).closest('.qty, .unit, .tools')) return;
    this.select(option, slot);
  }

  isSelected(option: ProposedOption): boolean {
    const s = this.selected();
    return !!s && s.option.food_id === option.food_id && s.option.normalized_key === option.normalized_key;
  }

  setQuantity(slot: string, gi: number, oi: number, value: string | number | null): void {
    this.update((p) => {
      const o = this.meal(p, slot).groups[gi].options[oi];
      o.quantity = value == null ? null : Number(value);
    });
  }

  setUnit(slot: string, gi: number, oi: number, unit: string | string[] | null): void {
    this.update((p) => {
      this.meal(p, slot).groups[gi].options[oi].unit = String(unit ?? '');
    });
  }

  removeOption(slot: string, gi: number, oi: number): void {
    this.update((p) => {
      const m = this.meal(p, slot);
      m.groups[gi].options.splice(oi, 1);
      if (!m.groups[gi].options.length) m.groups.splice(gi, 1);
      if (!m.groups.length) p.meals = p.meals.filter((x) => x.slot !== slot);
    });
    this.selected.set(null);
  }

  moveOption(slot: string, gi: number, oi: number, target: string | string[] | null): void {
    if (!target || Array.isArray(target) || target === slot) return;
    this.update((p) => {
      const m = this.meal(p, slot);
      const [o] = m.groups[gi].options.splice(oi, 1);
      if (!m.groups[gi].options.length) m.groups.splice(gi, 1);
      if (!m.groups.length) p.meals = p.meals.filter((x) => x.slot !== slot);
      const t = p.meals.find((x) => x.slot === target) ?? this.addMeal(p, target);
      t.groups.push({ position: t.groups.length, options: [o] });
      if (this.added().has(`${slot}|${o.food_id}`))
        this.added.update((set) => new Set([...[...set].filter((k) => k !== `${slot}|${o.food_id}`), `${target}|${o.food_id}`]));
    });
  }

  /** Abre el buscador donde se pide, y lo cierra si ya estaba abierto ahí. */
  toggleAdder(slot: string, group: number | null = null): void {
    const open = this.addingTo();
    this.addingTo.set(open && open.slot === slot && open.group === group ? null : { slot, group });
  }

  isAdding(slot: string, group: number | null): boolean {
    const open = this.addingTo();
    return !!open && open.slot === slot && open.group === group;
  }

  addFood(slot: string, choice: AutocompleteOption<number>, asAlternativeOf: number | null = null): void {
    this.update((p) => {
      const m = this.meal(p, slot);
      const food = this.store.foodById().get(choice.value);
      const option = newOption(choice.value, food?.canonical_name ?? choice.label, null, 'g');
      if (asAlternativeOf != null && m.groups[asAlternativeOf]) m.groups[asAlternativeOf].options.push(option);
      else m.groups.push({ position: m.groups.length, options: [option] });
    });
    this.added.update((set) => new Set([...set, `${slot}|${choice.value}`]));
    this.addingTo.set(null);
  }

  addSlot(): void {
    const s = this.newSlot();
    if (!s || Array.isArray(s)) return;
    this.update((p) => {
      this.addMeal(p, s);
    });
    this.newSlot.set(null);
  }

  removeSlot(slot: string): void {
    this.confirm.confirm({ title: 'Quitar franja', message: slot, danger: true }).subscribe((ok) => {
      if (ok)
        this.update((p) => {
          p.meals = p.meals.filter((m) => m.slot !== slot);
        });
    });
  }

  setNote(i: number, text: string | null): void {
    this.update((p) => {
      p.notes[i] = text ?? '';
    });
  }

  removeNote(i: number): void {
    this.update((p) => {
      p.notes.splice(i, 1);
    });
  }

  addNote(): void {
    const n = (this.newNote() ?? '').trim();
    if (!n) return;
    this.update((p) => {
      p.notes.push(n);
    });
    this.newNote.set(null);
  }

  openNewFood(slot: string, asAlternativeOf: number | null = null): void {
    this.dialog
      .open(NewFoodDialogComponent, { width: '640px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((body: NewFood | undefined) => {
        if (body) this.catalog.addFood(body).subscribe((food) => this.addFood(slot, { value: food.id, label: food.canonical_name }, asAlternativeOf));
      });
  }

  private meal(p: Proposal, slot: string): ProposedMeal {
    return p.meals.find((m) => m.slot === slot) ?? this.addMeal(p, slot);
  }

  private addMeal(p: Proposal, slot: string): ProposedMeal {
    const m: ProposedMeal = { slot, groups: [] };
    const order = SLOTS.map((s) => s.value);
    p.meals = [...p.meals, m].sort((a, b) => order.indexOf(a.slot) - order.indexOf(b.slot));
    return m;
  }

  groupOf(m: ProposedMeal, gi: number): ProposedGroup {
    return m.groups[gi];
  }

  pct(v: number | null | undefined): string {
    return v == null ? '—' : `${Math.round(v * 100)} %`;
  }
}
