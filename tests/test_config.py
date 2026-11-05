import pytest
from hydra_orch.config import load_config, HydraConfig


def test_load_default_config():
    config = load_config()
    assert isinstance(config, HydraConfig)
    assert config.server.port == 8000
    assert config.orchestrator.default_mode in ("relay", "swarm", "persistent")
    assert "claude_pro" in config.providers.ui_cdp
    assert config.providers.ui_cdp["claude_pro"].cdp_port == 9222
