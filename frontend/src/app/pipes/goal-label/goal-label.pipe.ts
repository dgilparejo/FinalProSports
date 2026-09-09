import { Pipe, PipeTransform } from '@angular/core';

import { goalLabel } from '@models/common';

@Pipe({ name: 'goalLabel' })
export class GoalLabelPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    return goalLabel(value);
  }
}
