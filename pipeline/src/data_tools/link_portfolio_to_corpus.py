"""Propone el puente cartera <-> base de casos: que cliente de la cartera es, ademas, un caso del corpus.

POR QUE HACE FALTA. La cartera identifica al cliente por UUID (S9) y el corpus por seudonimo `CLIENTE_NNN`. Un cliente
que ya era caso del profesional antes de existir la aplicacion esta en los dos sitios con dos codigos distintos, y la
exclusion obligatoria de la recuperacion mira `client_code`: no lo cubre. El sistema puede devolverle SU PROPIA dieta
como si fuera el caso de un tercero. Confirmado con un cliente real: sus dos dietas estan en el corpus con J = 1,0000.

POR QUE PROPONE Y NO ENLAZA. En este corpus el contenido NO identifica a una persona. Medido sobre las 1.195 dietas:

    umbral J    pares del MISMO cliente    pares de clientes DISTINTOS
      0,90                115                        73
      0,95                 76                        39
      0,98 .. 1,00         47                        19

Diecinueve pares de dietas IDENTICAS pertenecen a personas distintas, porque el profesional reutiliza dietas
literalmente. Una sola coincidencia, aunque sea perfecta, no prueba nada.

EL CRITERIO, Y SU TASA DE ERROR MEDIDA. Se enlaza cuando **todas** las dietas guardadas del cliente de cartera tienen
gemelo con J >= 0,98 en el corpus **y todas apuntan al mismo seudonimo**, con un minimo de dos dietas. Simulacro sobre
el propio corpus -- cada uno de los 167 clientes con dos o mas dietas hace de cliente de cartera y se busca gemelo
entre los demas --: **0 enlaces falsos de 167**. Con una sola dieta el criterio no se aplica, porque ahi los 19 pares
identicos entre personas distintas lo harian fallar.

Aun asi la ultima palabra es del profesional: `--apply` escribe, sin el solo informa. La comparacion usa food_id y
franja, nunca nombres.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from pipeline_v3 import paths  # noqa: E402

MIN_JACCARD = 0.98
MIN_DIETS = 2


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def corpus_signatures() -> dict[str, set]:
    """(franja, food_id) por dieta del corpus. Sin texto y sin nombres."""
    out: dict[str, set] = collections.defaultdict(set)
    for line in (paths.dataset_dir_v3() / "diet_items.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            x = json.loads(line)
            if x.get("food_id") is not None:
                out[x["diet_id"]].add((x["meal_slot"], x["food_id"]))
    return out


def propose(signature_of_saved: list[set], corpus: dict[str, set]) -> tuple[str | None, list[tuple[float, str, float]]]:
    """Devuelve (seudonimo propuesto o None, detalle por dieta).

    El detalle lleva, por cada dieta guardada: el mejor Jaccard, el seudonimo donde cae, y el mejor Jaccard alcanzado
    por CUALQUIER OTRO cliente. Ese tercer numero es el que deja ver lo justo que va el criterio, y en el caso real va
    justo: 1,0000 contra 0,9091.
    """
    votes, detail = collections.Counter(), []
    for own in signature_of_saved:
        best_j, best_id = max(((jaccard(own, sig), did) for did, sig in corpus.items()), default=(0.0, None))
        best_code = (best_id or "").split("::")[0]
        runner = max((jaccard(own, sig) for did, sig in corpus.items() if did.split("::")[0] != best_code), default=0.0)
        detail.append((best_j, best_code or "?", runner))
        if best_j >= MIN_JACCARD and best_code:
            votes[best_code] += 1
    if len(signature_of_saved) < MIN_DIETS or not votes:
        return None, detail
    code, n = votes.most_common(1)[0]
    return (code if n == len(signature_of_saved) else None), detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="escribe client_profiles.corpus_alias; sin esto solo informa")
    args = ap.parse_args()

    from finalprosports.infrastructure.composition_root import CompositionRoot
    from sqlalchemy import text

    root = CompositionRoot.from_env()
    pid = root.configured_professional_id
    corpus = corpus_signatures()

    with root.client_records._sf() as session:                       # noqa: SLF001
        portfolio = [r[0] for r in session.execute(text(
            "SELECT client_code FROM client_profiles WHERE professional_id = :p AND NOT is_corpus_case ORDER BY client_code"),
            {"p": pid})]

    enlazados, sin_enlace, sin_historial = [], [], []
    for code in portfolio:
        history = tuple(root.history.history(pid, code))
        if not history:
            sin_historial.append(code)
            continue
        firmas = [{(m.slot.value, i.food_id) for m in d.meals for i in m.items if i.food_id is not None} for d in history]
        alias, detail = propose(firmas, corpus)
        marca = code[:8] + "…"
        print(f"{marca}  {len(history)} dieta(s) guardada(s)")
        for j, cli, runner in detail:
            print(f"     mejor gemelo J {j:.4f} en {cli} · mejor de OTRO cliente J {runner:.4f}")
        if alias:
            enlazados.append((code, alias))
            print(f"     -> PROPUESTA de enlace: {alias}")
        else:
            sin_enlace.append(code)
            print("     -> sin enlace (no unánime, por debajo del umbral, o una sola dieta)")

    print(f"\nresumen: {len(portfolio)} clientes de cartera · {len(enlazados)} con seudónimo propuesto · "
          f"{len(sin_enlace)} sin enlace · {len(sin_historial)} sin dietas guardadas (no evaluables)")
    if not args.apply:
        print("(simulación: sin --apply no se escribe nada)")
        return 0
    with root.client_records._sf() as session:                       # noqa: SLF001
        for code, alias in enlazados:
            session.execute(text("UPDATE client_profiles SET corpus_alias = :a WHERE professional_id = :p AND client_code = :c"),
                            {"a": alias, "p": pid, "c": code})
        session.commit()
    print(f"escritos {len(enlazados)} enlaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
