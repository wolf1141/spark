"""SPARK — IRON's planning stage shell."""

import sys


def _ensure_lossy_console_safe() -> None:
    """Survive cp1252 (and other lossy) consoles without crashing on glyphs.

    Reconfigures stdout/stderr to replace unencodable characters instead of
    raising UnicodeEncodeError, so the exit code reflects the operation, not
    the print.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


_ensure_lossy_console_safe()
