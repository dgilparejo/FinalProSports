"""FastAPI entry point. Wires the application through the composition root and mounts the REST adapters."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finalprosports.infrastructure.adapter.inbound.rest.exception.global_exception_handler import register_exception_handlers
from finalprosports.infrastructure.adapter.inbound.rest.router import build_router
from finalprosports.infrastructure.adapter.inbound.rest.security.authentication import build_authentication_dependency
from finalprosports.infrastructure.composition_root import CompositionRoot
from finalprosports.infrastructure.config.security import KeycloakConfig, TokenVerifier
from finalprosports.infrastructure.config.settings import Settings

# CORS, explicitly (v1 seam 8). No wildcard anywhere: the origin is the SPA and nothing else, the
# methods are the ones the API answers to and the headers are the ones the SPA sends.
# `tests/architecture/test_cors_has_no_wildcard.py` fails if a `*` is ever put back.
CORS_ORIGINS = ["http://localhost:4200", "http://127.0.0.1:4200"]
CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type", "Accept"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    root = CompositionRoot.from_env()
    app = FastAPI(title="finalprosports", version="0.2.0",
                  description="Asistente de prescripción dietética basado en casos: recuperación por atributos, composición por consenso, rotación de la versión anterior "
                              "y validación con las reglas del profesional. Todas las consultas están acotadas al profesional del token (realm fps, rol entrenador).")
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=CORS_METHODS,
                       allow_headers=CORS_HEADERS, allow_credentials=False, max_age=600)
    # Kept on app.state so the fast test suite can override THIS dependency (and only this one):
    # FastAPI keys dependency_overrides on the callable object, and the callable is a closure.
    config = KeycloakConfig.from_settings(settings)
    app.state.authenticate = build_authentication_dependency(TokenVerifier(config), root.professional_directory, config.required_role)
    app.include_router(build_router(root, settings, app.state.authenticate))
    register_exception_handlers(app)

    @app.get("/health", tags=["health"])
    def health() -> dict:
        """The ONLY open endpoint: liveness for the container. Says nothing about anyone's data."""
        return {"status": "ok"}

    return app


app = create_app()
