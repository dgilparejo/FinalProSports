import { LabResult, groupIntoReports } from './lab.model';

function row(marker: string, measured_at: string | null, out = false, source: 'manual' | 'file' = 'file'): LabResult {
  return {
    id: Math.floor(Math.random() * 1e6),
    marker,
    value: 1,
    unit: null,
    ref_low: out ? 10 : null,
    ref_high: null,
    measured_at,
    note: null,
    source,
    status: out ? 'bajo' : 'sin_rango',
    out_of_range: out,
  };
}

describe('groupIntoReports', () => {
  it('groups the rows into one analysis per date, most recent first', () => {
    const reports = groupIntoReports([
      row('Glucosa', '2026-01-10'),
      row('HDL', '2026-06-02'),
      row('Ferritina', '2026-01-10'),
      row('LDL', '2026-06-02'),
      row('TSH', '2026-06-02'),
    ]);
    expect(reports.map((r) => r.measured_at)).toEqual(['2026-06-02', '2026-01-10']);
    expect(reports.map((r) => r.markers)).toEqual([3, 2]);
  });

  it('counts the markers out of range of each analysis on its own', () => {
    const reports = groupIntoReports([row('Glucosa', '2026-06-02', true), row('HDL', '2026-06-02'), row('LDL', '2026-01-10', true)]);
    expect(reports.map((r) => r.out_of_range)).toEqual([1, 1]);
    expect(reports[0].markers).toBe(2);
  });

  it('keeps the rows with no date as their own group instead of dropping them', () => {
    const reports = groupIntoReports([row('Glucosa', null), row('HDL', '2026-06-02')]);
    expect(reports.length).toBe(2);
    expect(reports.find((r) => r.measured_at === null)?.markers).toBe(1);
  });

  it('orders the markers of an analysis alphabetically and lists its sources', () => {
    const reports = groupIntoReports([row('TSH', '2026-06-02', false, 'manual'), row('Glucosa', '2026-06-02', false, 'file')]);
    expect(reports[0].rows.map((r) => r.marker)).toEqual(['Glucosa', 'TSH']);
    expect(reports[0].sources).toEqual(['file', 'manual']);
  });

  it('is empty for a client with no analysis', () => {
    expect(groupIntoReports([])).toEqual([]);
  });
});
