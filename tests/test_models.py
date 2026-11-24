"""Offline tests for model-cache detection, using a fake Hugging Face cache on disk.

    python -m unittest discover tests
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voicenote.config import Config
from voicenote.models import ModelNotAvailable, is_cached, require

REPO = "someone/tiny-model"


def make_cache(root: Path, files: dict[str, bytes], repo: str = REPO) -> None:
    """Build a minimal HF cache layout: blobs/ + snapshots/<rev>/ symlinks + refs/main."""
    repo_dir = root / f"models--{repo.replace('/', '--')}"
    rev = "abc123"
    (repo_dir / "refs").mkdir(parents=True)
    (repo_dir / "refs" / "main").write_text(rev)
    snap = repo_dir / "snapshots" / rev
    snap.mkdir(parents=True)
    (repo_dir / "blobs").mkdir()
    for name, data in files.items():
        blob = repo_dir / "blobs" / f"blob-{name}"
        blob.write_bytes(data)
        (snap / name).symlink_to(blob)


class IsCachedTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_complete_model(self):
        make_cache(self.root, {"config.json": b"{}", "model.safetensors": b"x"})
        self.assertTrue(is_cached(REPO, cache_dir=self.root))

    def test_npz_weights_count(self):  # mlx-whisper style
        make_cache(self.root, {"config.json": b"{}", "weights.npz": b"x"})
        self.assertTrue(is_cached(REPO, cache_dir=self.root))

    def test_missing_readme_is_fine(self):
        # Regression: mlx-lm never downloads README.md/.gitattributes; that must not matter.
        make_cache(self.root, {"config.json": b"{}", "model.safetensors": b"x", "tokenizer.json": b"{}"})
        self.assertTrue(is_cached(REPO, cache_dir=self.root))

    def test_not_downloaded(self):
        self.assertFalse(is_cached(REPO, cache_dir=self.root))

    def test_config_without_weights(self):
        make_cache(self.root, {"config.json": b"{}"})
        self.assertFalse(is_cached(REPO, cache_dir=self.root))

    def test_broken_weight_symlink_does_not_count(self):
        make_cache(self.root, {"config.json": b"{}", "model.safetensors": b"x"})
        (self.root / f"models--{REPO.replace('/', '--')}" / "blobs" / "blob-model.safetensors").unlink()
        self.assertFalse(is_cached(REPO, cache_dir=self.root))

    def test_local_directory_counts(self):
        self.assertTrue(is_cached(str(self.root)))


class RequireTests(unittest.TestCase):
    def _config(self, offline: bool) -> Config:
        return Config(
            sample_rate=16000,
            input_device=None,
            data_dir=Path("data"),
            transcription_backend="mlx-whisper",
            transcription_model="nobody/does-not-exist-whisper",
            transcription_language=None,
            offline=offline,
        )

    def test_offline_and_missing_raises_with_setup_hint(self):
        with self.assertRaises(ModelNotAvailable) as ctx:
            require(self._config(offline=True), "transcription")
        self.assertIn("python -m voicenote setup", str(ctx.exception))

    def test_online_mode_never_raises(self):
        require(self._config(offline=False), "transcription")  # would download on demand


if __name__ == "__main__":
    unittest.main()
