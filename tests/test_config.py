from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squat_ai_mvp.core.config import AppConfig, ConfigError, load_config, load_yaml


class TestAppConfig:
    def test_properties(self):
        cfg = AppConfig(
            raw={
                "session": {"exercise": "squat"},
                "stream": {"input_url": "rtsp://..."},
                "perception": {"backend": "mediapipe"},
                "biomechanics": {"rules_file": "rules/squat.side.yaml"},
                "alert": {"tts_provider": "print"},
                "ui": {"enabled": True},
            },
            root_dir=Path("/tmp"),
        )
        assert cfg.session["exercise"] == "squat"
        assert cfg.stream["input_url"] == "rtsp://..."
        assert cfg.perception["backend"] == "mediapipe"
        assert cfg.biomechanics["rules_file"] == "rules/squat.side.yaml"
        assert cfg.alert["tts_provider"] == "print"
        assert cfg.ui["enabled"] == True

    def test_empty_config(self):
        cfg = AppConfig(raw={}, root_dir=Path("/tmp"))
        assert cfg.session == {}
        assert cfg.stream == {}
        assert cfg.perception == {}

    def test_resolve_path_relative(self):
        cfg = AppConfig(raw={}, root_dir=Path("/project"))
        resolved = cfg.resolve_path("configs/app.yaml")
        assert resolved == Path("/project/configs/app.yaml").resolve()

    def test_resolve_path_absolute(self):
        cfg = AppConfig(raw={}, root_dir=Path("/project"))
        resolved = cfg.resolve_path("/etc/app.yaml")
        assert resolved == Path("/etc/app.yaml")


class TestLoadConfig:
    def test_load_from_file(self, tmp_path: Path):
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        cfg_file = config_dir / "app.yaml"
        cfg_file.write_text(
            "session:\n  exercise: squat\nstream:\n  input_url: rtsp://test\n",
            encoding="utf-8",
        )
        cfg = load_config(cfg_file)
        assert cfg.session["exercise"] == "squat"
        assert cfg.stream["input_url"] == "rtsp://test"

    def test_file_not_found(self):
        with pytest.raises(ConfigError, match="does not exist"):
            load_config("/nonexistent/config.yaml")

    def test_invalid_yaml(self, tmp_path: Path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text(": broken yaml [\n", encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            load_config(cfg_file)

    def test_non_dict_config(self, tmp_path: Path):
        cfg_file = tmp_path / "list.yaml"
        cfg_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="YAML mapping"):
            load_config(cfg_file)

    def test_root_dir_detection(self, tmp_path: Path):
        """When config is in configs/, root_dir should be parent of configs"""
        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        cfg_file = config_dir / "app.yaml"
        cfg_file.write_text("session:\n  exercise: squat\n", encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg.root_dir == tmp_path.resolve()


class TestLoadYaml:
    def test_load_valid(self, tmp_path: Path):
        f = tmp_path / "rules.yaml"
        f.write_text("exercise: squat\nphases:\n  up_angle: 155\n", encoding="utf-8")
        data = load_yaml(f)
        assert data["exercise"] == "squat"
        assert data["phases"]["up_angle"] == 155

    def test_file_not_found(self):
        with pytest.raises(ConfigError, match="does not exist"):
            load_yaml("/nonexistent.yaml")

    def test_non_dict_yaml(self, tmp_path: Path):
        f = tmp_path / "list.yaml"
        f.write_text("[1, 2, 3]\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="YAML root must be a mapping"):
            load_yaml(f)
