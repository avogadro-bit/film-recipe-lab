"""Responsive Dock/Finder lifecycle for the browser-based macOS studio."""
import threading
import webbrowser

from AppKit import NSApplication, NSApplicationActivationPolicyRegular, NSMenu, NSMenuItem, NSAlert
from Foundation import NSObject
from PyObjCTools import AppHelper

from .gui import serve
from .desktop import record_crash


class StudioAppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.worker.start()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
        self.openStudio_(None)
        return False

    def openStudio_(self, sender):
        if self.session_url:
            webbrowser.open(self.session_url, new=2)
        else:
            self.open_when_ready = True

    def applicationWillTerminate_(self, notification):
        # AppKit runs on the main thread; the HTTP loop is on the worker.
        self.stopping.set()
        if self.server is not None:
            self.server.shutdown()
        if self.worker.is_alive():
            self.worker.join(timeout=3)


def run(roots, port):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = StudioAppDelegate.alloc().init()
    delegate.server = None
    delegate.session_url = None
    delegate.open_when_ready = True
    delegate.stopping = threading.Event()
    result = [0]

    def ready(server, url):
        delegate.server = server
        delegate.session_url = url
        def show():
            if not delegate.stopping.is_set() and delegate.open_when_ready:
                delegate.open_when_ready = False
                delegate.openStudio_(None)
        AppHelper.callAfter(show)

    def failed(exc):
        record_crash(exc)
        result[0] = 2
        def alert():
            message = NSAlert.alloc().init()
            message.setMessageText_("Film Recipe Lab could not start")
            message.setInformativeText_(str(exc))
            message.runModal()
            app.terminate_(None)
        AppHelper.callAfter(alert)

    def worker():
        try:
            serve(roots, port, on_ready=ready)
        except Exception as exc:
            failed(exc)

    delegate.worker = threading.Thread(target=worker, name="FilmRecipeLabServer", daemon=True)
    app.setDelegate_(delegate)
    menu = NSMenu.alloc().init()
    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Film Recipe Lab", None, "")
    submenu = NSMenu.alloc().initWithTitle_("Film Recipe Lab")
    reopen = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Open Film Recipe Lab", "openStudio:", "o")
    reopen.setTarget_(delegate)
    submenu.addItem_(reopen)
    submenu.addItem_(NSMenuItem.separatorItem())
    submenu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Film Recipe Lab", "terminate:", "q"))
    item.setSubmenu_(submenu)
    menu.addItem_(item)
    app.setMainMenu_(menu)
    app.run()
    return result[0]
