// Intake record (S3): the five blocks of the professional's sheet, measurements and derived estimates, as served by GET /clients/{code}/record.

export interface Identification {
  full_name: string | null;
  birth_date: string | null;
  phone: string | null;
  email: string | null;
}
export interface Physiology {
  first_visit: string | null;
  initial_weight_kg: number | null;
  height_cm: number | null;
  wrist_cm: number | null;
  waist_cm: number | null;
  neck_cm: number | null;
  hip_cm: number | null;
  somatotype: 'ectomorfo' | 'mesomorfo' | 'endomorfo' | null;
}
export interface MedicalHistory {
  allergies: string | null;
  intolerances: string | null;
  injuries: string | null;
  surgeries: string | null;
}
export interface DietPreferences {
  liked_foods: string | null;
  disliked_foods: string | null;
  food_vices: string | null;
  smokes: boolean | null;
  drinks_alcohol: boolean | null;
}
export interface SportsProfile {
  training_years: number | null;
  sports: string | null;
  achievements: string | null;
  goals_text: string | null;
  work_schedule: string | null;
  training_schedule: string | null;
  supplements_owned: string | null;
  first_diet_notes: string | null;
  watch_brand: string | null;
}
export interface ClientRecord {
  client_id?: string;
  identification: Identification;
  physiology: Physiology;
  medical: MedicalHistory;
  diet: DietPreferences;
  sports: SportsProfile;
  updated_at?: string | null;
}

/** One scale reading: the eleven magnitudes the export carries. `muscle_pct` is the only one the scale does not give (it measures kilos). */
export interface BodyMeasurement {
  measured_at: string;
  weight_kg: number | null;
  height_cm: number | null;
  body_fat_pct: number | null;
  muscle_pct: number | null;
  muscle_mass_kg: number | null;
  water_pct: number | null;
  bone_kg: number | null;
  physique_rating: number | null;
  visceral_fat_rating: number | null;
  metabolic_age: number | null;
  basal_met_kcal: number | null;
  source: 'scale' | 'manual';
}
/** A reading typed by hand: the same magnitudes, all optional but the weight. */
export type NewBodyMeasurement = Partial<Omit<BodyMeasurement, 'measured_at' | 'source'>> & { measured_at?: string | null };
export interface BodyComposition {
  body_fat_pct: number | null;
  method: string | null;
  note: string | null;
  bmi: number | null;
  frame_index: number | null;
  somatotype_hint: string | null;
}
export interface CompletenessField {
  key: string;
  label: string;
}
export interface CompletenessPart {
  ratio: number;
  present: CompletenessField[];
  missing: CompletenessField[];
  total: number;
}
export interface Completeness {
  algorithm: CompletenessPart;
  record: CompletenessPart;
}
export interface FoodRef {
  food_id: number;
  canonical_name: string | null;
}
export interface RecordView {
  client: {
    id: string;
    full_name: string | null;
    sex: 'M' | 'F' | null;
    age: number | null;
    height_cm: number | null;
    activity_level: number | null;
    goal: string | null;
    restrictions: string[];
    sport: string | null;
    disliked_foods: FoodRef[];
    supplements_owned: FoodRef[];
  };
  record: ClientRecord;
  measurements: BodyMeasurement[];
  latest_weight_kg: number | null;
  body_composition: BodyComposition;
  completeness: Completeness;
  matching?: Record<string, { matched: { text: string; food_id: number; canonical_name: string }[]; unmatched: string[] }>;
}

export function emptyRecord(): ClientRecord {
  return {
    identification: { full_name: null, birth_date: null, phone: null, email: null },
    physiology: { first_visit: null, initial_weight_kg: null, height_cm: null, wrist_cm: null, waist_cm: null, neck_cm: null, hip_cm: null, somatotype: null },
    medical: { allergies: null, intolerances: null, injuries: null, surgeries: null },
    diet: { liked_foods: null, disliked_foods: null, food_vices: null, smokes: null, drinks_alcohol: null },
    sports: {
      training_years: null,
      sports: null,
      achievements: null,
      goals_text: null,
      work_schedule: null,
      training_schedule: null,
      supplements_owned: null,
      first_diet_notes: null,
      watch_brand: null,
    },
  };
}
