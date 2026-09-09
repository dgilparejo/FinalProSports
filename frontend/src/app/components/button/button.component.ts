import { Component, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { NgTemplateOutlet } from '@angular/common';

import { ButtonConstants } from '@models/components/button';

/** The only component that knows Material's button. Pages use `app-button`; changing the UI library touches this file alone. */
@Component({
  selector: 'app-button',
  imports: [MatButtonModule, MatIconModule, NgTemplateOutlet],
  template: `
    <ng-template #label><ng-content /></ng-template>
    @switch (variant()) {
      @case ('primary') {
        <button mat-flat-button [type]="type()" [disabled]="disabled()" (click)="clicked.emit($event)" [attr.aria-label]="ariaLabel()">
          @if (icon()) {
            <mat-icon>{{ icon() }}</mat-icon>
          }
          <ng-container *ngTemplateOutlet="label" />
        </button>
      }
      @case ('ghost') {
        <button mat-button [type]="type()" [disabled]="disabled()" (click)="clicked.emit($event)" [attr.aria-label]="ariaLabel()">
          @if (icon()) {
            <mat-icon>{{ icon() }}</mat-icon>
          }
          <ng-container *ngTemplateOutlet="label" />
        </button>
      }
      @case ('danger') {
        <button mat-stroked-button class="danger" [type]="type()" [disabled]="disabled()" (click)="clicked.emit($event)" [attr.aria-label]="ariaLabel()">
          @if (icon()) {
            <mat-icon>{{ icon() }}</mat-icon>
          }
          <ng-container *ngTemplateOutlet="label" />
        </button>
      }
      @case ('icon') {
        <button mat-icon-button [type]="type()" [disabled]="disabled()" (click)="clicked.emit($event)" [attr.aria-label]="ariaLabel()">
          <mat-icon>{{ icon() }}</mat-icon>
        </button>
      }
      @default {
        <button mat-stroked-button [type]="type()" [disabled]="disabled()" (click)="clicked.emit($event)" [attr.aria-label]="ariaLabel()">
          @if (icon()) {
            <mat-icon>{{ icon() }}</mat-icon>
          }
          <ng-container *ngTemplateOutlet="label" />
        </button>
      }
    }
  `,
  styles: `
    :host {
      display: inline-flex;
    }
    button.danger {
      --mat-button-outlined-label-text-color: var(--danger);
      --mat-button-outlined-outline-color: var(--danger);
    }
    mat-icon {
      font-size: 18px;
      width: 18px;
      height: 18px;
    }
  `,
})
export class ButtonComponent extends ButtonConstants {
  readonly variant = input<(typeof ButtonConstants.VARIANTS)[number]>(ButtonConstants.DEFAULT_VARIANT);
  readonly type = input<'button' | 'submit'>(ButtonConstants.DEFAULT_TYPE);
  readonly icon = input<string | null>(null);
  readonly disabled = input(false);
  readonly ariaLabel = input<string | null>(null);
  readonly clicked = output<Event>();
}
