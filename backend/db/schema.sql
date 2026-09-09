-- finalprosports — logical schema (Postgres 16 + pgvector). Source of truth: db/migrations/versions/0001_initial_schema.py
-- Every table carries professional_id and every query filters by it (logical multi-tenant; Keycloak seam).
-- Data values stay in Spanish (meal slots, goals, canonical food names); identifiers are English.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE professionals (
    id                text PRIMARY KEY,             -- tenant key, internal ('prof_001'); never typed by anyone
    display_name      text NOT NULL,
    keycloak_subject  text UNIQUE,                  -- v2 (0011): OIDC `sub` that owns this professional; a subject mapping to nothing gets 403
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE client_profiles (
    client_code                 text NOT NULL,      -- INTERNAL KEY, never shown: CLIENTE_NNN (pseudonym of dataset-v1) for a corpus case; a UUID assigned by the application for a portfolio client (S9, 0010)
    professional_id             text NOT NULL REFERENCES professionals(id),
    sex                         char(1) CHECK (sex IN ('M','F')),
    age                         smallint,           -- plausibility is a FLAG (suspicious_demographics), not a constraint: dataset-v1 is frozen
    age_bucket                  text,
    height_cm                   smallint,
    activity_level              smallint,
    activity_level_reported     boolean NOT NULL,
    is_athlete                  boolean,
    body_type                   text,               -- complexión por muñeca (0013): rasgo de similitud
    training_time               text,               -- franja horaria de entrenamiento (0013)
    goals                       text,
    sport                       text,
    liked_foods                 text,
    disliked_foods              text,
    has_allergies               boolean NOT NULL,
    has_intolerances            boolean NOT NULL,
    has_medical_restrictions    boolean NOT NULL,
    diet_count                  smallint NOT NULL,
    diet_count_raw              smallint NOT NULL,
    diet_count_stored           smallint NOT NULL,
    empty_profile               boolean NOT NULL,
    unmapped                    boolean NOT NULL,
    suspicious_demographics     boolean NOT NULL,
    field_carryover_suspected   boolean NOT NULL,
    carryover_fields            text[] NOT NULL DEFAULT '{}',
    redacted_public_fields      text[] NOT NULL DEFAULT '{}',
    restrictions                text[] NOT NULL DEFAULT '{}',   -- structured restrictions (RestrictionKind values) declared in the registration form (E6)
    disliked_food_ids           integer[] NOT NULL DEFAULT '{}',   -- S3: «gustos negativos» resolved against the catalogue (soft exclusions in the validator)
    liked_food_ids     integer[],                 -- 0017: gustos POSITIVOS resueltos; desempatan en la composicion, nunca introducen un alimento
    owned_supplement_ids        integer[] NOT NULL DEFAULT '{}',   -- S3: supplements the client already owns (shown, never vetoed)
    is_corpus_case              boolean NOT NULL DEFAULT false, -- S1: true = pseudonymous profile of the CASE BASE (corpus, retrieval only); false = client of the professional's portfolio (the application)
    corpus_alias                text,               -- 0014: el puente cartera -> base de casos. Un cliente de cartera que YA era caso del corpus lleva aqui su CLIENTE_NNN, para que la exclusion obligatoria de la recuperacion no le devuelva su propia dieta como caso de un tercero
    PRIMARY KEY (professional_id, client_code),
    CONSTRAINT portfolio_key_is_uuid CHECK (is_corpus_case OR client_code ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),   -- S9: the identity of a portfolio client is his NAME (client_records); the key is the machine's
    CONSTRAINT ck_client_profiles_alias_only_for_portfolio CHECK (corpus_alias IS NULL OR NOT is_corpus_case)   -- 0014: un caso del corpus nunca tiene alias, es el propio corpus
);
CREATE INDEX ix_client_profiles_corpus_alias ON client_profiles (professional_id, corpus_alias);

CREATE TABLE foods (
    id                   integer NOT NULL,
    professional_id      text NOT NULL REFERENCES professionals(id),
    canonical_name       text NOT NULL,
    family               text NOT NULL,
    food_group           text NOT NULL,             -- FoodGroup
    secondary_group      text,
    frequency            integer NOT NULL,
    attribute_source     text NOT NULL,
    synonyms             text[] NOT NULL DEFAULT '{}',
    keys                 text[] NOT NULL DEFAULT '{}',   -- normalised keys resolving to this food
    created_by_professional boolean NOT NULL DEFAULT false,   -- S5: registered through the application (POST /catalog/foods), not mined from the corpus
    is_processed_sugar   boolean NOT NULL, is_soft_drink boolean NOT NULL, is_salt boolean NOT NULL,
    is_fasting_compatible boolean NOT NULL, is_alcohol boolean NOT NULL, is_stimulant boolean NOT NULL,
    is_peanut boolean NOT NULL, is_tree_nut boolean NOT NULL,
    contains_lactose boolean NOT NULL, contains_gluten boolean NOT NULL, contains_soy boolean NOT NULL,
    contains_shellfish boolean NOT NULL, contains_egg boolean NOT NULL, contains_fish boolean NOT NULL,
    PRIMARY KEY (professional_id, id),
    UNIQUE (professional_id, canonical_name)
);

CREATE TABLE diets (
    id                  text NOT NULL,             -- CLIENTE_NNN::vNN
    professional_id     text NOT NULL REFERENCES professionals(id),
    client_code         text NOT NULL,
    goal                text NOT NULL,
    goals               text[] NOT NULL DEFAULT '{}',
    goal_inferred       boolean NOT NULL,
    goal_text           text,
    method              text,                      -- structural regime declared with the goal (0012); null = none
    doc_date            date,                      -- 0015: date of the source document; the ONLY thing that makes a longitudinal signal usable without temporal leakage
    methods             text[] NOT NULL DEFAULT '{}',
    diet_version        smallint,
    template_group_id   text,
    shared_diet         boolean NOT NULL,
    shared_diet_signals text[] NOT NULL DEFAULT '{}',
    template_clients    text[] NOT NULL DEFAULT '{}',
    has_intolerances    boolean NOT NULL,
    notes               text[] NOT NULL DEFAULT '{}',
    text                text NOT NULL,             -- canonical diet text (dataset-v1)
    retrieval_text      text,                      -- E3.1: header + canonical foods per slot + informative notes; THIS is what gets embedded
    embedding           vector(768),               -- intfloat/multilingual-e5-base over retrieval_text; no HNSW index on purpose (~1k rows)
    PRIMARY KEY (professional_id, id),
    FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
);

CREATE TABLE meals (
    id               bigserial PRIMARY KEY,
    professional_id  text NOT NULL,
    diet_id          text NOT NULL,
    meal_slot        text NOT NULL,                -- DESAYUNO, MEDIA MAÑANA, ... OTHER
    position         smallint NOT NULL,
    text             text NOT NULL,                -- meal text as written (chunk used by the legacy index)
    item_count       smallint NOT NULL,
    UNIQUE (professional_id, diet_id, meal_slot),
    FOREIGN KEY (professional_id, diet_id) REFERENCES diets(professional_id, id) ON DELETE CASCADE
);

CREATE TABLE diet_items (
    id                 bigserial PRIMARY KEY,
    professional_id    text NOT NULL,
    diet_id            text NOT NULL,
    meal_slot          text NOT NULL,
    position           smallint NOT NULL,
    component_index    smallint NOT NULL,
    food_id            integer,                     -- NULL when unmapped
    normalized_key     text NOT NULL,
    raw_text           text NOT NULL,
    food_text          text NOT NULL,
    quantity           numeric(10,2),
    unit               text NOT NULL,               -- Unit literal ('g', 'ml', 'unidad', ...)
    raw_unit           text,
    alternative_group  text,
    compound_item      boolean NOT NULL,
    compound_group     text,
    unmapped           boolean NOT NULL,
    unmapped_reason    text,
    generic_assumption boolean NOT NULL,
    note               text,
    FOREIGN KEY (professional_id, diet_id) REFERENCES diets(professional_id, id) ON DELETE CASCADE,
    FOREIGN KEY (professional_id, food_id) REFERENCES foods(professional_id, id)
);
CREATE INDEX diet_items_diet_idx ON diet_items (professional_id, diet_id, meal_slot);
CREATE INDEX diet_items_food_idx ON diet_items (professional_id, food_id);

CREATE TABLE rules (
    id               text NOT NULL,
    professional_id  text NOT NULL REFERENCES professionals(id),
    section          text NOT NULL,
    kind             text NOT NULL,               -- global | goal | sex | phase | placement | avoid_placement | behaviour | policy
    statement        text NOT NULL,
    condition        text[] NOT NULL DEFAULT '{}',
    n_group          integer, n_support integer,
    prevalence_in_group numeric(6,4), prevalence_global numeric(6,4),
    lift             numeric(8,2), adjusted numeric(8,2), adjusted_method text,
    criteria         text NOT NULL,
    detail           jsonb NOT NULL DEFAULT '{}',       -- n_match, by_group, per_food, evaluability attributes
    confidence       text,                        -- high | medium | low
    status           text NOT NULL,               -- kept | retired | descriptive | policy
    evaluation_level text NOT NULL,               -- item | note
    enabled          boolean NOT NULL DEFAULT true,   -- low-confidence rules disabled by default, switchable
    nature           text,                         -- prescriptive | descriptive (Fase 9 B: demandable of every proposal only if followed in the majority of its group)
    PRIMARY KEY (professional_id, id)
);

CREATE TABLE archetypes (
    id               bigserial PRIMARY KEY,
    professional_id  text NOT NULL REFERENCES professionals(id),
    sex              text, age_bucket text, goal text NOT NULL,
    diet_count       integer NOT NULL, client_count integer NOT NULL,
    client_codes     text[] NOT NULL DEFAULT '{}',    -- pseudonyms CLIENTE_NNN
    UNIQUE (professional_id, sex, age_bucket, goal)
);

CREATE TABLE saved_diets (                         -- proposals accepted/edited by the professional (E6): full proposal with evidence + validation
    id               text NOT NULL,                 -- <client_code>::eNN
    professional_id  text NOT NULL REFERENCES professionals(id),
    client_code      text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    goal             text NOT NULL,
    strategy         text NOT NULL,                 -- case_based_composer | rotation_composer
    edited           boolean NOT NULL DEFAULT false,
    payload          jsonb NOT NULL,
    original_payload jsonb,                          -- S5: the proposal exactly as the engine returned it
    diff             jsonb,                          -- S5: what the professional changed (proposal_diff_policy): added / removed / re-quantified / moved, notes, edit_ratio
    PRIMARY KEY (professional_id, id),
    FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
);

CREATE TABLE gaps (                                -- unmet demand: profiles with no similar case, unmapped foods requested
    id               bigserial PRIMARY KEY,
    professional_id  text NOT NULL REFERENCES professionals(id),
    created_at       timestamptz NOT NULL DEFAULT now(),
    kind             text NOT NULL,               -- no_similar_cases | unsatisfiable_restriction | unmapped_food
    payload          jsonb NOT NULL
);

CREATE TABLE client_records (                      -- S3: the professional's intake questionnaire, one row per PORTFOLIO client (five blocks of the sheet)
    client_code        text NOT NULL,
    professional_id    text NOT NULL REFERENCES professionals(id),
    full_name          text, birth_date date, phone text, email text,                                   -- identification: THE identity of a portfolio client (S9); written at registration; fictitious in demos; never the corpus
    first_visit        date, initial_weight_kg numeric(5,1), height_cm smallint, wrist_cm numeric(4,1), waist_cm numeric(5,1), neck_cm numeric(4,1), hip_cm numeric(5,1),
    somatotype         text,                       -- ectomorfo | mesomorfo | endomorfo
    allergies          text, intolerances text, injuries text, surgeries text,                           -- medical block: record only; the engine uses client_profiles.restrictions
    liked_foods        text, disliked_foods text, food_vices text, smokes boolean, drinks_alcohol boolean,
    training_years     numeric(4,1), sports text, achievements text, goals_text text, work_schedule text, training_schedule text,
    supplements_owned  text, first_diet_notes text, watch_brand text,                                    -- watch: brand only, no credentials by design
    updated_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (professional_id, client_code),
    FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
);

CREATE TABLE body_measurements (                   -- S3: connected-scale import (db_*/history structure) or manual readings
    id               bigserial PRIMARY KEY,
    professional_id  text NOT NULL REFERENCES professionals(id),
    client_code      text NOT NULL,
    measured_at      timestamptz NOT NULL,
    weight_kg        numeric(5,1), height_cm smallint, body_fat_pct numeric(4,1), muscle_pct numeric(4,1), water_pct numeric(4,1), bone_kg numeric(4,1),
    -- 0015: the four magnitudes the scale export carries beyond the S3 sheet, plus muscle in KILOS (the export gives kg,
    -- `muscle_pct` is a percentage and could not receive it without inventing a conversion).
    muscle_mass_kg   numeric(5,1), physique_rating smallint, visceral_fat_rating numeric(4,1), metabolic_age smallint, basal_met_kcal integer,
    source           text NOT NULL,                -- scale | manual
    UNIQUE (professional_id, client_code, measured_at, source),
    FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
);

CREATE TABLE lab_results (                         -- S4 + 0016: analytical measurements. The corpus ones DO feed retrieval (see 0016); they never reach the client's document
    id               bigserial PRIMARY KEY,
    professional_id  text NOT NULL REFERENCES professionals(id),
    client_code      text NOT NULL,
    measured_at      date,
    marker           text NOT NULL,                -- as written in the report
    value            numeric(12,3) NOT NULL,
    unit             text,
    ref_low          numeric(12,3), ref_high numeric(12,3),   -- reference range; status (low / high / in range) is derived, not stored
    note             text,
    source           text NOT NULL,                -- manual | file
    -- 0016: de que FORMATO sale cada valor. Obligatorio para que nadie compare un indice de dispositivo con una
    -- magnitud de laboratorio: bioanalyzer | clinical | nutrigenetic | sports_physiology | manual.
    source_type      text NOT NULL DEFAULT 'manual',
    report_sha1      text,                         -- procedencia: el informe del que salio
    values_unreliable boolean NOT NULL DEFAULT false,  -- el PDF extrae sus columnas desordenadas; se guarda y no se usa
    FOREIGN KEY (professional_id, client_code) REFERENCES client_profiles(professional_id, client_code)
);
CREATE INDEX lab_results_source_idx ON lab_results (professional_id, source_type);
CREATE INDEX lab_results_asof_idx ON lab_results (professional_id, client_code, measured_at);
CREATE INDEX lab_results_client_idx ON lab_results (professional_id, client_code, measured_at);
