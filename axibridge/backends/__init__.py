"""Execution backends: the third extension point.

Backends are deliberately *not* feature-symmetric. Each declares its own
parameter model and a :class:`~axibridge.backends.base.BackendCapabilities`,
and the UI renders only what the active backend actually supports.
"""

from .base import BackendCapabilities, ExecutionBackend, JobControl  # noqa: F401
