import struct
import unittest
from unittest.mock import patch
import numpy as np
from fuji_recipe_lab.optics import parse_warp, warp_coordinates, apply_corrections, lensfun_match, database


def opcode(coeff=(1,0,0,0,0,0),center=(.5,.5)):
    payload=struct.pack('>I8d',1,*coeff,*center)
    return struct.pack('>5I',1,1,0x01030000,0,len(payload))+payload


class OpticsTests(unittest.TestCase):
    def test_identity_and_radial_mapping_follow_dng_coordinates(self):
        xy=warp_coordinates(101,81,0,81,parse_warp(opcode()))
        yy,xx=np.mgrid[:81,:101]
        np.testing.assert_allclose(xy[...,0],xx,atol=1e-5)
        np.testing.assert_allclose(xy[...,1],yy,atol=1e-5)
        # At a corner r=1; radial factor .9 maps (0,0) to (5,4).
        warp=parse_warp(opcode((1,-.1,0,0,0,0)))
        np.testing.assert_allclose(warp_coordinates(101,81,0,1,warp)[0,0],[5,4],atol=1e-5)

    def test_invalid_or_unhandled_opcodes_are_rejected(self):
        for b in (b'',opcode()[:-1],opcode()+b'extra',opcode((float('nan'),0,0,0,0,0)),
                  opcode((1,0,0,0,.1,0)),opcode((1,-1,0,0,0,0)),opcode(center=(2,.5))):
            with self.subTest(data=len(b)),self.assertRaises(ValueError):parse_warp(b)

    def test_off_is_bit_exact_and_active_preserves_hdr_and_source(self):
        a=np.random.default_rng(2).uniform(-.1,4,(64,96,3)).astype(np.float32);saved=a.copy()
        profile={'orientation':1,'source':'dng-warp','distortion':True,'vignetting':False,
                 'warp':parse_warp(opcode((1,-.1,0,0,0,0)))}
        self.assertIs(apply_corrections(a,profile),a)
        b=apply_corrections(a,profile,'auto')
        np.testing.assert_array_equal(a,saved)
        self.assertEqual(b.shape,a.shape);self.assertGreater(float(b.max()),1)
        self.assertTrue(np.isfinite(b).all());self.assertGreater(float(abs(b-a).mean()),.1)
        np.testing.assert_allclose(apply_corrections(np.full_like(a,3),profile,'auto'),3)

    def test_portrait_rotation_uses_sensor_axes(self):
        a=np.random.default_rng(1).uniform(0,1,(63,95,3)).astype(np.float32)
        profile={'orientation':1,'source':'dng-warp','distortion':True,
                 'warp':parse_warp(opcode((1,-.1,0,0,0,0),(.4,.55)))}
        expected=apply_corrections(a,profile,'auto')
        for orientation,k in ((3,2),(6,3),(8,1)):
            result=apply_corrections(np.rot90(a,k),{**profile,'orientation':orientation},'auto')
            np.testing.assert_allclose(result,np.rot90(expected,k),atol=1e-6)

    def test_unknown_profile_does_not_guess_or_change_pixels(self):
        a=np.ones((8,9,3),np.float32)
        self.assertIs(apply_corrections(a,{'distortion':False,'vignetting':False},'auto','auto'),a)
        with patch('fuji_recipe_lab.optics.database',return_value=None):
            self.assertIsNone(lensfun_match({'Make':'Unknown','Model':'Unknown'}))

    def test_lensfun_profile_corrects_vignetting_without_clipping_hdr(self):
        if database() is None:self.skipTest('Optional optics dependency absent')
        meta={'Make':'Canon','Model':'Canon EOS R6m2','LensModel':'EF16-35mm f/2.8L III USM'}
        self.assertIsNotNone(lensfun_match(meta))
        profile={'source':'lensfun','orientation':1,'metadata':meta,'distortion':True,
                 'vignetting':True,'focal':26.,'aperture':2.8}
        a=np.full((80,120,3),2.,np.float32)
        b=apply_corrections(a,profile,'auto','auto')
        self.assertGreater(b[0,0,0],b[40,60,0]*1.2)
        self.assertTrue(np.isfinite(b).all());np.testing.assert_array_equal(a,2.)
