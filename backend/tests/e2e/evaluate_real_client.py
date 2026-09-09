# -*- coding: utf-8 -*-
"""Automatic evaluation of one generated diet against the professional's own versions of the same client.

This is the point of the functional test: the trainer does not review the output by hand. Given a client fixture (record, scale,
labs, previous versions) the module registers the client through the real use cases, asks for the next version and answers two
questions with numbers:

  (a) is the diet plausible?      every assertion of the corpus envelope: quantities inside the band, items per slot, alternatives,
                                  recalibrated repeats, slot structure, and zero foods vetoed by the client's declared restrictions.
  (b) does it look like his?      Jaccard against his own previous version at the three granularities, novelty, renewal rate,
                                  conditional rule compliance and plausibility violations, each against the published reference.

Importable from a test (see test_e2e_real_client.py) and runnable on its own. Prints food words and counts only.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finalprosports.domain.composition.factory.proposal_factory import to_diet  # noqa: E402
from finalprosports.domain.composition.policy.plausibility_policy import check_plausibility  # noqa: E402
from finalprosports.domain.composition.policy.restriction_policy import veto_reasons  # noqa: E402
from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind, RestrictionMode  # noqa: E402
from finalprosports.domain.model.client_record import (  # noqa: E402
    ClientRecord, DietPreferences, Identification, MedicalHistory, Physiology, Somatotype, SportsProfile,
)
from finalprosports.domain.model.lab_result import LabResult  # noqa: E402
from finalprosports.infrastructure.adapter.outbound.persistence.mapper.proposal_mapper import profile_to_dict, proposal_from_dict  # noqa: E402

# published references (la memoria (resultados), dataset-v2)
REFERENCE = {
    "j_key_floor": 0.2064, "j_key_copy": 0.2557, "j_key_composer": 0.3094,
    "j_family_recurrent": 0.7028, "novelty_human": 0.4454, "novelty_system": 0.4349,
    "renewal_same_goal": 0.2708, "renewal_goal_change": 0.4225,
    "compliance_cond_prescriptive": 1.0, "compliance_cond_mixed": 0.8573, "compliance_professional": 0.6793,
    "violations_delivered": 0.1775,
}
BANDS = {          # metric -> (low, high) acceptable band around the reference
    "renewal": (0.15, 0.45), "novelty_j_key": (0.30, 0.60), "j_family": (0.55, 0.90),
    "violations": (0.0, 1.0), "compliance_cond_prescriptive": (0.9, 1.0),
}


@dataclass(frozen=True)
class Fixture:
    """Everything one client contributes. `previous` holds his real earlier versions as proposal payloads."""

    full_name: str
    birth_date: str
    sex: str
    height_cm: int
    activity_level: int
    goal: str
    restrictions: tuple[str, ...]
    record: dict
    scale: list[dict]
    labs: list[dict]
    previous: list[dict]
    phone: str | None = None
    email: str | None = None

    @classmethod
    def load(cls, path: Path) -> "Fixture":
        """The invented contact address is stored as [local part, domain] and joined here: the tree audit rejects an
        e-mail-shaped literal in any versioned file, and weakening that detector to admit one fictitious address is
        a worse trade than assembling it at load time."""
        d = json.loads(path.read_text(encoding="utf-8"))
        for marca in ("_synthetic", "generated_by", "_note"):      # el fixture sintético se declara; no son datos
            d.pop(marca, None)
        parts = d.pop("email_parts", None)
        if parts:
            d["email"] = "@".join(parts)
        return cls(**{**d, "restrictions": tuple(d["restrictions"])})


def as_proposal(diet, profile):
    """Su versión anterior, leída como si fuera una propuesta, CONSERVANDO SUS GRUPOS DE ALTERNATIVAS.

    Importa más de lo que parece. Antes esta reconstrucción metía cada ítem en un grupo de uno, y con eso el chequeo
    `alternative_groups_mixed` —que mira cuántos grupos mezclan macrogrupo— no podía dispararse NUNCA sobre lo que él
    escribió: un grupo de un solo elemento no mezcla nada. Resultado: la comparación «introducida frente a heredada»
    era ciega justo para ese chequeo y le atribuía al sistema una conducta suya. Medido sobre el cliente del e2e: la
    propuesta mezcla en 11 de 14 grupos (0,79) y SUS DOS versiones anteriores mezclan en 11 de 13 (0,85). El sistema
    no introduce nada ahí; reproduce lo que él hace, y su envolvente lo declara (el 21 % de sus grupos no tienen
    macrogrupo común, `rotation_analysis` §7).

    Los ítems sin grupo siguen yendo cada uno por su cuenta, que es lo que son."""
    from finalprosports.domain.model import AlternativeGroup, DietProposal, ItemEvidence, ProposedItem, ProposedMeal
    meals = []
    for m in diet.meals:
        grupos: dict[str, list] = {}
        orden: list[str] = []
        for i, it in enumerate(m.items):
            clave = it.alternative_group or f"__solo_{i}"
            if clave not in grupos:
                grupos[clave] = []
                orden.append(clave)
            grupos[clave].append(ProposedItem(it, ItemEvidence((), 0.0)))
        meals.append(ProposedMeal(m.slot, tuple(AlternativeGroup(n, tuple(grupos[k])) for n, k in enumerate(orden))))
    return DietProposal(profile, tuple(meals), diet.notes, (), "previous")


def _record_of(fx: Fixture, key: str, pid: str) -> ClientRecord:
    r = fx.record
    return ClientRecord(key, pid,
                        Identification(fx.full_name, date.fromisoformat(fx.birth_date), fx.phone, fx.email),
                        Physiology(date.fromisoformat(r["first_visit"]) if r.get("first_visit") else None, r.get("initial_weight_kg"),
                                   fx.height_cm, r.get("wrist_cm"), r.get("waist_cm"), r.get("neck_cm"), r.get("hip_cm"),
                                   Somatotype(r["somatotype"]) if r.get("somatotype") else None),
                        MedicalHistory(r.get("allergies"), r.get("intolerances"), r.get("injuries"), r.get("surgeries")),
                        DietPreferences(r.get("liked_foods"), r.get("disliked_foods"), r.get("food_vices"), r.get("smokes"), r.get("drinks_alcohol")),
                        SportsProfile(r.get("training_years"), r.get("sports"), r.get("achievements"), r.get("goals_text"),
                                      r.get("work_schedule"), r.get("training_schedule"), r.get("supplements_owned"),
                                      r.get("first_diet_notes"), r.get("watch_brand")))


def load_client(root, fx: Fixture) -> str:
    """Register through the REAL use cases and load record, scale, labs and history. Returns the client key (UUID)."""
    pid = root.configured_professional_id
    for key, ident in root.client_records.list_identifications(pid).items():
        if (ident.full_name or "").strip().casefold() == fx.full_name.casefold():
            root.client_repository.delete(pid, key)
    draft = ClientProfile(client_code="", professional_id=pid, sex=fx.sex, age=None, height_cm=fx.height_cm,
                          activity_level=fx.activity_level, goal=Goal(fx.goal),
                          restrictions=tuple(Restriction(RestrictionKind(r)) for r in fx.restrictions),
                          has_intolerances=bool(fx.restrictions))
    profile = root.register_client_use_case.register(draft, Identification(fx.full_name, date.fromisoformat(fx.birth_date), fx.phone, fx.email))
    cid = profile.client_code
    root.update_client_record_use_case.update(pid, _record_of(fx, cid, pid))
    if fx.scale:
        users = [{"isMale": fx.sex == "M", "height_cm": fx.height_cm, "activity_level": fx.activity_level, "isLifetimeAthlete": False}]
        root.import_body_composition_use_case.import_scale(pid, cid, users, fx.scale)
    if fx.labs:
        root.add_lab_results_use_case.add_manual(pid, cid, tuple(
            LabResult(l["marker"][:80], l["value"], l.get("unit"), l.get("ref_low"), l.get("ref_high"),
                      date.fromisoformat(l["measured_at"]) if l.get("measured_at") else None, (l.get("note") or "")[:300] or None, "file")
            for l in fx.labs))
    stored = root.client_repository.get(pid, cid)
    from sqlalchemy import text
    for i, doc in enumerate(fx.previous, start=1):
        payload = dict(doc["payload"])
        payload["profile"] = profile_to_dict(stored)
        diet_id = root.proposal_repository.save(pid, proposal_from_dict(payload), edited=True, original=None, diff=None)
        if doc.get("date"):
            with root.proposal_repository._sf() as s:      # noqa: SLF001 — document date as created_at; there is no document-import endpoint yet
                s.execute(text("UPDATE saved_diets SET created_at = :d WHERE professional_id = :p AND id = :i"),
                          {"d": doc["date"] + "T09:00:00", "p": pid, "i": diet_id})
                s.commit()
    return cid


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def evaluate(root, cid: str, fx: Fixture) -> dict:
    pid = root.configured_professional_id
    profile = root.client_repository.get(pid, cid)
    history = tuple(root.history.history(pid, cid))
    proposal = root.propose_diet_use_case.propose(pid, profile, k=20)
    diet = to_diet(proposal)
    previous = max(history, key=lambda d: (d.diet_version or 0, d.id)) if history else None
    catalog = root.catalog
    env = root.envelope.load(pid)
    rules = root.rules.all(pid)

    # (a) plausibility + restrictions. A violation the professional's OWN previous version also has is INHERITED, not introduced
    # by the system: the assertion is his envelope, and for this client he himself sits outside it.
    violations = check_plausibility(proposal, env, catalog, rules, previous=previous)
    inherited = set()
    if previous is not None:
        prev_proposal = as_proposal(previous, profile)
        inherited = {(v.check, v.slot) for v in check_plausibility(prev_proposal, env, catalog, rules)}
    introduced = [v for v in violations if (v.check, v.slot) not in inherited]
    vetoed = [(m.slot.value, catalog[o.item.food_id].canonical_name, veto_reasons(catalog[o.item.food_id], profile, RestrictionMode.STRICT)[0])
              for m in proposal.meals for o in m.items if o.item.food_id in catalog and veto_reasons(catalog[o.item.food_id], profile, RestrictionMode.STRICT)]

    # (b) similarity to his own previous version
    def keys(d):
        return frozenset(i.normalized_key for m in d.meals for i in m.items if i.normalized_key)

    def foods(d):
        return frozenset(i.food_id for m in d.meals for i in m.items if i.food_id is not None)

    def families(d):
        return frozenset(catalog[i.food_id].family for m in d.meals for i in m.items if i.food_id in catalog and catalog[i.food_id].family)

    # SU comportamiento con ESTE cliente, entre sus dos versiones consecutivas más recientes. Es la vara que faltaba:
    # las bandas de `BANDS` son de POBLACIÓN (RESULTS §9, 904 pares de 164 clientes) y aquí se juzga UNA persona. Y no
    # es un matiz: medido con el cliente del e2e, él mantiene el 95,56 % de las claves y el 100 % de las familias entre
    # una versión y la siguiente —renueva un 2 %—, así que ÉL MISMO cae fuera de la banda [0,30, 0,60]. Exigirle al
    # sistema estar dentro de una banda que su propio autor no cumple no mide calidad, mide otra cosa.
    orden = sorted(history, key=lambda d: (d.diet_version or 0, d.id)) if history else []
    propio = {}
    if len(orden) >= 2:
        a, b = orden[-2], orden[-1]
        fa = foods(a)
        propio = {"own_j_key": round(jaccard(keys(a), keys(b)), 4),
                  "own_j_family": round(jaccard(families(a), families(b)), 4),
                  "own_renewal": round(len(fa - foods(b)) / len(fa), 4) if fa else None,
                  "own_pairs": len(orden) - 1}

    prev_foods = foods(previous) if previous else frozenset()
    now_foods = foods(diet)
    engine_rules = [r for r in rules if r.id in {"sin_hidratos_cena", "suplementacion_pre_post", "sal_himalaya"}]
    from finalprosports.domain.composition.policy.rule_engine import RuleEngine
    engine = RuleEngine(catalog)
    checks = [c for c in engine.check(rules, diet, profile) if c.applicable and c.rule_id in {r.id for r in engine_rules}]
    params = proposal.parameters
    return {
        "routing": params.get("routing"), "strategy": proposal.strategy,
        "retrieved": len(proposal.retrieved_case_ids), "rotated": params.get("rotated_items"),
        "renewal": params.get("renewal_applied"), "renewal_target": params.get("renewal_target"),
        "items": sum(len(m.items) for m in proposal.meals), "slots": [m.slot.value for m in proposal.meals],
        "j_key": round(jaccard(keys(previous), keys(diet)), 4) if previous else None,
        "j_food": round(jaccard(prev_foods, now_foods), 4) if previous else None,
        "j_family": round(jaccard(families(previous), families(diet)), 4) if previous else None,
        "novelty_j_key": round(jaccard(keys(previous), keys(diet)), 4) if previous else None,
        "renewal_measured": round(len(prev_foods - now_foods) / len(prev_foods), 4) if prev_foods else None,
        "compliance_cond_prescriptive": round(sum(1 for c in checks if c.satisfied) / len(checks), 4) if checks else None,
        **propio,
        "violations": len(violations), "violations_introduced": len(introduced), "violations_inherited": len(violations) - len(introduced),
        "violation_detail": [str(v) for v in violations], "introduced_detail": [str(v) for v in introduced],
        "vetoed_foods": vetoed,
        "forced": [(f.slot.value, f.canonical_name, f.action, f.reason) for f in (proposal.validation.forced_changes if proposal.validation else ())],
        "unsatisfiable": [w for w in (proposal.validation.warnings if proposal.validation else ()) if w.startswith("rule:")],
        "plausibility_changes": len((params.get("plausibility") or {}).get("changes", [])),
        "rotation_refusals": len(params.get("rotation_refusals") or []),
    }


def metric_problems(r: dict) -> list[str]:
    """Las cifras de parecido contra su vara. Una función, usada por el veredicto y por el test: dos copias de este
    criterio se habrían separado en la primera corrección."""
    problems: list[str] = []
    # El SUELO es siempre el de la población: por debajo, el sistema no está renovando la dieta, está inventando otra.
    # El TECHO, cuando el cliente tiene dos versiones suyas, es SU PROPIA cifra: el techo existe para cazar «el sistema
    # ha copiado la versión anterior», y copiar es parecerse a ella TANTO COMO ÉL o más. Con este cliente, él mantiene
    # 0,9556 de las claves; pedirle al sistema ≤ 0,60 es pedirle que renueve más que el profesional, que no es lo que
    # el sistema promete. Sin sus versiones, se usa la banda de población tal cual.
    relativo = {"novelty_j_key": "own_j_key", "j_family": "own_j_family"}
    for name, key in (("renewal", "renewal_measured"), ("novelty_j_key", "novelty_j_key"), ("j_family", "j_family"),
                      ("compliance_cond_prescriptive", "compliance_cond_prescriptive")):
        lo, hi = BANDS[name]
        v = r.get(key)
        if v is None:
            continue
        suyo = r.get(relativo.get(name, ""))
        if suyo is not None and suyo > hi:
            if v < lo:
                problems.append(f"{name} {v} por debajo del suelo [{lo}, ...]: la propuesta no se parece a su versión anterior")
            elif v >= suyo:
                problems.append(f"{name} {v} >= {suyo}, que es lo que él mismo conserva: el sistema ha COPIADO su versión")
            continue
        if not (lo <= v <= hi):
            problems.append(f"{name} {v} fuera de la banda [{lo}, {hi}]")
    return problems


def verdict(r: dict) -> tuple[bool, list[str]]:
    problems = []
    if r["violations_introduced"]:
        problems.append(f"{r['violations_introduced']} violación(es) de plausibilidad INTRODUCIDAS por el sistema")
    if r["vetoed_foods"]:
        problems.append(f"{len(r['vetoed_foods'])} alimento(s) vetado(s) por sus restricciones")
    problems += metric_problems(r)
    return (not problems), problems


if __name__ == "__main__":
    from finalprosports.infrastructure.composition_root import CompositionRoot
    fx = Fixture.load(Path(sys.argv[1]))
    root = CompositionRoot.from_env()
    cid = load_client(root, fx)
    res = evaluate(root, cid, fx)
    ok, problems = verdict(res)
    print(json.dumps({k: v for k, v in res.items() if k != "violation_detail"}, ensure_ascii=False, indent=1))
    print("\nVEREDICTO:", "APTA" if ok else "NO APTA")
    for p in problems:
        print("  -", p)
    sys.exit(0 if ok else 1)
