import { ClientRef } from '@models/client';

import { LabContext } from '../client/lab.model';

export interface RuleSupport {
  rule_id: string;
  prevalence: number | null;
  lift: number | null;
}
export interface Evidence {
  support: number;
  cases: string[];
  rules: RuleSupport[];
}
export interface ProposedOption {
  food_id: number | null;
  canonical_name: string | null;
  normalized_key: string;
  text: string;
  quantity: number | null;
  unit: string;
  alternative_group: string | null;
  note: string | null;
  evidence: Evidence;
}
export interface ProposedGroup {
  position: number;
  options: ProposedOption[];
}
export interface ProposedMeal {
  slot: string;
  groups: ProposedGroup[];
}
export interface RuleCheck {
  rule_id: string;
  applicable: boolean;
  satisfied: boolean | null;
  enforced: boolean;
}
export interface ForcedChange {
  slot: string;
  food_id: number | null;
  canonical_name: string | null;
  action: string;
  reason: string;
}
export interface Validation {
  compliance: number | null;
  rules: RuleCheck[];
  forced_changes: ForcedChange[];
  warnings: string[];
}
export interface Routing {
  code: 'cold_start' | 'same_goal' | 'goal_changed' | string;
  label: string;
  strategy: string;
  previous_version: string | null;
  rotated_items: number | null;
  renewal_applied: number | null;
  renewal_target: number | null;
  degradation: string | null;
  k_effective: number | null;
  same_goal_cases: number | null;
}
export interface Gap {
  kind: string;
  triggered: string[];
  counts: Record<string, number>;
  best_score: number | null;
  threshold: number;
}
export interface PlausibilityChange {
  kind: string;
  slot: string;
  food_id: number | null;
  canonical_name: string | null;
  detail: string;
}
export interface ItemChange {
  slot: string;
  food_id: number | null;
  canonical_name: string | null;
  change: string;
  before: string | null;
  after: string | null;
}
export interface ProposalDiff {
  items_added: ItemChange[];
  items_removed: ItemChange[];
  items_changed: ItemChange[];
  items_moved: ItemChange[];
  slots_added: string[];
  slots_removed: string[];
  notes_added: string[];
  notes_removed: string[];
  proposed_items: number;
  kept_unchanged: number;
  edit_ratio: number;
  is_edited: boolean;
  summary: Record<string, number>;
}
export interface FoodRef {
  food_id: number;
  canonical_name: string | null;
}
export interface Proposal {
  id?: string;
  profile: Record<string, unknown>;
  strategy: string;
  parameters: Record<string, unknown> & { plausibility?: { applied: boolean; changes: PlausibilityChange[] } };
  retrieved_case_ids: string[];
  meals: ProposedMeal[];
  notes: string[];
  validation: Validation | null;
  routing: Routing;
  gap: Gap | null;
  owned_supplements?: FoodRef[];
  client?: ClientRef | null;
  context?: { lab_results: LabContext };
  diff?: ProposalDiff | null;
  edited?: boolean;
  created_at?: string | null;
}
/** What POST /diets accepts: the proposal body plus the edited flag and the untouched original (S5 diff). */
export interface SaveDietBody {
  profile: Record<string, unknown>;
  strategy: string;
  parameters: Record<string, unknown>;
  retrieved_case_ids: string[];
  meals: ProposedMeal[];
  notes: string[];
  validation: Validation | null;
  edited: boolean;
  original: Record<string, unknown> | null;
}

export interface HistoryItem {
  food_id: number | null;
  canonical_name: string | null;
  text: string;
  quantity: number | null;
  unit: string;
  alternative_group: string | null;
}
export interface HistoryVersion {
  id: string;
  goal: string;
  diet_version: number | null;
  template_group_id: string | null;
  slots: string[];
  items: number;
  notes: number;
  meals: { slot: string; items: HistoryItem[] }[];
}
export interface SavedSummary {
  id: string;
  created_at: string;
  goal: string;
  strategy: string;
  edited: boolean;
  edit_ratio: number | null;
}
export interface ClientDiets {
  versions: HistoryVersion[];
  saved: SavedSummary[];
}
