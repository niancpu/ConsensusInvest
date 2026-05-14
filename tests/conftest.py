"""Shared pytest configuration."""

from __future__ import annotations

import os


# API smoke tests import consensusinvest.app during collection. Production
# runtime now requires an explicit real LLM provider, so tests declare that
# contract up front without adding provider secrets.
os.environ.setdefault("CONSENSUSINVEST_LLM_PROVIDER", "litellm")
os.environ.setdefault("CONSENSUSINVEST_LLM_MODEL", "openai/gpt-4.1-mini")
os.environ.setdefault("CONSENSUSINVEST_EVIDENCE_STORE_BACKEND", "memory")
os.environ.setdefault("CONSENSUSINVEST_ALLOW_IN_MEMORY_RUNTIME", "1")
