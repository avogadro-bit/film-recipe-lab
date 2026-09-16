import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from fuji_recipe_lab import official_luts
from fuji_recipe_lab.lut_install import install_archive


class LutInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.archive=self.root/'source.zip'
        self.destination=self.root/'installed'
        self.data=b'synthetic test data, never a Fuji LUT'
        self.manifest={'files':{'test':{'file':'test.cube','original':'pack/test.cube',
            'sha256':hashlib.sha256(self.data).hexdigest()}}}

    def archive_with(self,data):
        with ZipFile(self.archive,'w') as z:
            z.writestr('pack/test.cube',data)
            z.writestr('../outside.txt',b'must not be extracted')

    def test_verified_members_only_are_installed(self):
        self.archive_with(self.data)
        with patch('fuji_recipe_lab.lut_install.MANIFEST',self.manifest):
            install_archive(self.archive,self.destination)
        self.assertEqual((self.destination/'test.cube').read_bytes(),self.data)
        self.assertEqual([p.name for p in self.destination.iterdir()],['test.cube'])
        self.assertFalse((self.root/'outside.txt').exists())

    def test_bad_hash_does_not_replace_existing_installation(self):
        self.destination.mkdir();old=self.destination/'test.cube';old.write_bytes(b'old')
        self.archive_with(b'wrong')
        with patch('fuji_recipe_lab.lut_install.MANIFEST',self.manifest), self.assertRaises(ValueError):
            install_archive(self.archive,self.destination)
        self.assertEqual(old.read_bytes(),b'old')

    def test_extracted_folder_and_subfolder_are_detected(self):
        folder = self.root/'unpacked'/'pack'
        folder.mkdir(parents=True)
        (folder/'test.cube').write_bytes(self.data)
        with patch('fuji_recipe_lab.lut_install.MANIFEST', self.manifest):
            for source in (folder.parent, folder):
                install_archive(source, self.destination)
                self.assertEqual((self.destination/'test.cube').read_bytes(), self.data)

    def test_modified_folder_leaves_installed_luts_unchanged(self):
        folder = self.root/'unpacked'
        folder.mkdir()
        (folder/'test.cube').write_bytes(b'wrong')
        self.destination.mkdir()
        (self.destination/'test.cube').write_bytes(b'old')
        with patch('fuji_recipe_lab.lut_install.MANIFEST', self.manifest), self.assertRaises(ValueError):
            install_archive(folder, self.destination)
        self.assertEqual((self.destination/'test.cube').read_bytes(), b'old')

    def test_missing_members_do_not_create_partial_installation(self):
        with ZipFile(self.archive,'w') as z:z.writestr('unrelated.cube',self.data)
        with patch('fuji_recipe_lab.lut_install.MANIFEST',self.manifest), self.assertRaises(ValueError):
            install_archive(self.archive,self.destination)
        self.assertFalse(self.destination.exists())

    def test_missing_official_asset_fails_explicitly_without_fallback(self):
        with patch.dict(os.environ,{'FUJI_RECIPE_LUT_DIR':str(self.destination)}):
            official_luts.load_lut.cache_clear()
            self.addCleanup(official_luts.load_lut.cache_clear)
            self.assertEqual(len(official_luts.missing_luts()),10)
            with self.assertRaisesRegex(ValueError,'Fuji LUT missing'):
                official_luts.load_lut('classic_negative')
