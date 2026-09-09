import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from '@components/button/button.component';
import { Chip, ChipsComponent } from '@components/chips/chips.component';
import { ConfirmModalService } from '@components/confirm-modal/confirm-modal.component';
import { DatepickerComponent } from '@components/datepicker/datepicker.component';
import { FileUploadComponent, UploadedFile } from '@components/file-upload/file-upload.component';
import { FormComponent } from '@components/form/form.component';
import { InputComponent } from '@components/input/input.component';
import { LoadingComponent } from '@components/loading/loading.component';
import { SelectComponent } from '@components/select/select.component';
import { StatTileComponent } from '@components/stat-tile/stat-tile.component';
import { TableColumn, TableComponent } from '@components/table/table.component';
import { TabsComponent } from '@components/tabs/tabs.component';
import { TextareaComponent } from '@components/textarea/textarea.component';
import {
  ClientRecord,
  LabReport,
  LabResult,
  LabResultsResponse,
  NewBodyMeasurement,
  NewLabResult,
  RecordView,
  emptyRecord,
  groupIntoReports,
} from '@models/client';
import { Option, restrictionLabel } from '@models/common';
import { BreadcrumbService } from '@services/breadcrumb/breadcrumb.service';
import { IntakeService } from '@services/intake/intake/intake.service';
import { LoggerService } from '@services/logger/logger.service';

/** Intake page (S3 + S4): the five blocks of the sheet, the scale import / manual weight, the lab results and the two completeness indicators. */
@Component({
  selector: 'app-client-intake',
  imports: [
    RouterLink,
    TranslatePipe,
    ButtonComponent,
    ChipsComponent,
    DatepickerComponent,
    FileUploadComponent,
    FormComponent,
    InputComponent,
    LoadingComponent,
    SelectComponent,
    StatTileComponent,
    TableComponent,
    TabsComponent,
    TextareaComponent,
  ],
  templateUrl: './client-intake.component.html',
  styleUrl: './client-intake.component.sass',
})
export class ClientIntakeComponent implements OnInit {
  readonly id = input.required<string>();
  readonly tab = input<string | undefined>(); // deep link to a section (?tab=0..6)
  private readonly intake = inject(IntakeService);
  private readonly breadcrumb = inject(BreadcrumbService);
  private readonly logger = inject(LoggerService);
  private readonly confirm = inject(ConfirmModalService);

  readonly view = signal<RecordView | null>(null);
  readonly section = signal(0);
  readonly tabLabels = computed(() => ['identification', 'physiology', 'medical', 'diet', 'sports', 'body', 'labs'].map((k) => `intake.tabs.${k}`));
  readonly record = signal<ClientRecord>(emptyRecord());
  readonly labs = signal<LabResultsResponse | null>(null);
  readonly saving = signal(false);
  readonly savedAt = signal<string | null>(null);
  readonly matching = signal<RecordView['matching'] | null>(null);
  readonly importMessage = signal<string | null>(null);

  readonly somatotypes: Option[] = [
    { value: 'ectomorfo', label: 'Ectomorfo' },
    { value: 'mesomorfo', label: 'Mesomorfo' },
    { value: 'endomorfo', label: 'Endomorfo' },
  ];
  readonly yesNo: Option<string>[] = [
    { value: 'true', label: 'Sí' },
    { value: 'false', label: 'No' },
  ];
  /**
   * Los campos de una lectura a mano SON los que la báscula exporta (verificado contra `pipeline_v3/scale.py`, que abre
   * el `.bin`). Se declaran una vez y la plantilla los recorre, para que añadir una magnitud sea una línea y no cinco
   * sitios. El músculo va en KILOS porque es lo que el aparato mide; el porcentaje se queda aparte y no se convierte.
   *
   * La unidad va dentro de la ETIQUETA y no como sufijo del campo: con once campos en una rejilla, el sufijo se
   * montaba encima de la etiqueta flotante de Material («Complexión» y «9» pisándose), y además es lo único que
   * distingue los dos campos de músculo.
   */
  readonly manualFields: { key: keyof NewBodyMeasurement; label: string; step: string }[] = [
    { key: 'weight_kg', label: 'intake.body.weight', step: '0.1' },
    { key: 'body_fat_pct', label: 'intake.body.fat', step: '0.1' },
    { key: 'muscle_mass_kg', label: 'intake.body.muscleMass', step: '0.1' },
    { key: 'muscle_pct', label: 'intake.body.musclePct', step: '0.1' },
    { key: 'water_pct', label: 'intake.body.water', step: '0.1' },
    { key: 'bone_kg', label: 'intake.body.bone', step: '0.1' },
    { key: 'visceral_fat_rating', label: 'intake.body.visceral', step: '0.1' },
    { key: 'physique_rating', label: 'intake.body.physique', step: '1' },
    { key: 'metabolic_age', label: 'intake.body.metabolicAge', step: '1' },
    { key: 'basal_met_kcal', label: 'intake.body.basalMet', step: '1' },
    { key: 'height_cm', label: 'intake.body.height', step: '1' },
  ];
  readonly manual = signal<Record<string, string | number | null>>({});
  readonly manualDate = signal<string | null>(null);
  readonly newLab = signal<NewLabResult>({ marker: '', value: null, unit: null, ref_low: null, ref_high: null, measured_at: null });
  readonly labDate = signal<string | null>(null);
  readonly labColumns: TableColumn[] = [
    { key: 'marker', label: 'Marcador' },
    { key: 'value', label: 'Valor', align: 'right' },
    { key: 'unit', label: 'Unidad' },
    { key: 'range', label: 'Referencia' },
    { key: 'status', label: 'Estado' },
    { key: 'source', label: 'Origen' },
    { key: 'actions', label: '', align: 'right', width: '48px' },
  ];
  readonly measurementColumns: TableColumn[] = [
    { key: 'measured_at', label: 'Fecha' },
    { key: 'weight_kg', label: 'Peso (kg)', align: 'right' },
    { key: 'body_fat_pct', label: 'Grasa (%)', align: 'right' },
    { key: 'muscle_mass_kg', label: 'Músculo (kg)', align: 'right' },
    { key: 'muscle_pct', label: 'Músculo (%)', align: 'right' },
    { key: 'water_pct', label: 'Agua (%)', align: 'right' },
    { key: 'bone_kg', label: 'Hueso (kg)', align: 'right' },
    { key: 'visceral_fat_rating', label: 'Visceral', align: 'right' },
    { key: 'physique_rating', label: 'Complexión', align: 'right' },
    { key: 'metabolic_age', label: 'Edad metab.', align: 'right' },
    { key: 'basal_met_kcal', label: 'Basal (kcal)', align: 'right' },
    { key: 'height_cm', label: 'Altura (cm)', align: 'right' },
    { key: 'source', label: 'Origen' },
  ];
  /**
   * Las analíticas de la persona, una por fecha, la más reciente primero. Antes se volcaban TODAS las filas de TODAS
   * las fechas en una sola tabla: para un cliente con 489 mediciones eso no es «una analítica», es un montón sin
   * separar, y no se podía leer un informe concreto. Ahora se elige uno y se ve su detalle.
   */
  readonly labReports = computed<LabReport[]>(() => groupIntoReports(this.labs()?.rows ?? []));
  readonly selectedReport = signal<string | null>(null);
  /** Sin elección explícita, la más reciente: entrar en la pestaña y no ver nada no ayuda a nadie. */
  readonly currentReport = computed<LabReport | null>(() => {
    const reports = this.labReports();
    const picked = reports.find((r) => r.key === this.selectedReport());
    return picked ?? reports[0] ?? null;
  });
  readonly reportRows = computed(() => this.labReports() as unknown as Record<string, unknown>[]);
  readonly labRows = computed(() => (this.currentReport()?.rows ?? []) as unknown as Record<string, unknown>[]);
  readonly reportColumns: TableColumn[] = [
    { key: 'measured_at', label: 'Fecha de la analítica' },
    { key: 'markers', label: 'Marcadores', align: 'right' },
    { key: 'out_of_range', label: 'Fuera de rango', align: 'right' },
    { key: 'sources', label: 'Origen' },
  ];
  readonly measurementRows = computed(() => (this.view()?.measurements ?? []).slice().reverse() as unknown as Record<string, unknown>[]);
  readonly missingAlgorithm = computed<Chip[]>(() => (this.view()?.completeness.algorithm.missing ?? []).map((m) => ({ label: m.label, tone: 'warn' })));
  readonly missingRecord = computed<Chip[]>(() => (this.view()?.completeness.record.missing ?? []).map((m) => ({ label: m.label })));
  readonly engineRestrictions = computed<Chip[]>(() => (this.view()?.client.restrictions ?? []).map((r) => ({ label: restrictionLabel(r), tone: 'danger' })));
  readonly engineDisliked = computed<Chip[]>(() =>
    (this.view()?.client.disliked_foods ?? []).map((f) => ({ label: f.canonical_name ?? String(f.food_id), tone: 'warn' })),
  );
  readonly engineSupplements = computed<Chip[]>(() =>
    (this.view()?.client.supplements_owned ?? []).map((f) => ({ label: f.canonical_name ?? String(f.food_id), tone: 'accent' })),
  );
  readonly matchedText = computed(() => (this.matching()?.['disliked_foods']?.matched ?? []).map((x) => x.canonical_name).join(', '));

  ngOnInit(): void {
    const t = Number(this.tab());
    if (Number.isInteger(t) && t >= 0 && t < 7) this.section.set(t);
    this.reload();
    this.intake.labs(this.id()).subscribe((l) => this.labs.set(l));
  }

  reload(): void {
    this.intake.record(this.id()).subscribe((v) => {
      this.view.set(v);
      this.breadcrumb.set(v.client.full_name);
      this.record.set({ ...emptyRecord(), ...v.record });
    });
  }

  // ------------------------------------------------------------------------------------------------------ record
  patch<K extends keyof ClientRecord>(block: K, field: string, value: unknown): void {
    this.record.update((r) => ({ ...r, [block]: { ...(r[block] as object), [field]: value } }));
  }

  boolValue(v: boolean | null | undefined): string | null {
    return v == null ? null : String(v);
  }

  save(): void {
    this.saving.set(true);
    this.intake.saveRecord(this.id(), this.record()).subscribe({
      next: (v) => {
        this.view.set(v);
        this.matching.set(v.matching ?? null);
        this.savedAt.set(new Date().toLocaleTimeString('es-ES'));
        this.saving.set(false);
      },
      error: () => this.saving.set(false),
    });
  }

  // ------------------------------------------------------------------------------------------------------ body composition
  onScaleFile(f: UploadedFile): void {
    try {
      this.intake.importScale(this.id(), f.content).subscribe((r) => {
        this.view.set(r);
        this.importMessage.set(`${r.measurements_added} mediciones importadas · ${r.users_seen} usuario(s) leídos (nombre y correo ignorados)`);
      });
    } catch {
      this.logger.error('El fichero de la báscula no es JSON válido');
    }
  }

  patchManual(key: string, value: unknown): void {
    this.manual.update((m) => ({ ...m, [key]: value as string | number | null }));
  }

  manualValue(key: string): string | number | null {
    return this.manual()[key] ?? null;
  }

  addManual(): void {
    const typed = this.manual();
    if (typed['weight_kg'] == null || typed['weight_kg'] === '') return;
    const reading: NewBodyMeasurement = { measured_at: this.manualDate() };
    for (const f of this.manualFields) {
      const v = typed[f.key as string];
      if (v !== null && v !== undefined && v !== '') (reading as Record<string, unknown>)[f.key as string] = Number(v);
    }
    this.intake.addMeasurement(this.id(), reading).subscribe((v) => {
      this.view.set(v);
      this.manual.set({});
      this.manualDate.set(null);
    });
  }

  // ------------------------------------------------------------------------------------------------------ lab results
  onLabFile(f: UploadedFile): void {
    this.intake.importLabs(this.id(), f.content, this.labDate()).subscribe((l) => {
      this.labs.set(l);
      this.selectedReport.set(l.added?.[0]?.measured_at ?? this.labDate() ?? null);
      this.importMessage.set(
        `${l.added?.length ?? 0} filas importadas${l.rejected?.length ? ` · ${l.rejected.length} rechazadas: ${l.rejected.join('; ')}` : ''}`,
      );
    });
  }

  pickReport(row: Record<string, unknown>): void {
    this.selectedReport.set(String((row as unknown as LabReport).key));
  }

  patchLab(field: keyof NewLabResult, value: unknown): void {
    this.newLab.update((r) => ({ ...r, [field]: value }));
  }

  addLab(): void {
    const r = this.newLab();
    if (!r.marker.trim() || r.value == null) return;
    this.intake.addLabs(this.id(), [{ ...r, measured_at: r.measured_at ?? this.labDate() }]).subscribe((l) => {
      this.labs.set(l);
      this.selectedReport.set(r.measured_at ?? this.labDate() ?? '');
      this.newLab.set({ marker: '', value: null, unit: null, ref_low: null, ref_high: null, measured_at: null });
    });
  }

  deleteLab(row: Record<string, unknown>): void {
    const r = row as unknown as LabResult;
    this.confirm.confirm({ title: 'Borrar marcador', message: `${r.marker} ${r.value} ${r.unit ?? ''}`, danger: true }).subscribe((ok) => {
      if (ok && r.id != null) this.intake.deleteLab(this.id(), r.id).subscribe((l) => this.labs.set(l));
    });
  }

  range(r: LabResult): string {
    if (r.ref_low == null && r.ref_high == null) return '—';
    return `${r.ref_low ?? '—'} – ${r.ref_high ?? '—'}`;
  }

  statusTone(s: string): 'ok' | 'warn' | 'danger' | 'neutral' {
    return s === 'en_rango' ? 'ok' : s === 'alto' ? 'danger' : s === 'bajo' ? 'warn' : 'neutral';
  }

  pct(v: number | null | undefined): string {
    return v == null ? '—' : `${Math.round(v * 100)} %`;
  }
}
