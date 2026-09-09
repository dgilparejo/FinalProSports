import { Component, input } from '@angular/core';
import { MatProgressBarModule } from '@angular/material/progress-bar';

import { LoadingConstants } from '@models/components/loading';

@Component({
  selector: 'app-loading',
  imports: [MatProgressBarModule],
  template: `@if (active()) {
    <mat-progress-bar [mode]="MODE" [style.height.px]="HEIGHT_PX" />
  }`,
  styles: `
    :host {
      display: block;
      min-height: 3px;
    }
  `,
})
export class LoadingComponent extends LoadingConstants {
  readonly active = input(true);
  readonly MODE = LoadingConstants.MODE;
  readonly HEIGHT_PX = LoadingConstants.HEIGHT_PX;
}
