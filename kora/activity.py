"""Scope macOS energy-management assertions to work requested by the user."""
from contextlib import contextmanager
import sys


@contextmanager
def user_activity():
    process = token = None
    if sys.platform == 'darwin':
        try:
            from Foundation import NSProcessInfo, NSActivityUserInitiatedAllowingIdleSystemSleep
        except ImportError:
            pass  # Cocoa is optional for command-line installations.
        else:
            process = NSProcessInfo.processInfo()
            token = process.beginActivityWithOptions_reason_(
                NSActivityUserInitiatedAllowingIdleSystemSleep, 'Developing and exporting photographs')
    try:
        yield
    finally:
        if token is not None:
            process.endActivity_(token)
