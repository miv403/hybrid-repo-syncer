import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from hybrid_syncer.errors import ManifestError, RepoAccessError
from hybrid_syncer.temp_manager import TempRepoCache, get_repo_path


class TestTempRepoCache(unittest.TestCase):

    def test_missing_repo_url_raises_manifest_error(self):
        cache = TempRepoCache()
        with self.assertRaises(ManifestError):
            cache.get_repo_path("")

    def test_missing_local_repo_raises_repo_access_error(self):
        cache = TempRepoCache()
        with self.assertRaises(RepoAccessError):
            cache.get_repo_path("/nonexistent/local/path/repo.git")

    def test_existing_local_repo_returns_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache = TempRepoCache()
            res = cache.get_repo_path(tmp_dir)
            self.assertEqual(res, Path(tmp_dir))

    @patch("hybrid_syncer.git_utils.run_git")
    def test_context_manager_cleanup(self, mock_run_git):
        mock_run_git.return_value = (0, "", "")
        remote_url = "https://example.com/repo.git"

        created_path = None
        with TempRepoCache() as cache:
            p = cache.get_repo_path(remote_url)
            created_path = p
            self.assertTrue(p.exists())
            self.assertIn(remote_url, cache)
            # Ensure return cached path on subsequent calls
            self.assertEqual(cache.get_repo_path(remote_url), p)

        # Outside with block, temporary dir should be cleaned up automatically
        self.assertFalse(created_path.exists())

    @patch("hybrid_syncer.git_utils.run_git")
    def test_reentrant_nested_context(self, mock_run_git):
        mock_run_git.return_value = (0, "", "")
        remote_url = "https://example.com/repo.git"

        created_path = None
        with TempRepoCache() as cache:
            with cache:
                p = cache.get_repo_path(remote_url)
                created_path = p
                self.assertTrue(p.exists())
            # Exiting inner context should NOT delete while outer context is active
            self.assertTrue(created_path.exists())

        # Exiting outer context cleans up
        self.assertFalse(created_path.exists())


if __name__ == "__main__":
    unittest.main()
