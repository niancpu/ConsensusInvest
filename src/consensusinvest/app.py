"""FastAPI application factory for ConsensusInvest."""

from __future__ import annotations

from fastapi import FastAPI

from .common.errors import install_error_handlers
from .report_module.router import router as report_module_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="ConsensusInvest API",
        version="0.1.0",
        description=(
            "Evidence-driven A-share investment research system. "
            "This server currently exposes the Report Module view APIs (docs/report_module)."
        ),
    )
    install_error_handlers(app)
    app.include_router(report_module_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
