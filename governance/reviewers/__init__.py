"""Real second-model reviewers for the cross-model review gate.

The core library is dependency-free and ships only the in-process reviewers
in `governance.review`. This subpackage adds adapters that send the action to
a real, independent LLM with a skeptical prompt and parse its verdict, so the
review gate can run against an actual second model in production.

The LLM SDKs are optional dependencies, imported lazily inside the adapter
factories. Install what you need:

    pip install -e ".[anthropic]"   # Claude reviewer
    pip install -e ".[openai]"      # GPT reviewer

Every adapter is fail-closed: a crashing call, an unreachable model, or any
response that is not an explicit approval resolves to DENY.
"""
from __future__ import annotations

from .llm import LLMReviewer, anthropic_reviewer, openai_reviewer

__all__ = ["LLMReviewer", "anthropic_reviewer", "openai_reviewer"]
