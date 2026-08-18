import tempfile
import unittest
from types import SimpleNamespace

from etl.state import changed_documents, load_state, record_documents


class TestEtlState(unittest.TestCase):
    def test_manifest_skips_unchanged_document(self):
        document = SimpleNamespace(source="https://example.test/a", content_hash="abc", title="A")
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/state.json"
            state = load_state(path)
            self.assertEqual(changed_documents([document], state, "example"), [document])
            record_documents([document], state, "example", path)
            reloaded = load_state(path)
            self.assertEqual(changed_documents([document], reloaded, "example"), [])
