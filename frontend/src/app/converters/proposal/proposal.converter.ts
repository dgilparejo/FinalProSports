import { Proposal, ProposedMeal, ProposedOption, SaveDietBody } from '@models/diet';

const BODY_KEYS = ['profile', 'strategy', 'parameters', 'retrieved_case_ids', 'meals', 'notes', 'validation'] as const;

/** The subset of a proposal the API accepts back (the routing, gap, context and diff are read-only decorations). */
export function toProposalBody(p: Proposal): Record<string, unknown> {
  return Object.fromEntries(BODY_KEYS.map((k) => [k, p[k]]));
}

export function toSaveBody(edited: Proposal, original: Proposal | null): SaveDietBody {
  const body = toProposalBody(edited) as Omit<SaveDietBody, 'edited' | 'original'>;
  return { ...body, edited: true, original: original ? toProposalBody(original) : null };
}

/** Deep copy so the professional's edits never touch the original proposal (the diff needs it untouched). */
export function cloneProposal(p: Proposal): Proposal {
  return JSON.parse(JSON.stringify(p)) as Proposal;
}

export function itemCount(meals: ProposedMeal[]): number {
  return meals.reduce((n, m) => n + m.groups.reduce((k, g) => k + g.options.length, 0), 0);
}

export function newOption(foodId: number, name: string, quantity: number | null, unit: string): ProposedOption {
  return {
    food_id: foodId,
    canonical_name: name,
    normalized_key: name,
    text: quantity != null ? `${quantity} ${unit} ${name}`.trim() : name,
    quantity,
    unit,
    alternative_group: null,
    note: null,
    evidence: { support: 0, cases: [], rules: [] },
  };
}

export function isProfessionalAddition(o: ProposedOption): boolean {
  return o.evidence.support === 0 && o.evidence.cases.length === 0 && o.evidence.rules.length === 0;
}
