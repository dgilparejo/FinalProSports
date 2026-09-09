# -*- coding: utf-8 -*-
"""v2 · What the API exposes without a token, and what CORS allows.

Static: reads the router and the CORS constants from the source, so it needs neither a database nor
a running Keycloak. Run: python tests/architecture/test_api_surface_is_guarded.py
"""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
SRC = ROOT / "src" / "finalprosports"
sys.path.insert(0, str(ROOT / "src"))

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {name}{'' if condition else ': ' + detail}")
    if not condition:
        failures.append(name)


def run() -> None:
    # ------------------------------------------------------------------ CORS
    from finalprosports.main import CORS_HEADERS, CORS_METHODS, CORS_ORIGINS

    for label, values in (("origins", CORS_ORIGINS), ("methods", CORS_METHODS), ("headers", CORS_HEADERS)):
        check(f"cors_{label}_carry_no_wildcard", "*" not in values and not any("*" in v for v in values),
              f"{label} = {values}")
    check("cors_origins_are_the_spa_only",
          all(o.startswith(("http://localhost:4200", "http://127.0.0.1:4200")) for o in CORS_ORIGINS), str(CORS_ORIGINS))
    check("cors_allows_the_authorization_header", "Authorization" in CORS_HEADERS)

    main_src = (SRC / "main.py").read_text(encoding="utf-8")
    check("cors_is_configured_from_those_constants",
          "allow_origins=CORS_ORIGINS" in main_src and "allow_methods=CORS_METHODS" in main_src and "allow_headers=CORS_HEADERS" in main_src,
          "the middleware must read the audited constants, not inline literals")

    # ------------------------------------------------- every route is guarded
    router_src = (SRC / "infrastructure" / "adapter" / "inbound" / "rest" / "router.py").read_text(encoding="utf-8")
    check("the_api_router_mounts_the_authentication_dependency",
          'APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])' in router_src,
          "the dependency must be on the ROUTER, so a new endpoint is guarded without remembering to decorate it")

    # /health is the only route declared outside the guarded router
    tree = ast.parse(main_src)
    open_routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and isinstance(deco.func.value, ast.Name) \
                        and deco.func.value.id == "app" and deco.func.attr in {"get", "post", "put", "delete", "patch"}:
                    open_routes.append(deco.args[0].value if deco.args else "?")
    check("health_is_the_only_open_route", open_routes == ["/health"], f"open routes: {open_routes}")

    # ------------------------------ the subject of the migration IS the realm's
    realm = json.loads((REPO / "keycloak" / "realm-fps.json").read_text(encoding="utf-8"))
    trainer = next(u for u in realm["users"] if u["username"] == "entrenador")
    migration = (ROOT / "db" / "migrations" / "versions" / "0011_keycloak_subject.py").read_text(encoding="utf-8")
    check("the_migration_maps_the_subject_of_the_versioned_realm", f'"{trainer["id"]}"' in migration,
          f"realm says {trainer['id']}, migration 0011 does not carry it")

    # The loader is what actually creates the professional row on a clean bootstrap (the migrations run
    # before any data exists), so it must carry the SAME subject or a valid token gets a 403.
    loader = (REPO / "pipeline" / "src" / "pipeline" / "load_postgres.py").read_text(encoding="utf-8")
    check("the_loader_maps_the_same_subject", f'"{trainer["id"]}"' in loader,
          "load_postgres.py creates the professionals row; without the mapping the API answers 403 to a valid token")
    check("the_loader_writes_the_subject_with_the_row",
          "keycloak_subject" in loader and "INSERT INTO professionals" in loader)

    # ------------------------------------ the realm itself keeps its promises
    front = next(c for c in realm["clients"] if c["clientId"] == "fps-frontend")
    check("the_spa_client_is_public", front["publicClient"] is True)
    check("the_spa_client_has_no_implicit_flow", front["implicitFlowEnabled"] is False)
    check("the_spa_client_has_no_direct_access_grants", front["directAccessGrantsEnabled"] is False)
    check("the_spa_client_requires_pkce_s256", front["attributes"].get("pkce.code.challenge.method") == "S256")
    check("redirect_uris_are_limited_to_the_spa_origin",
          all(u.startswith("http://localhost:4200/") for u in front["redirectUris"]), str(front["redirectUris"]))
    check("web_origins_carry_no_wildcard", "*" not in front["webOrigins"] and "+" not in front["webOrigins"], str(front["webOrigins"]))
    mapper = next((m for m in front.get("protocolMappers", []) if m["protocolMapper"] == "oidc-audience-mapper"), None)
    check("an_audience_mapper_puts_fps_backend_in_aud",
          mapper is not None and mapper["config"]["included.client.audience"] == "fps-backend"
          and mapper["config"]["access.token.claim"] == "true",
          "without it the token carries aud: account and validating the audience validates nothing")
    check("token_lifetimes_are_short", realm["accessTokenLifespan"] == 300 and realm["ssoSessionIdleTimeout"] == 1800,
          f"access {realm['accessTokenLifespan']}s / refresh {realm['ssoSessionIdleTimeout']}s")
    check("there_is_exactly_one_realm_role", [r["name"] for r in realm["roles"]["realm"]] == ["entrenador"])
    check("the_no_role_user_really_has_no_role",
          next(u for u in realm["users"] if u["username"] == "sinrol")["realmRoles"] == [],
          "without a valid token that lacks the role, the 403 cannot be demonstrated")
    check("no_user_carries_an_e_mail",
          all("email" not in u for u in realm["users"]),
          "the PII audit criterion is 0 e-mail patterns in the tree and it takes no per-file exceptions")
    check("verify_profile_is_disabled_because_the_users_have_no_e_mail",
          any(a["alias"] == "VERIFY_PROFILE" and a["enabled"] is False for a in realm.get("requiredActions", [])),
          "Keycloak's default user profile requires an e-mail and would put an interactive step before every login")

    # the sign-in page is the application's, not a stock one (la memoria (capítulo de seguridad) §2)
    check("the_realm_uses_the_application_login_theme", realm.get("loginTheme") == "finalprosports")
    check("the_login_theme_only_overrides_the_skin",
          (REPO / "keycloak" / "themes" / "finalprosports" / "login" / "theme.properties").exists()
          and not list((REPO / "keycloak" / "themes" / "finalprosports" / "login").glob("*.ftl")),
          "a forked template would need re-checking on every Keycloak upgrade, and sign-in is where a silent breakage locks everyone out")
    check("the_sign_in_page_speaks_the_language_of_the_application", realm.get("defaultLocale") == "es")
    theme_icon = REPO / "keycloak" / "themes" / "finalprosports" / "login" / "resources" / "img" / "favicon.ico"
    app_icon = REPO / "frontend" / "public" / "favicon.ico"
    check("the_sign_in_tab_carries_the_icon_of_the_application",
          theme_icon.exists() and app_icon.exists() and theme_icon.read_bytes() == app_icon.read_bytes(),
          "the same file, byte for byte: two icons that drift apart make the identity provider look like another product")


if __name__ == "__main__":
    run()
    print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILED: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)
