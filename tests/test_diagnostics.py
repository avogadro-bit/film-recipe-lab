import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fuji_recipe_lab import diagnostics as d
from fuji_recipe_lab.gui import TileRequest


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'errors.jsonl'
        self.patch = patch.object(d, 'log_path', return_value=self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def events(self):
        return [json.loads(line) for line in self.path.read_text().splitlines()]

    def test_redacts_tokens_paths_and_drops_payloads(self):
        d.register_secret('secret-test-token')
        d.record_error('zoom', message='secret-test-token /private/diagnostic-fixture/My Photos/test.DNG',
                       context={'photo_id':'abc', 'zoom':4, 'recipe':{'name':'private'}, 'path':'secret'})
        text = self.path.read_text()
        self.assertNotIn('secret-test-token', text)
        self.assertNotIn('/private/diagnostic-fixture', text)
        self.assertNotIn('test.DNG', text)
        self.assertNotIn('recipe', text)
        self.assertEqual(self.events()[0]['context']['zoom'],4)

    def test_validation_errors_exclude_input(self):
        try:
            TileRequest.model_validate({'private':'my confidential recipe'})
        except Exception as exc:
            d.record_error('validate', exc)
        self.assertNotIn('my confidential recipe',self.path.read_text())

    def test_exception_frames_without_local_values(self):
        secret_local='never-log-me'
        try: raise RuntimeError('test')
        except Exception as exc: d.record_error('render',exc)
        self.assertTrue(self.events()[0]['frames'])
        self.assertNotIn(secret_local,self.path.read_text())

    def test_concurrent_writers_and_rotation(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i:d.record_error('test',message=str(i)),range(40)))
        self.assertEqual(len(self.events()),40)
        with patch.object(d,'MAX_BYTES',1200):
            for i in range(15): d.record_error('test',message='x'*500)
        self.assertLessEqual(len(list(Path(self.temp.name).glob('errors*.jsonl'))),4)
        for path in Path(self.temp.name).glob('errors*.jsonl'):
            for line in path.read_text().splitlines(): json.loads(line)

    def test_failure_to_write_does_not_raise(self):
        with patch.object(Path,'mkdir',side_effect=OSError('disk full')):
            self.assertIsNone(d.record_error('test',message='error'))
