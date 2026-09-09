/** Every REST endpoint of the application, in one place (S8). Paths are relative to environment.apiBaseUrl. */
export type DietFormat = 'pdf' | 'odt';

export const URLS = {
  clients: 'clients',
  client: (id: string) => `clients/${encodeURIComponent(id)}`,
  clientDiets: (id: string) => `clients/${encodeURIComponent(id)}/diets`,
  record: (id: string) => `clients/${encodeURIComponent(id)}/record`,
  bodyComposition: (id: string) => `clients/${encodeURIComponent(id)}/body-composition`,
  bodyCompositionImport: (id: string) => `clients/${encodeURIComponent(id)}/body-composition/import`,
  labResults: (id: string) => `clients/${encodeURIComponent(id)}/lab-results`,
  labResultsImport: (id: string) => `clients/${encodeURIComponent(id)}/lab-results/import`,
  labResult: (clientId: string, resultId: number) => `clients/${encodeURIComponent(clientId)}/lab-results/${resultId}`,
  propose: 'diets/propose',
  diets: 'diets',
  diet: (id: string) => `diets/${encodeURIComponent(id)}`,
  dietPdf: (id: string) => `diets/${encodeURIComponent(id)}/pdf`,
  /** The document in the format the professional chooses. The PDF is what he hands to the client; the .odt is the one
   *  he can still edit, which is what he does today with each client's previous version. */
  dietExport: (id: string, format: DietFormat) => `diets/${encodeURIComponent(id)}/export?format=${format}`,
  foods: 'catalog/foods',
  rules: 'rules?include_low_confidence=true',
} as const;
