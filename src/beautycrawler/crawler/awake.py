"""Keep Windows awake during a long crawl.

`SetThreadExecutionState` asks Windows not to sleep or turn the screen off (on laptops
with Modern Standby a screen timeout also suspends the machine) until the request is
cleared or the process exits. Nothing is changed in the power settings. Elsewhere this
is a no-op.
"""

import ctypes
import sys
from collections.abc import Iterator
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _set_state(flags: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))


@contextmanager
def keep_awake(enabled: bool = True) -> Iterator[bool]:
    """Yields whether the request was made (False when disabled or not on Windows)."""
    active = enabled and _set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    try:
        yield active
    finally:
        if active:
            _set_state(ES_CONTINUOUS)
