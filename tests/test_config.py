from mi_fitness_mcp.config import Config, load_config, save_config


def test_config_roundtrip(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("mi_fitness_mcp.config.get_config_path", lambda: config_file)

    config = Config(mode="mi_fitness_cloud", region="ru")
    save_config(config)
    loaded = load_config()

    assert loaded.mode == "mi_fitness_cloud"
    assert loaded.region == "ru"
    assert loaded.database_path.name == "mi_fitness.db"
