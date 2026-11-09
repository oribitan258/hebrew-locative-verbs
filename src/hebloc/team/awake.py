"""Keep the computer from going to sleep while a long parse runs (no admin rights needed).

Windows: ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)`` for the life of the
command (the display may still turn off; closing a laptop lid can still sleep it, depending on the
lid setting). macOS: ``caffeinate -i -w <pid>``. Elsewhere: nothing (the guide tells the user).
Released automatically when the command ends or crashes.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


@contextmanager
def keep_awake():
    system = platform.system()
    proc = None
    active = False
    if system == "Windows":
        try:
            import ctypes

            active = bool(ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED))
        except (OSError, AttributeError):
            active = False
    elif system == "Darwin" and shutil.which("caffeinate"):
        proc = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
        active = True
    try:
        yield active
    finally:
        if system == "Windows" and active:
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        if proc is not None:
            proc.terminate()
