export interface Food {
  id: number;
  canonical_name: string;
  family: string | null;
  group: string;
  secondary_group: string | null;
  flags: Record<string, boolean>;
  created_by_professional: boolean;
  synonyms: string[];
}

export interface NewFood {
  canonical_name: string;
  family: string;
  group: string;
  secondary_group: string | null;
  flags: Record<string, boolean>;
  synonyms: string[];
}
