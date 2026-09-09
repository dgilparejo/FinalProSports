# -*- coding: utf-8 -*-
"""Architecture contracts enforced without external tools (mirrors setup.cfg / import-linter, which CI also runs).

Layers: infrastructure -> application -> domain, never backwards. The domain imports no framework. pydantic only under
infrastructure.adapter.inbound.rest.dto (+ config.settings); sqlalchemy only under infrastructure.adapter.outbound.persistence
(+ config.persistence). Parsed with `ast`: importing nothing, so it runs in milliseconds and without the dependencies installed.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = SRC / "finalprosports"
FRAMEWORKS = {"sqlalchemy", "pydantic", "pydantic_settings", "fastapi", "alembic", "psycopg", "pgvector", "sentence_transformers", "numpy", "torch"}


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
    return out


def modules(layer: str):
    for p in (PKG / layer).rglob("*.py"):
        yield p, imports_of(p)


def top(name: str) -> str:
    return name.split(".")[0]


def test_domain_imports_no_framework_and_no_outer_layer():
    bad = []
    for p, imps in modules("domain"):
        for i in imps:
            if top(i) in FRAMEWORKS or i.startswith("finalprosports.application") or i.startswith("finalprosports.infrastructure"):
                bad.append((p.relative_to(SRC).as_posix(), i))
    assert not bad, bad


def test_application_imports_no_framework_and_no_infrastructure():
    bad = []
    for p, imps in modules("application"):
        for i in imps:
            if top(i) in FRAMEWORKS or i.startswith("finalprosports.infrastructure"):
                bad.append((p.relative_to(SRC).as_posix(), i))
    assert not bad, bad


def test_pydantic_only_in_rest_dto_and_settings():
    allowed = ("finalprosports/infrastructure/adapter/inbound/rest/dto/", "finalprosports/infrastructure/config/settings.py")
    bad = []
    for p in PKG.rglob("*.py"):
        rel = p.relative_to(SRC).as_posix()
        if any(top(i) in ("pydantic", "pydantic_settings") for i in imports_of(p)) and not rel.startswith(allowed):
            bad.append(rel)
    assert not bad, bad


def test_sqlalchemy_only_in_persistence():
    allowed = ("finalprosports/infrastructure/adapter/outbound/persistence/", "finalprosports/infrastructure/config/persistence.py")
    bad = []
    for p in PKG.rglob("*.py"):
        rel = p.relative_to(SRC).as_posix()
        if any(top(i) in ("sqlalchemy", "pgvector") for i in imports_of(p)) and not rel.startswith(allowed):
            bad.append(rel)
    assert not bad, bad


def test_layers_do_not_import_backwards():
    bad = []
    for p, imps in modules("domain"):
        bad += [(p.name, i) for i in imps if i.startswith("finalprosports.application") or i.startswith("finalprosports.infrastructure")]
    for p, imps in modules("application"):
        bad += [(p.name, i) for i in imps if i.startswith("finalprosports.infrastructure")]
    assert not bad, bad


def test_ports_are_protocols_not_abcs():
    bad = []
    for p in (PKG / "application" / "port").rglob("*_port.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(b) for b in node.bases]
                if "Protocol" not in bases:
                    bad.append((p.name, node.name, bases))
    assert not bad, bad


def test_setup_cfg_declares_the_import_linter_contracts():
    """import-linter (CI) and this file must describe the same architecture: the five contracts exist in setup.cfg."""
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(SRC.parent / "setup.cfg", encoding="utf-8")
    expected = {"layers", "domain-is-pure", "application-has-no-framework", "pydantic-only-in-rest-dto", "sqlalchemy-only-in-persistence"}
    found = {s.split(":", 2)[2] for s in cfg.sections() if s.startswith("importlinter:contract:")}
    assert expected <= found, sorted(expected - found)
    assert cfg["importlinter"]["root_package"] == "finalprosports"
    layers = [l.strip() for l in cfg["importlinter:contract:layers"]["layers"].splitlines() if l.strip()]
    assert layers == ["finalprosports.infrastructure", "finalprosports.application", "finalprosports.domain"], layers


def test_schema_sql_splits_into_clean_statements():
    """Migration 0001 executes db/schema.sql statement by statement after stripping comments (inline comments contain ';')."""
    mig = SRC.parent / "db" / "migrations" / "versions" / "0001_initial_schema.py"
    src = "\n".join(l for l in mig.read_text(encoding="utf-8").splitlines() if not l.startswith("from alembic"))
    ns: dict = {"__file__": str(mig)}
    exec(compile(src, str(mig), "exec"), ns)
    stmts = ns["statements"]((SRC.parent / "db" / "schema.sql").read_text(encoding="utf-8"))
    assert len(stmts) == 20, len(stmts)                      # 1 extension + 13 tables + 6 indexes (0016 anadio dos sobre lab_results; 0014, el de corpus_alias)
    assert all("--" not in s for s in stmts), [s for s in stmts if "--" in s][:1]
    assert all(s.upper().startswith(("CREATE EXTENSION", "CREATE TABLE", "CREATE INDEX")) for s in stmts), [s[:40] for s in stmts]
    tables = [s.split()[2] for s in stmts if s.upper().startswith("CREATE TABLE")]
    assert tables == ["professionals", "client_profiles", "foods", "diets", "meals", "diet_items", "rules", "archetypes", "saved_diets", "gaps", "client_records", "body_measurements", "lab_results"], tables
    assert all("professional_id" in s for s in stmts if s.upper().startswith("CREATE TABLE") and s.split()[2] != "professionals")


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS  {name}")
            except AssertionError as e:
                failed += 1; print(f"FAIL  {name}: {str(e)[:400]}")
    sys.exit(1 if failed else 0)
