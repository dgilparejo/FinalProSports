import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from '@components/button/button.component';
import { Chip, ChipsComponent } from '@components/chips/chips.component';
import { InputComponent } from '@components/input/input.component';
import { LoadingComponent } from '@components/loading/loading.component';
import { TableColumn, TableComponent } from '@components/table/table.component';
import { displayName, sexLabel } from '@converters/client/client.converter';
import { Client, RegisterClient } from '@models/client';
import { restrictionLabel } from '@models/common';
import { GoalLabelPipe } from '@pipes/goal-label/goal-label.pipe';
import { ClientsService } from '@services/clients/clients/clients.service';
import { LayoutService } from '@services/layout/layout.service';

import { RegisterClientDialogComponent } from './components/register-client-dialog/register-client-dialog.component';

/** Portfolio of the professional (S1, S9): clients BY NAME (the key is an internal UUID nobody types); empty on a clean installation. */
@Component({
  selector: 'app-clients',
  imports: [RouterLink, TranslatePipe, ButtonComponent, ChipsComponent, InputComponent, LoadingComponent, TableComponent, GoalLabelPipe],
  templateUrl: './clients.component.html',
  styleUrl: './clients.component.sass',
})
export class ClientsComponent implements OnInit {
  private readonly clients = inject(ClientsService);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  readonly layout = inject(LayoutService);

  readonly register = input<string | undefined>(); // ?register=1 opens the registration dialog (deep link)
  readonly all = signal<Client[]>([]);
  readonly filter = signal<string | number | null>('');
  readonly loading = signal(true);
  readonly rows = computed(() => {
    const f = String(this.filter() ?? '')
      .trim()
      .toUpperCase();
    return (f ? this.all().filter((c) => displayName(c).toUpperCase().includes(f)) : this.all()) as unknown as Record<string, unknown>[];
  });
  /**
   * Las mismas filas ya filtradas, con su tipo. La tabla trabaja con registros anónimos porque pinta por clave; las
   * tarjetas leen campos concretos y necesitan el tipo de vuelta.
   */
  readonly cards = computed<Client[]>(() => this.rows() as unknown as Client[]);
  readonly columns: TableColumn[] = [
    { key: 'full_name', label: 'Nombre' },
    { key: 'sex', label: 'Sexo' },
    { key: 'age', label: 'Edad', align: 'right', width: '64px' },
    { key: 'goal', label: 'Objetivo declarado' },
    { key: 'restrictions', label: 'Restricciones' },
    { key: 'diet_count', label: 'Dietas guardadas', align: 'right', width: '120px' },
    { key: 'actions', label: '', align: 'right', width: '220px' },
  ];
  readonly sexLabel = sexLabel;
  readonly displayName = displayName;

  ngOnInit(): void {
    this.load();
    if (this.register() === '1') setTimeout(() => this.openRegister());
  }

  load(): void {
    this.loading.set(true);
    this.clients.list().subscribe({
      next: (cs) => {
        this.all.set(cs);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  restrictionChips(c: Client): Chip[] {
    const chips: Chip[] = c.restrictions.map((r) => ({ label: restrictionLabel(r), tone: 'danger' }));
    if (!chips.length && (c.has_allergies || c.has_intolerances)) chips.push({ label: 'declaradas sin estructurar', tone: 'warn' });
    return chips;
  }

  openRegister(): void {
    this.dialog
      .open(RegisterClientDialogComponent, { width: '560px', maxWidth: '95vw' })
      .afterClosed()
      .subscribe((form: RegisterClient | undefined) => {
        if (form) this.clients.register(form).subscribe((c) => this.router.navigate(['/clients', c.id, 'intake']));
      });
  }

  open(row: Record<string, unknown>): void {
    this.router.navigate(['/clients', row['id']]);
  }
}
