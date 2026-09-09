# -*- coding: utf-8 -*-
"""
E2.5 — Vectorise the corpus: diets.text -> diets.embedding (vector(768)) with intfloat/multilingual-e5-base, in process.

Reads the diets of one professional whose embedding is NULL (or all of them with --all), embeds them through the
same adapter the application uses (E5EmbedderAdapter: "passage: " prefix, L2-normalised, so pgvector's cosine
distance <=> equals 1 - dot product) and writes the vectors back. Requires DATABASE_URL and the model in the local
Hugging Face cache (downloading it is network traffic without data: only with the owner's explicit OK).

No HNSW / IVFFlat index is created, on purpose: with ~1.000 rows a sequential scan costs ~8 ms (measured, EXPLAIN ANALYZE), and the
attribute prefilters (professional_id, goal, excluded ids of the leave-one-out) would degrade the recall of an
approximate index. See CaseRepositoryOutputAdapter.

Note on length: e5-base truncates at 512 tokens; the canonical diet text has a median of ~1.400 characters and a
maximum of ~5.500, so the longest diets are embedded from their first ~2.000 characters (header + first meals).
The count of truncated texts is reported so the effect can be discussed in the evaluation.

Nothing is printed but counts and timings.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import DATASET_DIR  # noqa: E402,F401  (adds backend/src to sys.path)

EXPECTED_DIMENSION = 768


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--professional-id", default=os.environ.get("PROFESSIONAL_ID", "prof_001"))
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"), help="psycopg URL; the SQLAlchemy driver suffix (+psycopg) is accepted and stripped")
    ap.add_argument("--model", default=os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-base"))
    ap.add_argument("--revision", default=os.environ.get("EMBEDDING_MODEL_REVISION", "d128750597153bb5987e10b1c3493a34e5a4502a"), help="Hugging Face commit hash")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--source-column", default="retrieval_text", choices=("retrieval_text", "text"), help="what gets embedded (E3.1: retrieval_text)")
    ap.add_argument("--all", action="store_true", help="re-embed every diet, not only those with a NULL embedding")
    ap.add_argument("--dry-run", action="store_true", help="count the diets to embed; load neither the model nor write anything")
    args = ap.parse_args()
    if args.database_url:
        args.database_url = args.database_url.replace("postgresql+psycopg://", "postgresql://")
    if not args.database_url:
        raise SystemExit("--database-url or DATABASE_URL is required")

    import psycopg                                   # lazy: keeps `--help` dependency-free
    where = "professional_id = %s" + ("" if args.all else " AND embedding IS NULL")
    with psycopg.connect(args.database_url) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT id, {args.source_column} FROM diets WHERE {where} AND {args.source_column} IS NOT NULL ORDER BY id", (args.professional_id,))
        rows = cur.fetchall()
        print(json.dumps({"professional_id": args.professional_id, "model": args.model, "revision": args.revision, "source_column": args.source_column, "to_embed": len(rows), "dry_run": args.dry_run}))
        if args.dry_run or not rows:
            return 0

        from finalprosports.infrastructure.adapter.outbound.embeddings.e5_embedder_adapter import E5EmbedderAdapter
        t0 = time.perf_counter()
        embedder = E5EmbedderAdapter(args.model, batch_size=args.batch_size, revision=args.revision)
        if embedder.dimension() != EXPECTED_DIMENSION:
            raise SystemExit(f"model dimension {embedder.dimension()} != vector({EXPECTED_DIMENSION}) column")
        load_s = time.perf_counter() - t0
        tokenizer = embedder._model.tokenizer                                     # noqa: SLF001 (diagnostic only)
        max_len = int(embedder._model.max_seq_length)
        truncated = sum(len(tokenizer(t, add_special_tokens=True)["input_ids"]) > max_len for _, t in rows)

        t1 = time.perf_counter()
        done = 0
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start:start + args.batch_size]
            vectors = embedder.embed_documents([t for _, t in batch])
            cur.executemany("UPDATE diets SET embedding = CAST(%s AS vector) WHERE professional_id = %s AND id = %s",
                            [(str(v), args.professional_id, i) for (i, _), v in zip(batch, vectors)])
            done += len(batch)
        conn.commit()
        embed_s = time.perf_counter() - t1
        cur.execute("SELECT count(*) FILTER (WHERE embedding IS NOT NULL), count(*) FROM diets WHERE professional_id = %s", (args.professional_id,))
        with_vec, total = cur.fetchone()
    report = {"embedded_now": done, "with_embedding": with_vec, "diets": total, "truncated_at_max_seq_length": truncated, "max_seq_length": max_len,
              "model_load_s": round(load_s, 1), "embedding_s": round(embed_s, 1), "ms_per_diet": round(1000 * embed_s / max(done, 1), 1)}
    print(json.dumps(report))
    (DATASET_DIR / "embed_corpus_log.json").write_text(json.dumps({"professional_id": args.professional_id, "model": args.model, "revision": args.revision, "source_column": args.source_column, **report}, indent=1), encoding="utf-8")
    return 0 if with_vec == total else 1


if __name__ == "__main__":
    sys.exit(main())
