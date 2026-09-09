import { QuantityPipe } from './quantity.pipe';

describe('QuantityPipe', () => {
  it('renders quantity, unit and name in the professional order', () => {
    const pipe = new QuantityPipe();
    expect(pipe.transform({ quantity: 150, unit: 'g', canonical_name: 'pollo' })).toBe('150 g pollo');
    expect(pipe.transform({ quantity: 1, unit: 'unidad', canonical_name: 'plátano' })).toBe('1 unidad plátano');
    expect(pipe.transform({ quantity: null, unit: '', canonical_name: 'sacarina' })).toBe('sacarina');
    expect(pipe.transform({ quantity: 17.5, unit: 'g', canonical_name: null, text: 'almendras' })).toBe('17,5 g almendras');
    expect(pipe.transform(null)).toBe('');
  });
});
