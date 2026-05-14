"""Entry point for `python -m consensusinvest` and the `consensusinvest` script."""

from __future__ import annotations

import os

import uvicorn

from .app import app  # re-exported so `uvicorn consensusinvest.main:app` also works


def run() -> None:
    host = os.environ.get("CONSENSUSINVEST_HOST", "127.0.0.1")
    port = int(os.environ.get("CONSENSUSINVEST_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
