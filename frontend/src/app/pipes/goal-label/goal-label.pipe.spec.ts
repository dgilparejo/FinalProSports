import { GoalLabelPipe } from './goal-label.pipe';

describe('GoalLabelPipe', () => {
  it('translates goal values and falls back to the value or a dash', () => {
    const pipe = new GoalLabelPipe();
    expect(pipe.transform('cetosis_keto')).toBe('Cetosis (keto)');
    expect(pipe.transform('otro')).toBe('otro');
    expect(pipe.transform(null)).toBe('—');
  });
});
