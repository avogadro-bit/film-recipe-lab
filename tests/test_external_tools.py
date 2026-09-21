import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fuji_recipe_lab.external_tools import find_exiftool
from fuji_recipe_lab import raw, optics


class ExternalToolTests(unittest.TestCase):
    def test_path_takes_priority(self):
        with patch('fuji_recipe_lab.external_tools.shutil.which', return_value='/custom/exiftool') as which:
            self.assertEqual(find_exiftool(), '/custom/exiftool')
            which.assert_called_once_with('exiftool')

    def test_macos_fallbacks_with_finder_path(self):
        for location in ('/opt/homebrew/bin/exiftool', '/usr/local/bin/exiftool', '/opt/local/bin/exiftool'):
            with self.subTest(location=location), \
                 patch('fuji_recipe_lab.external_tools.sys.platform', 'darwin'), \
                 patch('fuji_recipe_lab.external_tools.shutil.which', side_effect=lambda p: p if p == location else None):
                self.assertEqual(find_exiftool(), str(Path(location).resolve()))

    def test_missing_is_optional(self):
        with patch('fuji_recipe_lab.external_tools.shutil.which', return_value=None):
            self.assertIsNone(find_exiftool())

    def test_non_macos_does_not_search_macos_locations(self):
        with patch('fuji_recipe_lab.external_tools.sys.platform', 'linux'), \
             patch('fuji_recipe_lab.external_tools.shutil.which', return_value=None) as which:
            self.assertIsNone(find_exiftool())
            which.assert_called_once_with('exiftool')

    def test_metadata_invokes_resolved_binary(self):
        with patch.object(raw, 'require_local'), \
             patch.object(raw, 'find_exiftool', return_value='/custom/exiftool'), \
             patch.object(raw.subprocess, 'run', return_value=SimpleNamespace(stdout='[{"EXIF:Model":"Test"}]')) as run:
            self.assertEqual(raw.exif(Path('/photos/test.raf'))['Model'], 'Test')
            self.assertEqual(run.call_args.args[0][0], '/custom/exiftool')

    def test_optics_metadata_and_opcode_use_resolved_binary(self):
        metadata = {'Make':'LEICA', 'Model':'LEICA M11', 'Software':'1.0', 'PhotometricInterpretation':32803}
        optics._inspect.cache_clear()
        with patch.object(optics, 'find_exiftool', return_value='/custom/exiftool'), \
             patch.object(optics, 'parse_warp', return_value={}), \
             patch.object(optics.subprocess, 'run', side_effect=[SimpleNamespace(stdout=json.dumps([metadata])), SimpleNamespace(stdout=b'opcode')]) as run:
            result = optics._inspect(Path('/photos/test.dng'), 0, 0)
            self.assertTrue(result['distortion'])
            self.assertEqual([c.args[0][0] for c in run.call_args_list], ['/custom/exiftool'] * 2)
        optics._inspect.cache_clear()
