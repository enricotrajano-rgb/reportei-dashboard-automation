import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exporter", ROOT / "Exportação_Oficial.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {"enabled": True, "refresh": False,
                       "ttl_seconds": 168 * 3600, "dir": Path(self.temp.name)}
        self.old = [{"id": 884472, "name": "Canal Rural"}]
        self.new = self.old + [{"id": 1331967, "name": "BR IN TV"}]

    def test_discovers_new_product_despite_valid_cache(self):
        exporter.write_cache(self.config, "projects", self.old)
        client = Mock()
        client.list_projects.return_value = {"data": self.new}
        self.assertEqual(exporter.cached_list_projects(client, self.config), self.new)
        client.list_projects.assert_called_once_with(per_page=100)
        self.assertEqual(exporter.read_cache(self.config, "projects"), self.new)
        self.assertFalse(self.config["refresh"])

    def test_api_failure_preserves_cached_products(self):
        exporter.write_cache(self.config, "projects", self.old)
        client = Mock()
        client.list_projects.side_effect = RuntimeError("API unavailable")
        self.assertEqual(exporter.cached_list_projects(client, self.config), self.old)
        client.list_projects.assert_called_once()

    def test_api_failure_without_cache_is_visible(self):
        client = Mock()
        client.list_projects.side_effect = RuntimeError("API unavailable")
        with self.assertRaisesRegex(RuntimeError, "API unavailable"):
            exporter.cached_list_projects(client, self.config)


if __name__ == "__main__":
    unittest.main()
