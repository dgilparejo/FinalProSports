# -*- coding: utf-8 -*-
"""v2 · The authentication seam fails CLOSED, and nothing in the tree can quietly re-open it.

A context variable is implicit context, so its failure mode is silence. These tests are the ones
that make the silence impossible: the adapter raises when nothing is bound, the context variable has
exactly one writer, every route is behind the dependency, CORS carries no wildcard, and the adapter
that used to hand out a professional without a token is gone from the tree.

No dependency needed: source is parsed with `ast`, the rest is plain imports. Run: python tests/architecture/test_authentication_fails_closed.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "finalprosports"
sys.path.insert(0, str(ROOT / "src"))

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'' if condition else ': ' + detail}")
    if not condition:
        failures.append(name)


def python_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


# ---------------------------------------------------------------- fail closed

def run() -> None:
    from finalprosports.infrastructure.adapter.outbound.security.request_scoped_professional_adapter import (
        RequestScopedProfessionalAdapter,
    )
    from finalprosports.infrastructure.config.security import (
        ProfessionalContextNotBound, bind_professional, current_professional_id_or_raise, role_of,
    )

    # 1 · the adapter raises outside a request
    adapter = RequestScopedProfessionalAdapter()
    try:
        value = adapter.current_professional_id()
        check("adapter_outside_a_request_raises", False, f"it returned {value!r} instead of raising")
    except ProfessionalContextNotBound:
        check("adapter_outside_a_request_raises", True)

    # 2 · once bound, it returns exactly what was bound
    bind_professional("prof_test")
    check("adapter_returns_the_bound_professional", adapter.current_professional_id() == "prof_test")

    # 3 · the binding does not leak between contexts: a fresh context sees nothing
    import contextvars
    out: list = []
    contextvars.Context().run(lambda: out.append(_safe_read(current_professional_id_or_raise)))
    check("a_fresh_context_sees_no_professional", out[0] is ProfessionalContextNotBound,
          f"a clean context read {out[0]!r}")

    # 4 · the context reaches the threadpool FastAPI runs sync endpoints in
    import anyio
    seen: list = []

    async def _through_threadpool() -> None:
        from anyio.to_thread import run_sync
        seen.append(await run_sync(lambda: _safe_read(adapter.current_professional_id)))

    anyio.run(_through_threadpool)
    check("the_binding_reaches_the_threadpool", seen and seen[0] == "prof_test",
          f"a worker thread read {seen[0]!r}: a sync endpoint would not see the professional")

    # 5 · a missing realm_access is 'no role', not a KeyError
    check("absent_realm_access_is_no_role", role_of({"sub": "x"}, "entrenador") is False)
    check("empty_roles_is_no_role", role_of({"realm_access": {}}, "entrenador") is False)
    check("present_role_is_detected", role_of({"realm_access": {"roles": ["entrenador"]}}, "entrenador") is True)
    check("realm_access_of_the_wrong_shape_is_no_role", role_of({"realm_access": "entrenador"}, "entrenador") is False)

    # ------------------------------------------------------- one writer only
    writers = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bind_professional":
                writers.append(f"{path.relative_to(SRC)}:{node.lineno}")
    check("bind_professional_has_exactly_one_writer_in_src", len(writers) == 1, f"writers: {writers}")
    check("the_writer_is_the_authentication_dependency",
          bool(writers) and writers[0].replace("\\", "/").startswith("infrastructure/adapter/inbound/rest/security/authentication.py"),
          f"writer: {writers}")

    # -------------------------------------------- the v1 fixed adapter is gone
    fixed = SRC / "infrastructure" / "adapter" / "outbound" / "security" / "fixed_professional_adapter.py"
    check("the_fixed_professional_adapter_is_deleted", not fixed.exists(),
          "an adapter that returns a professional with no token must not exist in the delivered tree")
    mentions = [str(p.relative_to(SRC)) for p in python_files() if "FixedProfessionalAdapter" in p.read_text(encoding="utf-8")]
    check("nothing_references_the_fixed_adapter", not mentions, f"still referenced by {mentions}")

    # ------------------------- no broad handler can turn the bug into an answer
    # ProfessionalContextNotBound means a code path reached the adapter without authenticating. It has to
    # surface as a loud error. What would quietly undo that is a wide net upstream: an
    # `@app.exception_handler(Exception)`, or a registered type it happens to inherit from. Then the bug
    # becomes a tidy JSON response and nobody notices the tenant was never resolved.
    from finalprosports.infrastructure.adapter.inbound.rest.exception import global_exception_handler as handlers_module

    handlers_src = (SRC / "infrastructure" / "adapter" / "inbound" / "rest" / "exception" / "global_exception_handler.py")
    registered: list[str] = []
    for node in ast.walk(ast.parse(handlers_src.read_text(encoding="utf-8"))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr == "exception_handler" and deco.args and isinstance(deco.args[0], ast.Name)):
                registered.append(deco.args[0].id)

    check("some_handlers_were_found", len(registered) >= 8, f"only found {registered}")
    check("no_handler_is_registered_for_a_catch_all",
          not ({"Exception", "BaseException", "RuntimeError"} & set(registered)),
          f"registered handlers: {registered}")

    # And, name by name, no registered type is an ancestor of ours: FastAPI dispatches by isinstance.
    import builtins
    caught_by = []
    for name in registered:
        exc_type = getattr(handlers_module, name, None) or getattr(builtins, name, None)
        check(f"the_handler_type_{name}_resolves", isinstance(exc_type, type), f"could not resolve {name}")
        if isinstance(exc_type, type) and issubclass(ProfessionalContextNotBound, exc_type):
            caught_by.append(name)
    check("no_registered_handler_catches_the_unbound_context", not caught_by,
          f"ProfessionalContextNotBound would be answered by the handler for {caught_by}")
    check("the_unbound_context_is_not_a_ValueError", not issubclass(ProfessionalContextNotBound, ValueError),
          "ValueError has a handler answering 422: the bug would come back as a tidy validation error")

    # The broad `except Exception` blocks that DO exist must not sit OVER a read of the professional.
    # Checked lexically, not per file: config/security.py legitimately contains both, in different places
    # (the wide net is inside TokenVerifier.verify; the reader is a module-level function beside it).
    def _reads_professional(node: ast.AST) -> bool:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                fn = inner.func
                name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
                if name.startswith("current_professional_id"):
                    return True
        return False

    def _is_broad(handler: ast.ExceptHandler) -> bool:
        if handler.type is None:                                        # bare `except:`
            return True
        names = [handler.type] if not isinstance(handler.type, ast.Tuple) else list(handler.type.elts)
        return any(isinstance(n, ast.Name) and n.id in {"Exception", "BaseException"} for n in names)

    swallowed = []
    for path in python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Try) and any(_is_broad(h) for h in node.handlers)                     and any(_reads_professional(stmt) for stmt in node.body):
                swallowed.append(f"{path.relative_to(SRC)}:{node.lineno}")
    check("no_broad_except_sits_over_a_read_of_the_professional", not swallowed,
          f"a wide except would swallow ProfessionalContextNotBound at {swallowed}")

    # ---------------------------------------------- the dependency stays async
    auth = SRC / "infrastructure" / "adapter" / "inbound" / "rest" / "security" / "authentication.py"
    tree = ast.parse(auth.read_text(encoding="utf-8"))
    inner = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "authenticate"]
    check("the_authentication_dependency_is_async", bool(inner) and isinstance(inner[0], ast.AsyncFunctionDef),
          "a SYNC dependency runs in a worker thread with a COPY of the context: the binding would be discarded")


def _safe_read(fn):
    from finalprosports.infrastructure.config.security import ProfessionalContextNotBound
    try:
        return fn()
    except ProfessionalContextNotBound:
        return ProfessionalContextNotBound


if __name__ == "__main__":
    run()
    print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)
