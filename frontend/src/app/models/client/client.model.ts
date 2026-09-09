// A client of the professional's PORTFOLIO (S1, corrected in S9): identified by NAME everywhere a person reads, keyed by an internal
// UUID (`id`) everywhere the machine does. The case base of the corpus (CLIENTE_NNN) is never a Client here.

export interface Client {
  id: string;
  full_name: string | null;
  birth_date: string | null;
  phone: string | null;
  email: string | null;
  sex: 'M' | 'F' | null;
  age: number | null;
  age_bucket: string;
  height_cm: number | null;
  activity_level: number | null;
  goal: string | null;
  is_athlete: boolean | null;
  has_allergies: boolean;
  has_intolerances: boolean;
  has_medical_restrictions: boolean;
  restrictions: string[];
  diet_count?: number;
}

/** The registration form: identification as the professional's sheet asks + what the engine needs. Nobody types a code. */
export interface RegisterClient {
  full_name: string;
  birth_date: string | null;
  phone: string | null;
  email: string | null;
  sex: 'M' | 'F' | null;
  height_cm: number | null;
  activity_level: number | null;
  goal: string | null;
  restrictions: string[];
}

/** The reference a proposal or a saved diet carries: key + name (never inside the engine's profile). */
export interface ClientRef {
  id: string;
  full_name: string | null;
}
