import { Pipe, PipeTransform } from '@angular/core';

import { restrictionLabel } from '@models/common';

@Pipe({ name: 'restrictionLabel' })
export class RestrictionLabelPipe implements PipeTransform {
  transform(value: string): string {
    return restrictionLabel(value);
  }
}
