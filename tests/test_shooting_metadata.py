import unittest
from fuji_recipe_lab.raw import normalize_exif
from fuji_recipe_lab.studio import shooting_settings,StudioRecipe


class ShootingMetadataTests(unittest.TestCase):
    def test_makernotes_win_over_lossy_standard_exif_in_either_order(self):
        pairs=[('FujiFilm:Sharpness','+1 (medium hard)'),('ExifIFD:Sharpness','Hard'),('FujiFilm:WhiteBalance','Kelvin'),('ExifIFD:WhiteBalance','Manual')]
        for data in (dict(pairs),dict(reversed(pairs))):
            meta=normalize_exif(data)
            self.assertEqual(meta['Sharpness'],'+1 (medium hard)')
            self.assertEqual(meta['WhiteBalance'],'Kelvin')
            self.assertEqual(shooting_settings(meta)['sharpness'],1)

    def test_acros_and_filters_are_read_from_saturation(self):
        for suffix,filter_name in [('', 'none'),(' Red Filter','red'),(' Yellow Filter','yellow'),(' Green Filter','green')]:
            recipe=StudioRecipe(**shooting_settings({'Saturation':'Acros'+suffix,'FilmMode':'Classic Chrome'}))
            self.assertEqual(recipe.film,'acros');self.assertEqual(recipe.mono_filter,filter_name)
            self.assertEqual(recipe.color,0)

    def test_capture_wb_shift_is_not_applied_twice(self):
        r=StudioRecipe(**shooting_settings({'WhiteBalanceFineTune':'Red +40, Blue -80','WhiteBalance':'Kelvin','Saturation':'+4 (highest)','HighlightTone':'-2 (soft)','ShadowTone':-.5}))
        self.assertEqual((r.wb,r.wb_red,r.wb_blue),('camera',0,0))
        self.assertEqual((r.color,r.highlights,r.whites,r.shadows,r.blacks),(4,-50,0,12,0))
