import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kora import compatibility


class BrandingCompatibilityTests(unittest.TestCase):
    def test_existing_luts_and_webview_are_retained(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)):
            home = Path(directory)
            self.assertEqual(compatibility.lut_directory(), home / '.local/share/kora/luts')
            self.assertEqual(compatibility.mac_webview_directory(), home / 'Library/Application Support/KŌRA/WebView')
            legacy_luts = home / '.local/share/fuji-recipe-lab/luts'
            legacy_webview = home / 'Library/Application Support/Film Recipe Lab/WebView'
            for path in (legacy_luts, legacy_webview):
                path.mkdir(parents=True)
            self.assertEqual(compatibility.lut_directory(), legacy_luts)
            self.assertEqual(compatibility.mac_webview_directory(), legacy_webview)
            current = home / '.local/share/kora/luts'
            current.mkdir(parents=True)
            self.assertEqual(compatibility.lut_directory(), current)
            self.assertTrue(legacy_luts.exists())

    def test_new_environment_names_override_legacy_aliases(self):
        with patch.dict(os.environ, {'FUJI_RECIPE_LUT_DIR': 'legacy', 'FILM_RECIPE_LAB_NO_BROWSER': '1'}, clear=True):
            self.assertEqual(compatibility.lut_override(), 'legacy')
            self.assertTrue(compatibility.browser_disabled())
            with patch.dict(os.environ, {'KORA_LUT_DIR': 'current', 'KORA_NO_BROWSER': '0'}):
                self.assertEqual(compatibility.lut_override(), 'current')
                self.assertFalse(compatibility.browser_disabled())
