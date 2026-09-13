"""
Shared test setup.

Two jobs:

1. Put src/ on sys.path once, so test modules can `import rag_pipeline`
   directly. Previously each test file did its own sys.path insert and two of
   them pointed at a "code/" directory that no longer exists — they only
   imported at all because an earlier test file had already fixed the path as a
   side effect of failing.

2. Install a fake `streamlit` package. app.py imports `streamlit.components.v1`,
   and a bare MagicMock in sys.modules["streamlit"] is not a package, so the
   submodule import raised ModuleNotFoundError and the whole module failed to
   load. Registering the submodules explicitly fixes that.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _install_fake_streamlit() -> None:
    """Register a stub streamlit package, including its submodules."""
    if isinstance(sys.modules.get("streamlit"), types.ModuleType) and not isinstance(
        sys.modules.get("streamlit"), MagicMock
    ):
        # The real Streamlit is already imported; leave it alone.
        return

    st = MagicMock(name="streamlit")

    # Decorators must return the wrapped function, not a MagicMock, so that
    # decorated helpers stay callable and inspectable in tests.
    def _passthrough_decorator(*_args, **_kwargs):
        def wrap(fn):
            return fn
        if _args and callable(_args[0]) and not _kwargs:
            return _args[0]
        return wrap

    st.cache_resource = _passthrough_decorator
    st.cache_data = _passthrough_decorator
    st.session_state = {}

    components = MagicMock(name="streamlit.components")
    components_v1 = MagicMock(name="streamlit.components.v1")
    components.v1 = components_v1
    st.components = components

    sys.modules["streamlit"] = st
    sys.modules["streamlit.components"] = components
    sys.modules["streamlit.components.v1"] = components_v1


_install_fake_streamlit()
