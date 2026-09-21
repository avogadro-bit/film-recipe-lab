import sys
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import numpy as np
from kora.activity import user_activity
from kora.gui import Library


class ExportActivityTests(unittest.TestCase):
    def test_macos_activity_is_released_even_when_export_fails(self):
        process=Mock();token=object();process.beginActivityWithOptions_reason_.return_value=token
        foundation=SimpleNamespace(NSProcessInfo=Mock(),NSActivityUserInitiatedAllowingIdleSystemSleep=123)
        foundation.NSProcessInfo.processInfo.return_value=process
        with patch.object(sys,'platform','darwin'),patch.dict(sys.modules,Foundation=foundation):
            with self.assertRaisesRegex(RuntimeError,'failed'):
                with user_activity():
                    process.beginActivityWithOptions_reason_.assert_called_once_with(123,'Developing and exporting photographs')
                    process.endActivity_.assert_not_called()
                    raise RuntimeError('failed')
        process.endActivity_.assert_called_once_with(token)

    def test_simultaneous_full_decode_cache_misses_are_coalesced(self):
        with tempfile.TemporaryDirectory() as scratch:
            path=Path(scratch)/'image.DNG';path.write_bytes(b'fixture')
            lib=Library([],scratch,capacity={'export_workers':4,'thumbnail_workers':4})
            identifier=lib.add(path)['id'];pixels=np.ones((12,18,3),np.float32)
            entered=threading.Event();release=threading.Event();second=threading.Event()
            def decode(*args,**kwargs):
                entered.set()
                if not release.wait(3):raise RuntimeError('test timed out')
                return pixels
            def another():
                second.set();return lib.full_linear(identifier)
            with patch('kora.gui.decode',side_effect=decode) as decoder,ThreadPoolExecutor(2) as pool:
                first=pool.submit(lib.full_linear,identifier)
                try:
                    self.assertTrue(entered.wait(1));other=pool.submit(another)
                    self.assertTrue(second.wait(1))
                finally:release.set()
                self.assertIs(first.result(timeout=3),pixels)
                self.assertIs(other.result(timeout=3),pixels)
                decoder.assert_called_once()
