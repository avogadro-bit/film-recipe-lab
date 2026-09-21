import unittest
from pathlib import Path
import tempfile
import numpy as np
from kora.input_profiles import camera_profile,validate_linear_input,normalization_details
from kora.gui import Library
from kora.source_exposure import source_exposure

class CommonInputTests(unittest.TestCase):
    def test_camera_profile_is_scoped_to_leica_make(self):
        for m in [{'Make':'Canon','Model':'LEICA M11'}, {'Make':'Sony','Model':'ILCE-7M4'}]:
            self.assertIsNone(camera_profile(m))
        self.assertIsNotNone(camera_profile({'Make':' Leica Camera AG ','Model':'M11'}))

    def test_common_representation_keeps_signed_values_and_highlight_latitude(self):
        a=np.array([[[-.1,.18,4.]]],np.float64)
        b=validate_linear_input(a)
        self.assertEqual(b.dtype,np.float32)
        np.testing.assert_allclose(b,a)
        for bad in [np.zeros((2,2)),np.zeros((0,2,3)),np.zeros((2,2,4)),np.full((2,2,3),np.nan)]:
            with self.assertRaises(ValueError):validate_linear_input(bad)

    def test_generic_profile_honestly_reports_estimation(self):
        m={'Make':'Canon','Model':'Canon EOS R6m2'}
        e=source_exposure(m,'.cr3');self.assertEqual(e['gain'],1)
        d=normalization_details(m,'.cr3',{**e,'reference_matched':True})
        self.assertEqual(d['profile'],'generic-libraw')
        self.assertFalse(d['fuji_color_calibrated'])
        self.assertIn('preview',d['exposure_method'])
        self.assertFalse(d['embedded_pixels_used_in_output'])

    def test_multibrand_discovery_does_not_accept_rendered_jpegs(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ['a.CR3','b.NEF','c.ARW','d.RW2','e.ORF','f.RAF','g.DNG','h.JPG']:
                (Path(root)/name).write_bytes(b'test fixture')
            files=Library([root],root).select_folder(root)['files']
            self.assertEqual({r['format'] for r in files},{'CR3','NEF','ARW','RW2','ORF','RAF','DNG'})
