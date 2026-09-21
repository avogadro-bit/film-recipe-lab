"""Bounded local diagnostics. Never serialize request bodies, pixels or locals."""
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import platform
import re
import sys
import threading
import traceback
import uuid

from . import __version__
from .platform_support import windows_data_directory
from .compatibility import logs_directory

MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 3
RUN_ID = uuid.uuid4().hex[:16]
_lock = threading.RLock()
_installed = False
_secrets = set()
CONTEXT_KEYS = {'photo_id', 'film', 'grain', 'grain_size', 'zoom', 'pan_x', 'pan_y',
                'x', 'y', 'size', 'level', 'generation', 'revision', 'request_id',
                'status', 'recipe_hash', 'width', 'height', 'count', 'online', 'source',
                'client_time', 'client_version'}


def log_path():
    if sys.platform == 'win32':
        return windows_data_directory() / 'Logs' / 'errors.jsonl'
    return logs_directory() / 'errors.jsonl'


def register_secret(value):
    with _lock:
        _secrets.add(str(value))


def clean(value, limit=2000):
    text = str(value)[:16000]
    with _lock:
        for secret in _secrets:
            if secret:
                text = text.replace(secret, '[session]')
    text = re.sub(r'https?://[^\s\"\'<>]+', '[url]', text)
    text = re.sub(r'(?i)(session|token|authorization)[=: ]+[^\s,;\"\']+', r'\1=[redacted]', text)
    text = re.sub(r'(?:[A-Za-z]:[\\/]|/)[^\n\r\"\'<>]*', '[path]', text)
    return text[:limit]


def context_values(context):
    return {key: clean(value, 160) if isinstance(value, str) else value
            for key, value in (context or {}).items()
            if key in CONTEXT_KEYS and isinstance(value, (str, int, float, bool))
            and not (isinstance(value, float) and not math.isfinite(value))}


def record_error(operation, exc=None, *, message=None, context=None, stack=None, path=None):
    """Return a diagnostic ID, or None if storage failed; logging never breaks work."""
    try:
        # Validation errors normally echo input values (including whole recipes).
        if exc is not None and type(exc).__name__ == 'ValidationError':
            detail = json.dumps(exc.errors(include_input=False, include_context=False, include_url=False))
        else:
            detail = str(exc) if exc is not None else str(message or '')
        frames = ([{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                   for f in traceback.extract_tb(exc.__traceback__)[-24:]]
                  if exc is not None else [])
        event_id = uuid.uuid4().hex[:12]
        event = {'time': datetime.now(timezone.utc).isoformat(), 'version': __version__,
                 'run_id': RUN_ID, 'id': event_id, 'operation': clean(operation, 100),
                 'error': clean(f'{type(exc).__name__}: {detail}' if exc is not None else detail),
                 'context': context_values(context), 'frames': frames,
                 'runtime': {'os': platform.system(), 'release': platform.release(),
                             'arch': platform.machine(), 'python': platform.python_version()}}
        if stack:
            event['client_stack'] = clean(stack, 4000)
        data = json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n'
        target = path or log_path()
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.stat().st_size + len(data.encode()) > MAX_BYTES:
                for index in range(BACKUPS, 0, -1):
                    source = target if index == 1 else target.with_name(f'errors.{index-1}.jsonl')
                    if source.exists():
                        source.replace(target.with_name(f'errors.{index}.jsonl'))
            with target.open('a', encoding='utf-8') as stream:
                stream.write(data)
            target.chmod(0o600)
        return event_id
    except Exception:
        return None


class ErrorLogHandler(logging.Handler):
    def emit(self, record):
        try:
            record_error('python-logging', record.exc_info[1] if record.exc_info else None,
                         message=record.getMessage(), context={'source': record.name})
        except Exception:
            pass


def install_hooks():
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
        old_sys, old_thread, old_unraisable = sys.excepthook, threading.excepthook, sys.unraisablehook
        def system_hook(kind, value, tb):
            record_error('uncaught-python', value)
            old_sys(kind, value, tb)
        def thread_hook(args):
            record_error('uncaught-thread', args.exc_value)
            old_thread(args)
        def unraisable_hook(args):
            record_error('unraisable-python', args.exc_value)
            old_unraisable(args)
        sys.excepthook, threading.excepthook, sys.unraisablehook = system_hook, thread_hook, unraisable_hook
        logging.getLogger().addHandler(ErrorLogHandler(logging.ERROR))
