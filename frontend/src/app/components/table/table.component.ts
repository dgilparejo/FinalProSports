import { NgTemplateOutlet } from '@angular/common';
import { Component, TemplateRef, contentChild, input, output } from '@angular/core';
import { MatTableModule } from '@angular/material/table';
import { TranslatePipe } from '@ngx-translate/core';

import { TableConstants } from '@models/components/table';

export interface TableColumn {
  key: string;
  label: string;
  align?: (typeof TableConstants.ALIGNMENTS)[number];
  width?: string;
}

/** Compact data table (34 px rows). Cells render the row's field by key, or a projected `<ng-template let-row let-col="col">` when given. */
@Component({
  selector: 'app-table',
  imports: [MatTableModule, NgTemplateOutlet, TranslatePipe],
  template: `
    <table mat-table [dataSource]="rows()" class="table">
      @for (col of columns(); track col.key) {
        <ng-container [matColumnDef]="col.key">
          <th mat-header-cell *matHeaderCellDef [style.text-align]="col.align ?? 'left'" [style.width]="col.width ?? null">{{ col.label }}</th>
          <td mat-cell *matCellDef="let row" [style.text-align]="col.align ?? 'left'" [class.num]="col.align === 'right'">
            @if (cell()) {
              <ng-container *ngTemplateOutlet="cell()!; context: { $implicit: row, col: col }" />
            } @else {
              {{ row[col.key] ?? '—' }}
            }
          </td>
        </ng-container>
      }
      <tr mat-header-row *matHeaderRowDef="keys()"></tr>
      <tr mat-row *matRowDef="let row; columns: keys()" (click)="rowClicked.emit(row)" [class.clickable]="clickable()"></tr>
    </table>
    @if (!rows().length) {
      <p class="muted small empty">{{ EMPTY_KEY | translate }}</p>
    }
  `,
  styles: `
    :host {
      display: block;
      overflow-x: auto;
    }
    .table {
      width: 100%;
    }
    tr.clickable {
      cursor: pointer;
    }
    tr.clickable:hover td {
      background: var(--surface-alt);
    }
    .empty {
      padding: 12px 0;
    }
  `,
})
export class TableComponent<T extends Record<string, unknown> = Record<string, unknown>> extends TableConstants {
  readonly columns = input.required<TableColumn[]>();
  readonly rows = input.required<T[]>();
  readonly clickable = input(false);
  readonly rowClicked = output<T>();
  readonly cell = contentChild<TemplateRef<unknown>>('cell');
  readonly EMPTY_KEY = TableConstants.EMPTY_KEY;

  keys(): string[] {
    return this.columns().map((c) => c.key);
  }
}
