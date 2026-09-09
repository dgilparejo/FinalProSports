import { Proposal } from '@models/diet';

import { cloneProposal, isProfessionalAddition, itemCount, newOption, toSaveBody } from './proposal.converter';

const PROPOSAL: Proposal = {
  id: 'X',
  profile: { client_code: 'DEMO' },
  strategy: 'case_based_composer',
  parameters: { k: 20 },
  retrieved_cases: 20,
  retrieved_clients: 14,
  meals: [
    {
      slot: 'COMIDA',
      groups: [
        { position: 0, options: [newOption(1, 'pollo', 200, 'g'), newOption(2, 'pavo', 200, 'g')] },
        { position: 1, options: [newOption(3, 'arroz', 150, 'g')] },
      ],
    },
  ],
  notes: ['nota'],
  validation: null,
  routing: {
    code: 'cold_start',
    label: '',
    strategy: '',
    previous_version: null,
    rotated_items: null,
    renewal_applied: null,
    renewal_target: null,
    degradation: null,
    k_effective: 20,
    same_goal_cases: 20,
  },
  gap: null,
  context: { lab_results: { results: [], out_of_range: 0, total_rows: 0 } },
};

describe('proposal converter', () => {
  it('keeps only the body keys and attaches the original for the diff', () => {
    const body = toSaveBody(PROPOSAL, PROPOSAL);
    expect(Object.keys(body).sort()).toEqual(['edited', 'meals', 'notes', 'original', 'parameters', 'profile', 'strategy', 'validation']);
    expect(body.original && 'routing' in body.original).toBeFalse();
    expect(toSaveBody(PROPOSAL, null).original).toBeNull();
  });

  it('clones deeply, counts items and recognises professional additions', () => {
    const copy = cloneProposal(PROPOSAL);
    copy.meals[0].groups[0].options[0].quantity = 999;
    expect(PROPOSAL.meals[0].groups[0].options[0].quantity).toBe(200);
    expect(itemCount(PROPOSAL.meals)).toBe(3);
    expect(isProfessionalAddition(newOption(9, 'x', null, ''))).toBeTrue();
    expect(isProfessionalAddition({ ...newOption(9, 'x', null, ''), evidence: { support: 0.5, case_count: 1, client_count: 1, rules: [] } })).toBeFalse();
  });
});
