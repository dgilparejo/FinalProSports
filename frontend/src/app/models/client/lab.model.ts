export type LabStatus = 'bajo' | 'alto' | 'en_rango' | 'sin_rango';

export interface LabResult {
  id: number | null;
  marker: string;
  value: number;
  unit: string | null;
  ref_low: number | null;
  ref_high: number | null;
  measured_at: string | null;
  note: string | null;
  source: 'manual' | 'file';
  status: LabStatus;
  out_of_range: boolean;
}

export interface LabContext {
  results: LabResult[];
  out_of_range: number;
  total_rows: number;
}

export interface LabResultsResponse extends LabContext {
  rows: LabResult[];
  added?: LabResult[];
  rejected?: string[];
}

export interface NewLabResult {
  marker: string;
  value: number | null;
  unit: string | null;
  ref_low: number | null;
  ref_high: number | null;
  measured_at: string | null;
  note?: string | null;
}

/**
 * One analysis: every row that shares a date. The grouping key is the DATE because that is all the portfolio path
 * records — two reports drawn the same day would merge, and that is stated rather than papered over.
 */
export interface LabReport {
  key: string;
  measured_at: string | null;
  markers: number;
  out_of_range: number;
  sources: string[];
  rows: LabResult[];
}

export function groupIntoReports(rows: LabResult[]): LabReport[] {
  const by = new Map<string, LabResult[]>();
  for (const r of rows) {
    const key = r.measured_at ?? '';
    (by.get(key) ?? by.set(key, []).get(key)!).push(r);
  }
  return [...by.entries()]
    .map(([key, group]) => ({
      key,
      measured_at: group[0].measured_at,
      markers: group.length,
      out_of_range: group.filter((r) => r.out_of_range).length,
      sources: [...new Set(group.map((r) => r.source))].sort(),
      rows: [...group].sort((a, b) => a.marker.toLowerCase().localeCompare(b.marker.toLowerCase())),
    }))
    .sort((a, b) => (b.measured_at ?? '').localeCompare(a.measured_at ?? ''));
}
