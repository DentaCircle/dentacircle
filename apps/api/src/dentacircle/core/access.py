"""Route access markers. Health checks are the only public routes in this slice."""

from collections.abc import Callable


def public[F: Callable[..., object]](endpoint: F) -> F:
    """Mark a route as callable without a login. It must not return clinic or patient data."""
    endpoint.is_public = True  # type: ignore[attr-defined]
    return endpoint
