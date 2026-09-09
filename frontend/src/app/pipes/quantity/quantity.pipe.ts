import { Pipe, PipeTransform } from '@angular/core';

/** «150 g pollo» — quantity, unit and name in the professional's line order; tabular figures come from the .num class. */
@Pipe({ name: 'quantity' })
export class QuantityPipe implements PipeTransform {
  transform(item: { quantity: number | null; unit: string; canonical_name: string | null; text?: string } | null | undefined): string {
    if (!item) return '';
    const name = item.canonical_name || item.text || '';
    if (item.quantity == null) return name;
    const q = Number.isInteger(item.quantity) ? String(item.quantity) : item.quantity.toLocaleString('es-ES', { maximumFractionDigits: 2 });
    return [q, item.unit, name].filter(Boolean).join(' ');
  }
}
