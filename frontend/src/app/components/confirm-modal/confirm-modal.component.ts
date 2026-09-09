import { Component, Injectable, inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { TranslatePipe } from '@ngx-translate/core';
import { Observable } from 'rxjs';

import { ConfirmModalConstants } from '@models/components/confirm-modal';

import { ButtonComponent } from '../button/button.component';

export interface ConfirmData {
  title: string;
  message: string;
  danger?: boolean;
}

@Component({
  selector: 'app-confirm-modal',
  imports: [MatDialogModule, ButtonComponent, TranslatePipe],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content
      ><p>{{ data.message }}</p></mat-dialog-content
    >
    <mat-dialog-actions align="end">
      <app-button variant="ghost" (clicked)="ref.close(false)">{{ CANCEL_KEY | translate }}</app-button>
      <app-button [variant]="data.danger ? 'danger' : 'primary'" (clicked)="ref.close(true)">{{ CONFIRM_KEY | translate }}</app-button>
    </mat-dialog-actions>
  `,
})
export class ConfirmModalComponent extends ConfirmModalConstants {
  readonly ref = inject(MatDialogRef<ConfirmModalComponent>);
  readonly data = inject<ConfirmData>(MAT_DIALOG_DATA);
  readonly CONFIRM_KEY = ConfirmModalConstants.CONFIRM_KEY;
  readonly CANCEL_KEY = ConfirmModalConstants.CANCEL_KEY;
}

/** `confirm(...)` returns an Observable<boolean>; pages never touch MatDialog for confirmations. */
@Injectable({ providedIn: 'root' })
export class ConfirmModalService {
  private readonly dialog = inject(MatDialog);

  confirm(data: ConfirmData): Observable<boolean> {
    return this.dialog
      .open(ConfirmModalComponent, { data, width: ConfirmModalConstants.WIDTH, maxWidth: ConfirmModalConstants.MAX_WIDTH })
      .afterClosed() as Observable<boolean>;
  }
}
