import pytest
from main import app


@pytest.fixture(autouse=True)
def disable_rate_limiter():
    """Disable the rate limiter for every test by default.
    Tests that specifically exercise rate limiting re-enable it themselves."""
    app.state.limiter.enabled = False
    yield
    app.state.limiter.enabled = True
