import { Client } from '@models/client';

/** API response -> domain model. Defensive defaults so a partial payload never breaks a page. */
export function toClient(raw: Partial<Client> & { id: string }): Client {
  return {
    id: raw.id,
    full_name: raw.full_name ?? null,
    birth_date: raw.birth_date ?? null,
    phone: raw.phone ?? null,
    email: raw.email ?? null,
    sex: raw.sex ?? null,
    age: raw.age ?? null,
    age_bucket: raw.age_bucket ?? 'edad_NA',
    height_cm: raw.height_cm ?? null,
    activity_level: raw.activity_level ?? null,
    goal: raw.goal ?? null,
    is_athlete: raw.is_athlete ?? null,
    has_allergies: !!raw.has_allergies,
    has_intolerances: !!raw.has_intolerances,
    has_medical_restrictions: !!raw.has_medical_restrictions,
    restrictions: raw.restrictions ?? [],
    diet_count: raw.diet_count ?? 0,
  };
}

export function toClients(rows: (Partial<Client> & { id: string })[]): Client[] {
  return rows.map(toClient);
}

export function sexLabel(sex: 'M' | 'F' | null | undefined): string {
  return sex === 'M' ? 'Hombre' : sex === 'F' ? 'Mujer' : '—';
}

/** What a person reads: the name; a client without one (should not happen: the registration requires it) shows a neutral label. */
export function displayName(c: { full_name?: string | null } | null | undefined, fallback = 'Cliente sin nombre'): string {
  return c?.full_name?.trim() || fallback;
}

/** `eNN` of a saved diet id `<client id>::eNN`; the internal key is never shown. */
export function versionLabel(dietId: string | null | undefined): string {
  return dietId?.split('::').pop() ?? '';
}
