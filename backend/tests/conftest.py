import os

# Tests must never pick up a developer's real keys or hit real providers.
os.environ.update(
    {
        "APP_ENV": "test",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "HF_TOKEN": "",
        "OPENAI_API_KEY": "",
        "ADMIN_PASSCODE": "",
    }
)

from collections.abc import Iterator

import pytest

from app.api.security import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    limiter.reset()
    yield
    limiter.reset()
