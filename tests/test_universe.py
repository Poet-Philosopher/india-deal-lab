from deal_lab.universe import DEFAULT_PRESET, PRESETS, all_tickers


def test_default_preset_exists():
    assert DEFAULT_PRESET in PRESETS


def test_akzo_removed():
    assert "AKZOINDIA.NS" not in all_tickers()
    assert not any("Akzo" in name for name in PRESETS)


def test_every_preset_has_enough_peers_and_no_self_peer():
    for name, cfg in PRESETS.items():
        assert len(cfg["peers"]) >= 3, name
        assert cfg["ticker"] not in cfg["peers"], name
