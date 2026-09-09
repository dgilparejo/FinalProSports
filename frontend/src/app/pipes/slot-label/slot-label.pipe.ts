import { Pipe, PipeTransform } from '@angular/core';

import { slotLabel } from '@models/common';

@Pipe({ name: 'slotLabel' })
export class SlotLabelPipe implements PipeTransform {
  transform(value: string): string {
    return slotLabel(value);
  }
}
