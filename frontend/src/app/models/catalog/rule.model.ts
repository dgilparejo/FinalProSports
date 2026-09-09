export interface Rule {
  id: string;
  statement: string;
  scope: string;
  status: string;
  confidence: string | null;
  n_support: number | null;
  lift: number | null;
  adjusted: number | null;
  enabled: boolean;
}
