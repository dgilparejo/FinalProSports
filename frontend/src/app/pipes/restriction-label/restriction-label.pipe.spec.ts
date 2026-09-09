import { RestrictionLabelPipe } from './restriction-label.pipe';

describe('RestrictionLabelPipe', () => {
  it('translates RestrictionKind values', () => {
    const pipe = new RestrictionLabelPipe();
    expect(pipe.transform('contains_lactose')).toBe('Lactosa');
    expect(pipe.transform('is_tree_nut')).toBe('Frutos de cáscara');
    expect(pipe.transform('otra')).toBe('otra');
  });
});
