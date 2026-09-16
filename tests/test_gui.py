from fuji_recipe_lab.official_luts import missing_luts
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from fuji_recipe_lab.gui import Handler, Library, STATIC, TileRequest, bind_studio_server, output_geometry
from fuji_recipe_lab.studio import StudioRecipe


class StaticGuiTests(unittest.TestCase):
    def test_product_name_batch_selection_and_film_chrome_are_visible(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        page=(STATIC/'index.html').read_text(encoding='utf-8')
        style=(STATIC/'style.css').read_text(encoding='utf-8')
        self.assertIn('<title>Film Recipe Lab</title>',page)
        self.assertIn('FILM RECIPE LAB',page)
        self.assertNotIn('One photograph. A thousand nuances.',page)
        self.assertIn('class="film-edge film-edge-top"',page)
        self.assertIn('const selectedIds = new Set(), recipesById = new Map();',script)
        self.assertIn('applyPatchToSelection',script)
        self.assertIn('/api/export-batch',script)
        self.assertIn('/api/thumbnail/',script)
        self.assertIn('id="selection-clear"',page)
        self.assertIn('id="activity-bar"',page)
        for edge in ('data-resize="left"','data-resize="right"','data-resize="top"','data-resize="bottom"'):
            self.assertIn(edge,page)
        self.assertIn('beginActivity();',script)
        self.assertIn('localStorage.setItem("film-view-layout"',script)
        self.assertIn('.activity-bar',style)
        self.assertIn('.panel-resizer',style)
        self.assertIn('strip-active-badge',style)
        self.assertIn('.strip-entry.batch-selected',style)

    def test_full_resolution_view_preserves_ratio_without_transforming_60mp_bitmap(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        page=(STATIC/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="detail-layer"',page)
        self.assertIn('const geometry=outputGeometry(),displayWidth=geometry.width*viewScale,displayHeight=geometry.height*viewScale;',script)
        self.assertIn('photo.style.width=displayWidth+"px";photo.style.height=displayHeight+"px";',script)
        self.assertIn('/api/tile',script)
        self.assertIn('SOURCE-RESOLUTION DETAIL',script)
        self.assertIn('image.dataset.x=x;image.dataset.y=y;image.dataset.width=width;image.dataset.height=height',script)
        self.assertIn('layoutDetailTiles();',script)
        self.assertIn('if(delay<=0){refreshVisibleTiles();return;}',script)
        self.assertIn('zoomMode=next;updateView(0);',script)
        self.assertIn('function detailLevel()',script)
        self.assertIn('level:tileLevel',script)
        self.assertNotIn('viewScale<1',script)
        self.assertNotIn('queueRender("full")',script)
        self.assertNotIn('scale(${viewScale})',script)

    def test_four_way_tone_controls_and_interactive_preview_are_wired(self):
        script=(STATIC/'app.js').read_text(encoding='utf-8')
        for control in ('Highlights","highlights"','Whites","whites"',
                        'Shadows","shadows"','Blacks","blacks"'):
            self.assertIn(control,script)
        self.assertIn('SCREEN-QUALITY PREVIEW',script)
        self.assertIn('body:JSON.stringify({id,recipe:settings,quality:"interactive"})',script)
        self.assertIn('renderController?.abort()',script)


class GuiServerTests(unittest.TestCase):
    def test_source_resolution_tile_uses_full_decode_context_and_cache(self):
        from unittest.mock import patch
        import numpy as np
        path=Path(self.scratch.name)/'tile.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        pixels=np.random.default_rng(4).uniform(0,.8,(360,540,3)).astype(np.float32)
        self.server.library.linear_cache[item['id']]=pixels
        request=TileRequest(id=item['id'],recipe=StudioRecipe(noise_reduction=-4),x=128,y=128,size=128)
        observed=[]
        def renderer(region,recipe,**kwargs):
            observed.append((region.shape,kwargs))
            return region
        with patch('fuji_recipe_lab.gui.render',side_effect=renderer), \
             patch('fuji_recipe_lab.gui.encode',side_effect=lambda tile,*args,**kwargs:(tile.shape,'image/jpeg')) as encoder:
            shape,mime=self.server.library.render_tile(request)
            again=self.server.library.render_tile(request)
        self.assertEqual((shape,mime),((128,128,3),'image/jpeg'))
        self.assertEqual(again,(shape,mime))
        self.assertEqual(len(observed),1)
        self.assertFalse(observed[0][1]['output_transform'])
        self.assertEqual(observed[0][1]['context']['full_shape'],pixels.shape)
        self.assertEqual(encoder.call_count,1)

        level_two=TileRequest(id=item['id'],recipe=StudioRecipe(noise_reduction=-4),x=128,y=128,size=128,level=2)
        with patch('fuji_recipe_lab.gui.render',side_effect=lambda region,*args,**kwargs:region), \
             patch('fuji_recipe_lab.gui.encode',side_effect=lambda tile,*args,**kwargs:(tile.shape,'image/jpeg')):
            shape,mime=self.server.library.render_tile(level_two)
        self.assertEqual((shape,mime),((116,128,3),'image/jpeg'))

    def test_output_geometry_matches_crop_and_size_controls(self):
        geometry=output_geometry((4000,6000,3),StudioRecipe(digital_crop=2,aspect='1:1',image_size='M'))
        self.assertEqual(geometry['source'],(2000,1000,2000,2000))
        self.assertEqual(geometry['output'],(1414,1414))

    def test_carousel_thumbnail_endpoint_uses_small_preview_cache(self):
        path=Path(self.scratch.name)/'thumbnail.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        self.server.library.thumbnails[item['id']]=b'small-jpeg-preview'
        code,data=self.request('/api/thumbnail/'+item['id'])
        self.assertEqual((code,data),(200,b'small-jpeg-preview'))
        self.assertEqual(self.request('/api/thumbnail/missing')[0],404)

    def test_batch_export_uses_each_photo_recipe_and_returns_zip(self):
        from unittest.mock import patch
        first=Path(self.scratch.name)/'first.DNG';first.write_bytes(b'first')
        second=Path(self.scratch.name)/'second.RAF';second.write_bytes(b'second')
        a=self.server.library.add(first);b=self.server.library.add(second)
        observed=[]

        def develop(request,export=False):
            self.assertTrue(export)
            observed.append((request.id,request.recipe.exposure))
            return f'{request.id}:{request.recipe.exposure}'.encode(),'image/jpeg'

        body=json.dumps({'items':[
            {'id':a['id'],'recipe':{'exposure':-1,'file_type':'jpeg'}},
            {'id':b['id'],'recipe':{'exposure':1,'file_type':'jpeg'}},
        ]})
        with patch.object(Library,'develop',side_effect=develop):
            code,data=self.request('/api/export-batch','POST',body)
        self.assertEqual(code,200)
        with zipfile.ZipFile(__import__('io').BytesIO(data)) as archive:
            self.assertEqual(len(archive.namelist()),2)
            payloads=[archive.read(name) for name in archive.namelist()]
        self.assertEqual(observed,[(a['id'],-1.0),(b['id'],1.0)])
        self.assertNotEqual(payloads[0],payloads[1])
        self.assertFalse(list(Path(self.scratch.name).glob('film-recipe-lab-*.zip')))

    def test_batch_export_rejects_non_jpeg_and_duplicate_photos(self):
        path=Path(self.scratch.name)/'batch.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        tiff=json.dumps({'items':[{'id':item['id'],'recipe':{'file_type':'tiff8'}},{'id':'missing','recipe':{}}]})
        duplicate=json.dumps({'items':[{'id':item['id'],'recipe':{}},{'id':item['id'],'recipe':{}}]})
        self.assertEqual(self.request('/api/export-batch','POST',tiff)[0],422)
        self.assertEqual(self.request('/api/export-batch','POST',duplicate)[0],422)

    def test_optics_are_applied_to_preview_and_export_without_mutating_cache(self):
        from unittest.mock import patch
        import numpy as np
        from fuji_recipe_lab.gui import RenderRequest
        from fuji_recipe_lab.studio import StudioRecipe
        from fuji_recipe_lab.optics import apply_corrections
        path=Path(self.scratch.name)/'geometry.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        a=np.random.default_rng(10).uniform(0,3,(48,64,3)).astype(np.float32)
        saved=a.copy()
        profile={'orientation':1,'source':'dng-warp','distortion':True,
                 'warp':{'center':[.5,.5],'coefficients':[1,-.1,0,0,0,0]}}
        expected=apply_corrections(a,profile,'auto')
        request=RenderRequest(id=item['id'],recipe=StudioRecipe(lens_distortion='auto'))
        with patch('fuji_recipe_lab.optics.inspect_optics',return_value=profile), \
             patch('fuji_recipe_lab.gui.decode',return_value=a.copy()) as decoder, \
             patch('fuji_recipe_lab.gui.render',side_effect=lambda pixels,*args,**kwargs:pixels) as renderer, \
             patch('fuji_recipe_lab.gui.encode',return_value=(b'encoded','image/jpeg')):
            for export in (False,True):
                self.server.library.develop(request,export=export)
                np.testing.assert_allclose(renderer.call_args.args[0],expected)
        self.assertEqual([call.kwargs["preview"] for call in decoder.call_args_list],[False])
        np.testing.assert_array_equal(self.server.library.linear_cache[item['id']],saved)
        np.testing.assert_array_equal(a,saved)

    def test_interactive_preview_uses_reduced_decode_without_filling_full_cache(self):
        from unittest.mock import patch
        import numpy as np
        from fuji_recipe_lab.gui import RenderRequest
        from fuji_recipe_lab.studio import StudioRecipe
        path=Path(self.scratch.name)/'fast.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path);pixels=np.ones((32,48,3),np.float32)
        request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='interactive')
        with patch('fuji_recipe_lab.gui.decode',return_value=pixels) as decoder, \
             patch('fuji_recipe_lab.gui.render',side_effect=lambda *args,**kwargs:self._assert_decoder_released(pixels)), \
             patch('fuji_recipe_lab.gui.encode',return_value=(b'preview','image/jpeg')):
            self.server.library.develop(request)
        decoder.assert_called_once_with(Path(item['path']),preview=True)
        self.assertNotIn(item['id'],self.server.library.linear_cache)

    def _assert_decoder_released(self, pixels):
        acquired=self.server.library.decoder_lock.acquire(blocking=False)
        self.assertTrue(acquired,"The LibRaw lock must not cover rendering")
        if acquired:self.server.library.decoder_lock.release()
        return pixels

    def test_interactive_edit_overtakes_full_resolution_render(self):
        from unittest.mock import patch
        import numpy as np
        from fuji_recipe_lab.gui import RenderRequest
        from fuji_recipe_lab.studio import StudioRecipe
        path=Path(self.scratch.name)/'overtake.DNG';path.write_bytes(b'fixture')
        item=self.server.library.add(path)
        full=np.ones((64,96,3),np.float32)
        reduced=np.full((24,36,3),.5,np.float32)
        self.server.library.linear_cache[item['id']]=full
        started=threading.Event();release=threading.Event();interactive_done=threading.Event()

        def renderer(pixels,*args,**kwargs):
            if pixels is full:
                started.set();self.assertTrue(release.wait(2))
            else:
                interactive_done.set()
            return pixels

        full_request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='full')
        quick_request=RenderRequest(id=item['id'],recipe=StudioRecipe(),quality='interactive')
        with patch('fuji_recipe_lab.gui.decode',return_value=reduced), \
             patch('fuji_recipe_lab.gui.render',side_effect=renderer), \
             patch('fuji_recipe_lab.gui.encode',return_value=(b'image','image/jpeg')):
            worker=threading.Thread(target=self.server.library.develop,args=(full_request,))
            worker.start();self.assertTrue(started.wait(1))
            quick=threading.Thread(target=self.server.library.develop,args=(quick_request,))
            quick.start();self.assertTrue(interactive_done.wait(1))
            release.set();quick.join(1);worker.join(1)
        self.assertFalse(quick.is_alive());self.assertFalse(worker.is_alive())

    def test_startup_uses_folder_shortcuts_without_scanning_photos(self):
        root=Path(self.scratch.name)
        (root/'photo.DNG').write_bytes(b'fixture')
        library=Library([root],root)
        self.assertEqual(library.listing(),[])
        browser=library.folders()
        self.assertEqual(browser['path'],str(root.resolve()))
        self.assertIn(str(root.resolve()),[item['path'] for item in browser['shortcuts']])
        self.assertEqual(browser['raw_count'],1)
        self.assertEqual(browser['breadcrumbs'][-1]['path'],str(root.resolve()))
        self.assertEqual(library.listing(),[])

    def test_folder_rejects_malformed_input_and_cross_origin_access(self):
        for body in ('[]','null','{"path":""}','{"path":2}','{"path":"/","recursive":1}'):
            with self.subTest(body=body):
                self.assertEqual(self.request('/api/folder','POST',body)[0],422)
        self.assertEqual(self.request('/api/folder','POST','{}',{'Origin':'https://untrusted.example'})[0],403)
        self.assertEqual(self.request('/api/folders',headers={'X-Fuji-Session':''})[0],403)

    def test_busy_port_uses_another_loopback_port(self):
        other = bind_studio_server(self.server.server_port)
        try:
            self.assertNotEqual(other.server_port, self.server.server_port)
            self.assertEqual(other.server_address[0], '127.0.0.1')
        finally:
            other.server_close()

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.session_token = "unit-test-session"
        self.server.library = Library([], self.scratch.name)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.scratch.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        client.request(method, path, body, {"X-Fuji-Session": self.server.session_token, **(headers or {})})
        response = client.getresponse()
        code, data = response.status, response.read()
        client.close()
        return code, json.loads(data) if response.getheader("Content-Type", "").startswith("application/json") else data

    def test_library_is_private_to_local_session(self):
        for headers in [{"X-Fuji-Session": "wrong"}, {"Origin": "https://untrusted.example"}, {"Host": "untrusted.example"}]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/library", headers=headers)[0], 403)
        code, data = self.request("/api/library")
        self.assertEqual(code, 200)
        self.assertEqual(data["files"], [])
        self.assertTrue(data["engine"]["available"])
        self.assertFalse(data["engine"]["exact_fuji_render"])

    def test_recipe_roundtrip_and_invalid_input(self):
        code, data = self.request("/api/recipe", "POST", json.dumps({"name": "Test", "film": "acros", "highlights": -37, "whites": -12, "wb_red": 2}))
        self.assertEqual(code, 200)
        self.assertEqual(data["recipe"]["film"], "acros")
        self.assertEqual((data["recipe"]["highlights"],data["recipe"]["whites"]),(-37,-12))
        self.assertTrue(data["render_available"])
        self.assertEqual(self.request("/api/recipe", "POST", '{"unknown": 1}')[0], 422)

    def test_render_requires_valid_photo_and_recipe(self):
        self.assertEqual(self.request("/api/render", "POST", "{}")[0], 422)
        self.assertEqual(list(Path(self.scratch.name).iterdir()), [])

    def test_import_is_confined_to_generated_directory(self):
        self.assertEqual(self.request("/api/import?name=photo.jpg", "POST", "not-raw")[0], 415)
        code, data = self.request("/api/import?name=..%2F..%2Fexample.RAF", "POST", "synthetic-unit-test")
        self.assertEqual(code, 201)
        path = Path(data["path"])
        self.assertTrue(path.is_relative_to(Path(self.scratch.name).resolve()))
        self.assertEqual(path.name, "example.RAF")
        self.assertEqual(path.read_text(), "synthetic-unit-test")
        self.assertEqual(self.request("/api/import?name=large.RAF", "POST", "", {"Content-Length": str(201*1024*1024)})[0], 413)

    def test_lut_archive_is_verified_locally_then_deleted(self):
        from unittest.mock import patch
        observed=[]
        def install(path):
            self.assertTrue(path.is_file())
            self.assertTrue(path.resolve().is_relative_to(Path(self.scratch.name).resolve()))
            self.assertEqual(path.read_bytes(),b'synthetic ZIP fixture')
            observed.append(path)
        engine={'missing_luts':[]}
        with patch('fuji_recipe_lab.gui.install_archive',side_effect=install), \
             patch('fuji_recipe_lab.gui.studio_status',return_value=engine):
            code,data=self.request('/api/luts/install?name=official.zip','POST',b'synthetic ZIP fixture',
                                   {'Content-Type':'application/zip'})
        self.assertEqual(code,201)
        self.assertTrue(data['installed'])
        self.assertEqual(data['engine'],engine)
        self.assertEqual(len(observed),1)
        self.assertFalse(observed[0].exists())
        self.assertEqual(self.request('/api/luts/install?name=profile.cube','POST',b'not a zip')[0],415)

    def test_lut_folder_installation(self):
        from unittest.mock import patch
        folder = Path(self.scratch.name)/'extracted-luts'
        folder.mkdir()
        with patch('fuji_recipe_lab.gui.install_archive') as install, patch('fuji_recipe_lab.gui.studio_status', return_value={'missing_luts':[]}):
            code, data = self.request('/api/luts/install', 'POST', json.dumps({'path':str(folder)}), {'Content-Type':'application/json'})
        self.assertEqual(code, 201)
        self.assertTrue(data['installed'])
        install.assert_called_once_with(folder)
        self.assertTrue(folder.exists())

    def test_folder_selection_reads_originals_without_copying(self):
        root=Path(self.scratch.name).resolve()/"photos";root.mkdir()
        (root/"a.CR3").write_bytes(b"raw fixture")
        (root/"b.jpg").write_bytes(b"jpeg fixture")
        sub=root/"sub";sub.mkdir();(sub/"c.DNG").write_bytes(b"dng fixture")
        from urllib.parse import quote
        code,data=self.request("/api/folders?path="+quote(str(root)))
        self.assertEqual(code,200)
        self.assertEqual(data["folders"],[{"name":"sub","path":str(sub)}])
        self.assertEqual(data["raw_count"],1)
        self.assertEqual(data["breadcrumbs"][-1],[{"name":"photos","path":str(root)}][0])
        for recursive,count in [(False,1),(True,2)]:
            code,data=self.request("/api/folder","POST",json.dumps({"path":str(root),"recursive":recursive}))
            self.assertEqual(code,200);self.assertEqual(len(data["files"]),count)
            self.assertEqual(data["files"][0]["path"],str(root/"a.CR3"))
        self.assertEqual(len(list(root.rglob("*"))),4)
        self.assertEqual(self.request("/api/folder","POST",json.dumps({"path":str(root),"recursive":"false"}))[0],422)
        self.assertEqual(self.request("/api/folders?path="+quote(str(root)),headers={"X-Fuji-Session":"wrong"})[0],403)

    @unittest.skipIf(missing_luts(), "Official LUT integration: install Fuji assets separately")
    def test_render_endpoint_applies_recipe_to_cached_raw_pixels(self):
        import numpy as np
        from PIL import Image
        from io import BytesIO
        path=Path(self.scratch.name)/"cached.DNG"
        path.write_bytes(b"test fixture; decoder output injected below")
        item=self.server.library.add(path)
        self.server.library.linear_cache[item["id"]]=np.full((32,48,3),.15,dtype=np.float32)
        images=[]
        for exposure in [0,1]:
            code,data=self.request("/api/render","POST",json.dumps({"id":item["id"],"recipe":{"exposure":exposure}}))
            self.assertEqual(code,200)
            images.append(np.asarray(Image.open(BytesIO(data))).astype(float))
        self.assertGreater(images[1].mean(),images[0].mean()+20)
