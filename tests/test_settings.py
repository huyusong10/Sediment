from __future__ import annotations

from pathlib import Path

from sediment.settings import clear_settings_cache, load_settings_for_path


def test_environment_overrides_server_host_port_and_kb_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "sediment" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        (
            "server:\n"
            "  host: 0.0.0.0\n"
            "  port: 8000\n"
            "paths:\n"
            "  knowledge_base: knowledge-base\n"
        ),
        encoding="utf-8",
    )

    override_kb = project_root / "benchmark-kb"
    monkeypatch.setenv("SEDIMENT_HOST", "127.0.0.1")
    monkeypatch.setenv("SEDIMENT_PORT", "18800")
    monkeypatch.setenv("SEDIMENT_KB_PATH", str(override_kb))
    clear_settings_cache()

    settings = load_settings_for_path(config_path, argv=[])

    assert settings["server"]["host"] == "127.0.0.1"
    assert settings["server"]["port"] == 18800
    assert settings["paths"]["knowledge_base"] == override_kb.resolve()


def test_environment_overrides_invalidate_settings_cache(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "sediment" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("server:\n  port: 8000\n", encoding="utf-8")

    monkeypatch.setenv("SEDIMENT_PORT", "18800")
    clear_settings_cache()
    first = load_settings_for_path(config_path, argv=[])
    assert first["server"]["port"] == 18800

    monkeypatch.setenv("SEDIMENT_PORT", "18801")
    second = load_settings_for_path(config_path, argv=[])
    assert second["server"]["port"] == 18801
