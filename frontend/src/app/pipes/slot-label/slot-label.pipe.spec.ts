import { SlotLabelPipe } from './slot-label.pipe';

describe('SlotLabelPipe', () => {
  it('translates corpus slot literals', () => {
    const pipe = new SlotLabelPipe();
    expect(pipe.transform('MEDIA MAÑANA')).toBe('Media mañana');
    expect(pipe.transform('DESPUES DE ENTRENAR')).toBe('Después de entrenar');
    expect(pipe.transform('X')).toBe('X');
  });
});
