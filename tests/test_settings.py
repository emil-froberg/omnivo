"""Tests for core/settings.py — persistent CLI settings."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_state(monkeypatch):
    """Redirect STATE_PATH to a temp file for the duration of the test."""
    tmp_dir = tempfile.mkdtemp(prefix="omnivo_settings_test_")
    tmp_path = os.path.join(tmp_dir, "state.json")
    monkeypatch.setattr("utils.config.STATE_PATH", tmp_path)
    # core.settings imports STATE_PATH at module-level, so patch it there too
    import core.settings

    monkeypatch.setattr(core.settings, "STATE_PATH", tmp_path)
    yield tmp_path
    # Cleanup
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    os.rmdir(tmp_dir)


class TestLoadSettings:
    def test_returns_defaults_when_file_missing(self, tmp_state):
        from core.settings import load_settings

        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_file_is_empty(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            f.write("")
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_file_is_invalid_json(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            f.write("{not valid json")
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_schema_is_wrong_type(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            f.write('"a string, not a dict"')
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_unknown_model_value_falls_back_to_default(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            json.dump({"model": "bogus", "punctuation": True}, f)
        assert load_settings() == {"model": "whisper", "punctuation": True}

    def test_non_bool_punctuation_falls_back_to_default(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            json.dump({"model": "transcribe", "punctuation": "yes"}, f)
        assert load_settings() == {"model": "transcribe", "punctuation": False}

    def test_loads_valid_settings(self, tmp_state):
        from core.settings import load_settings

        with open(tmp_state, "w") as f:
            json.dump({"model": "transcribe", "punctuation": True}, f)
        assert load_settings() == {"model": "transcribe", "punctuation": True}


class TestSaveSettings:
    def test_creates_file_with_partial_update(self, tmp_state):
        from core.settings import save_settings, load_settings

        save_settings(model="transcribe")
        # punctuation should be the default since we didn't pass it
        assert load_settings() == {"model": "transcribe", "punctuation": False}

    def test_partial_update_preserves_other_field(self, tmp_state):
        from core.settings import save_settings, load_settings

        save_settings(model="transcribe", punctuation=True)
        save_settings(model="whisper")  # only update model
        assert load_settings() == {"model": "whisper", "punctuation": True}

    def test_round_trip(self, tmp_state):
        from core.settings import save_settings, load_settings

        save_settings(model="transcribe", punctuation=True)
        assert load_settings() == {"model": "transcribe", "punctuation": True}

    def test_returns_new_settings_dict(self, tmp_state):
        from core.settings import save_settings

        result = save_settings(model="transcribe", punctuation=True)
        assert result == {"model": "transcribe", "punctuation": True}

    def test_rejects_invalid_model(self, tmp_state):
        from core.settings import save_settings

        with pytest.raises(ValueError, match="model"):
            save_settings(model="bogus")

    def test_rejects_non_bool_punctuation(self, tmp_state):
        from core.settings import save_settings

        with pytest.raises(ValueError, match="punctuation"):
            save_settings(punctuation="yes")

    def test_creates_parent_directory_if_missing(self, monkeypatch):
        """If ~/.omnivo doesn't exist, save_settings should create it."""
        tmp_root = tempfile.mkdtemp(prefix="omnivo_settings_test_")
        # Point STATE_PATH at a nested path whose parent doesn't exist yet
        nested_path = os.path.join(tmp_root, "nested", "state.json")
        monkeypatch.setattr("utils.config.STATE_PATH", nested_path)
        import core.settings

        monkeypatch.setattr(core.settings, "STATE_PATH", nested_path)

        from core.settings import save_settings

        save_settings(model="transcribe")

        assert os.path.exists(nested_path)

        # cleanup
        os.remove(nested_path)
        os.rmdir(os.path.dirname(nested_path))
        os.rmdir(tmp_root)

    def test_atomic_write_via_temp_file(self, tmp_state):
        """Verify the temp-file convention: no leftover .tmp file after a successful save."""
        from core.settings import save_settings

        save_settings(model="transcribe")
        assert not os.path.exists(f"{tmp_state}.tmp")
