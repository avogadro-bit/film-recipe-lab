"""Native delegate checks, also run with the macOS release environment."""
import importlib.util
import sys
import threading
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(sys.platform == "darwin" and importlib.util.find_spec("AppKit"),
                     "Cocoa bindings are only installed in the macOS release environment")
class MacLifecycleTests(unittest.TestCase):
    def setUp(self):
        from fuji_recipe_lab.macos_app import StudioAppDelegate
        self.delegate = StudioAppDelegate.alloc().init()
        self.delegate.session_url = None
        self.delegate.open_when_ready = False
        self.delegate.stopping = threading.Event()
        self.delegate.server = Mock()
        self.delegate.worker = Mock()

    def test_reopen_pending_startup_is_deferred(self):
        with patch("fuji_recipe_lab.macos_app.webbrowser.open") as opened:
            self.delegate.applicationShouldHandleReopen_hasVisibleWindows_(None, False)
            self.assertTrue(self.delegate.open_when_ready)
            opened.assert_not_called()

    def test_reopen_uses_current_session_without_starting_second_server(self):
        self.delegate.session_url = "http://127.0.0.1:8877/#session=test"
        with patch("fuji_recipe_lab.macos_app.webbrowser.open") as opened:
            for _ in range(3):
                self.delegate.applicationShouldHandleReopen_hasVisibleWindows_(None, False)
            self.assertEqual(opened.call_count, 3)
            opened.assert_called_with(self.delegate.session_url, new=2)
            self.delegate.worker.start.assert_not_called()

    def test_quit_shuts_down_http_loop(self):
        self.delegate.worker.is_alive.return_value = True
        self.delegate.applicationWillTerminate_(None)
        self.assertTrue(self.delegate.stopping.is_set())
        self.delegate.server.shutdown.assert_called_once()
        self.delegate.worker.join.assert_called_once_with(timeout=3)

    def test_quit_before_worker_started_does_not_join(self):
        self.delegate.server = None
        self.delegate.worker.is_alive.return_value = False
        self.delegate.applicationWillTerminate_(None)
        self.delegate.worker.join.assert_not_called()
