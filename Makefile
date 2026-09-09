# finalprosports — named targets (S0). Same targets as the IntelliJ run configurations in .idea/runConfigurations/.
# Every Python target runs from backend/ with the backend virtualenv; the pipeline component has no venv of its own.
# Settings come from .env at this directory (copy .env.example): DATABASE_URL, FPS_DATA_DIR, FPS_DATASET_DIR ...

SHELL := bash
-include .env
export
export PYTHONUTF8 := 1
export PYTHONIOENCODING := utf-8
# Cap the V8 heap of every node process started from here (ng build / ng test / ng serve): a runaway watcher once took 16 GB of RAM.
export NODE_OPTIONS := --max-old-space-size=4096

ifeq ($(OS),Windows_NT)
VPY := .venv/Scripts/python.exe
LINT := .venv/Scripts/lint-imports.exe
else
VPY := .venv/bin/python
LINT := .venv/bin/lint-imports
endif

.PHONY: help up stack stack-reset stack-down stack-logs down keycloak migrate load load-check embed api web web-build web-lint web-test test test-infra test-security golden envelope hooks eval lint audit demo export-seed clear-portfolio verify-delivery verify-clean-clone public-dataset public-synth public-quality public-fixture public-check public-tree

help:            ## list the targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/  —  /'

up:              ## start PostgreSQL 16 + pgvector AND Keycloak 26.7.2 (the realm is imported on startup)
	docker compose up -d db keycloak

stack:           ## THE ONE COMMAND: db + keycloak + bootstrap (migrate, load the corpus, seed the demo) + api + web. App on http://localhost:4200
	docker compose up -d --build

stack-reset:     ## the same, from ZERO: drops the volume so the bootstrap runs again on an empty database. DESTROYS the loaded data
	docker compose down -v && docker compose up -d --build

stack-down:      ## stop the four containers (the pgdata volume is kept)
	docker compose down

stack-logs:      ## follow the logs of the api and the web container
	docker compose logs -f api web

keycloak:        ## start only Keycloak (admin console on http://localhost:8080, admin/admin, local only)
	docker compose up -d keycloak

down:            ## stop the database (the pgdata volume is kept)
	docker compose down

migrate:         ## apply the Alembic migrations (db/schema.sql is executed by 0001)
	cd backend && $(VPY) -m alembic upgrade head

load-check:      ## validate the frozen dataset against db/schema.sql without a database
	cd backend && $(VPY) ../pipeline/src/pipeline/load_postgres.py --dry-run

load:            ## load the corpus (replaces the corpus tables; needs DATABASE_URL)
	cd backend && $(VPY) ../pipeline/src/pipeline/load_postgres.py --apply --replace

embed:           ## vectorise diets.retrieval_text with multilingual-e5-base (pinned revision)
	cd backend && $(VPY) ../pipeline/src/pipeline/embed_corpus.py

api:             ## FastAPI on http://127.0.0.1:8000 (/docs)
	cd backend && $(VPY) -m uvicorn finalprosports.main:app --host 127.0.0.1 --port 8000

web:             ## Angular dev server on http://localhost:4200
	cd frontend && npm start

web-build:       ## compile the frontend (development configuration: API on :8000); serve dist/frontend/browser with any SPA-fallback static server for demos
	cd frontend && npx ng build --configuration development

web-lint:        ## angular-eslint + stylelint + prettier --check
	cd frontend && npm run -s lint

web-test:        ## Karma/Jasmine headless (49 specs). Works under a path with brackets ([Pro]) thanks to the bracket-safe-paths framework in frontend/karma.conf.js
	cd frontend && npm test

test:            ## tests that need neither pytest nor a database (architecture, domain, application, evaluation, pipeline)
	@fail=0; for t in backend/tests/architecture/test_*.py backend/tests/domain/test_*.py backend/tests/application/test_*.py backend/tests/evaluation/test_*.py pipeline/tests/test_*.py; do \
	  out=$$(cd backend && $(VPY) ../$$t 2>&1) || { echo "$$out"; fail=1; }; echo "$$out" | grep -E '^(PASS|FAIL)' | sed "s|^|$$t  |" | grep FAIL && fail=1; done; \
	  echo "PASS: $$(for t in backend/tests/architecture/test_*.py backend/tests/domain/test_*.py backend/tests/application/test_*.py backend/tests/evaluation/test_*.py pipeline/tests/test_*.py; do cd backend && $(VPY) ../$$t 2>&1; cd ..; done | grep -c '^PASS')"; exit $$fail

test-infra:      ## pytest against the running database (contracts + smoke)
	cd backend && $(VPY) -m pytest tests/infrastructure -q

test-security:   ## v2 — the eight token-rejection cases against a REAL Keycloak (needs `make up` and `make api` running). Excluded elsewhere with -m "not security"
	cd backend && $(VPY) -m pytest tests/security -q -m security

golden:          ## S2: 20 model diets — plausibility assertions (envelope mined from the corpus) + snapshots; accept changes with GOLDEN_UPDATE=1
	cd backend && $(VPY) -m pytest tests/golden -q -p no:cacheprovider

envelope:        ## S2: mine the plausibility envelope from the corpus -> $$FPS_DATASET_DIR/plausibility_envelope.json + its report under docs/ (generated)
	cd backend && $(VPY) ../pipeline/src/pipeline/plausibility_envelope.py

hooks:           ## install the pre-commit hook (.githooks: tests + import-linter + golden when the database is reachable)
	git config core.hooksPath .githooks

eval:            ## rerun the LOO harness and regenerate the evaluation output (results.json, RESULTS.md, figures) under docs/ — generated, not versioned
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.eval.report --rerun

notes:           ## rebuild the canonical note catalogue from the versioned themes (pipeline/data/note_themes.json)
	$(VPY) pipeline/src/pipeline/build_canonical_notes.py --apply

rule-rates:      ## per-rule agreement with the professional on the antecedent subset (+ conditional accuracy vs its baseline)
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.eval.rule_rates

predictability:  ## is his per-case rule decision predictable from the profile at all? (the ceiling of conditional accuracy)
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.eval.rule_predictability

discriminate:    ## external discriminator real vs generated (sanity control first) -> DISCRIMINABILITY.md + figure under docs/ (generated)
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.eval.discriminability

lint:            ## import-linter contracts (setup.cfg) + AST architecture tests
	cd backend && $(LINT) && $(VPY) tests/architecture/test_import_contracts.py

audit:           ## PII audit of the code tree and of the data tree: criterion 0
	cd backend && $(VPY) ../pipeline/src/data_tools/audit_tree.py | grep -E '"root"|"total_hits"'

demo:            ## seed the 16 fictitious demo clients (S1/S9), by name, with record + scale + labs + saved diets; --reset removes them first
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.cli.seed_demo --reset

export-seed:     ## copy into seed/dataset the 19 files the application needs (whitelist; refuses _private/). Then run `make audit`
	cd backend && $(VPY) ../pipeline/src/data_tools/export_seed_dataset.py $(if $(APPLY),--apply,)

# ---------------------------------------------------------------------------------------------------------------- #
# EL ÁRBOL PÚBLICO. El repositorio se publica, y el corpus no puede salir: 301 personas, 18.121 parámetros de        #
# laboratorio, art. 9 RGPD. Lo que viaja es el CRITERIO (agregados, 0 personas) más una base de casos GENERADA.      #
# Orden: public-dataset -> public-synth -> public-quality; `public-check` es la puerta y `public-tree` lo monta.      #
# ---------------------------------------------------------------------------------------------------------------- #
public-dataset:  ## exporta a seed/dataset_public los 11 agregados publicables (+ rotation sin per_client). Aborta si ve datos por persona
	cd backend && $(VPY) ../pipeline/src/data_tools/export_public_dataset.py --dataset "$$FPS_DATASET_DIR" --out ../seed/dataset_public --apply

public-params:   ## deriva synthetic_params.json del corpus privado (celda mínima 10). Se ejecuta UNA vez
	cd backend && $(VPY) ../pipeline/src/data_tools/derive_synthetic_params.py --dataset "$$FPS_DATASET_DIR" --out ../seed/dataset_public/synthetic_params.json

public-synth:    ## genera la base de casos sintética (determinista). CLIENTS=300 SEED=20260909
	cd backend && $(VPY) ../pipeline/src/data_tools/synthesize_case_base.py --aggregates ../seed/dataset_public 	  --out ../seed/dataset_public --clients $(or $(CLIENTS),300) --seed $(or $(SEED),20260909)

public-quality:  ## mide si las dietas salen bien con la base sintética y escribe docs/evaluation/SYNTHETIC_QUALITY.md
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.eval.synthetic_quality --sweep $(or $(SWEEP),200) 	  $(if $(BASELINE),--baseline $(BASELINE),) --out ../docs/evaluation/SYNTHETIC_QUALITY.md

public-fixture:  ## regenera el expediente SINTÉTICO del e2e (el real se queda fuera del árbol)
	cd backend && $(VPY) tests/e2e/build_synthetic_fixture.py --out tests/e2e/fixtures/client_recurrent_volume_synthetic.json

public-check:    ## LA PUERTA: ningún dato personal en el árbol. Sin FPS_PUBLIC_TREE=1 comprueba el inventario declarado
	cd backend && $(VPY) ../backend/tests/architecture/test_public_tree_has_no_personal_data.py

public-tree:     ## monta el árbol público en OUT=... (por defecto ../_public_tree) y le pasa la puerta
	./tools/build_public_tree.sh $(or $(OUT),../_public_tree)

clear-portfolio: ## leave the database in DELIVERY state: the portfolio emptied (demo + e2e clients), the case base untouched. Add APPLY=1 to delete for real
	cd backend && $(VPY) -m finalprosports.infrastructure.adapter.inbound.cli.clear_portfolio $(if $(APPLY),--apply,)

verify-delivery: ## the delivery gate: with the delivery database the application shows no client, no reading and no parameter (fails if the portfolio is not empty)
	cd backend && FPS_DELIVERY_CHECK=1 $(VPY) -m pytest tests/infrastructure/test_delivery_shows_no_client.py -q -rs

e2e-real:        ## whole path with a real client's data, pseudonymised: register by name, record, scale, labs, history, propose, evaluate automatically
	cd backend && $(VPY) -m pytest tests/e2e -q -m e2e_real

verify-clean-clone:  ## the truth test before a delivery: clone the COMMITTED tree into an empty folder and run the whole bootstrap there (venv, npm ci, isolated db, migrate, load, embed, suites, API, frontend); see tools/verify_clean_clone.sh
	bash tools/verify_clean_clone.sh
