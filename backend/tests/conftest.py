"""Test fixtures.

The suite is split in two, by design:

  * **Unit tests** run everywhere with no Postgres, no Ollama, and no API key.
    They cover chunking, routing, the Ship 30 rubric, the sanitizer, and the
    grounding gate — the logic most likely to regress.
  * **Integration tests** are marked `integration` and skip automatically unless
    `TEST_DATABASE_URL` is set. They cover persistence, hybrid retrieval, and
    the API contract end to end.

This split is what lets CI run on every push without provisioning anything.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("CHAT_PROVIDER", "echo")
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")
os.environ.setdefault("LOG_LEVEL", "WARNING")


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: requires a live Postgres (TEST_DATABASE_URL)"
    )


@pytest.fixture(scope="session")
def database_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL")


@pytest.fixture
def requires_db(database_url):
    if not database_url:
        pytest.skip("set TEST_DATABASE_URL to run integration tests")
    return database_url


@pytest.fixture
def sample_transcript() -> str:
    return (
        "**Host:** What is the first signal of product-market fit?\n\n"
        "**Guest:** [00:02:14] Retention flattening. If the month-six cohort is "
        "still sloping down you do not have it, whatever growth says.\n\n"
        "**Host:** And the qualitative side?\n\n"
        "**Guest:** [00:04:30] The work changes shape. You stop convincing people "
        "to try it and start apologising for how slow it is.\n\n"
    )
