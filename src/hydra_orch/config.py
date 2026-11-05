"""Configuration loading and models for hydra-orch."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    title: str = "Hydra Orchestrator API"
    description: str = "Universal Autonomous LLM Orchestrator"


class ResilienceConfig(BaseModel):
    database_path: str = ".orchestrator/checkpoints.sqlite"
    on_limit_action: str = "hot_handoff"  # 'hot_handoff' or 'auto_resume'
    handoff_fallback_chain: List[str] = Field(
        default_factory=lambda: [
            "claude_pro",
            "chatgpt_plus",
            "deepseek",
            "openrouter",
            "ssh_remote",
            "ollama_local",
        ]
    )
    auto_resume_check_interval_seconds: int = 60


class OrchestratorConfig(BaseModel):
    default_mode: str = "relay"  # 'swarm', 'relay', 'persistent'
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)


class DifficultyConfig(BaseModel):
    max_complexity: int
    preferred_provider: str


class SwarmConfig(BaseModel):
    worktrees_dir: str = ".orchestrator/worktree"
    base_contract_file: str = ".orchestrator/CONTRACT.md"
    auto_merge: bool = True
    run_tests_before_merge: bool = True
    test_command: str = "pytest"
    difficulty_thresholds: Dict[str, DifficultyConfig] = Field(
        default_factory=lambda: {
            "simple": DifficultyConfig(max_complexity=3, preferred_provider="ollama_local"),
            "moderate": DifficultyConfig(max_complexity=7, preferred_provider="deepseek"),
            "complex": DifficultyConfig(max_complexity=10, preferred_provider="claude_pro"),
        }
    )


class CdpProviderConfig(BaseModel):
    enabled: bool = True
    cdp_port: int
    target_url: str
    session_timeout_seconds: int = 300
    rate_limit_reset_hours: float = 5.0


class IdeBridgeConfig(BaseModel):
    enabled: bool = True
    bridge_url: str


class ApiGatewayConfig(BaseModel):
    enabled: bool = True
    base_url: str
    api_key_env: str = ""
    default_model: str = ""

    @property
    def api_key(self) -> Optional[str]:
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None


class RemoteLocalConfig(BaseModel):
    enabled: bool = True
    base_url: Optional[str] = None
    default_model: str = ""
    host: Optional[str] = None
    port: int = 22
    user: Optional[str] = None
    key_file: Optional[str] = None
    remote_port: int = 11434
    local_bind_port: int = 11435
    use_autossh: bool = False


class ProvidersConfig(BaseModel):
    ui_cdp: Dict[str, CdpProviderConfig] = Field(default_factory=dict)
    ide_bridge: Dict[str, IdeBridgeConfig] = Field(default_factory=dict)
    api_gateway: Dict[str, ApiGatewayConfig] = Field(default_factory=dict)
    remote_local: Dict[str, RemoteLocalConfig] = Field(default_factory=dict)


class HydraConfig(BaseModel):
    version: str = "1.0"
    server: ServerConfig = Field(default_factory=ServerConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    swarm: SwarmConfig = Field(default_factory=SwarmConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)


_CONFIG_CACHE: Optional[HydraConfig] = None


def load_config(config_path: Optional[str | Path] = None) -> HydraConfig:
    """Load config from YAML file or return cached config."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and config_path is None:
        return _CONFIG_CACHE

    paths_to_try = []
    if config_path:
        paths_to_try.append(Path(config_path))
    paths_to_try.extend([
        Path("config.yaml"),
        Path("config.yml"),
        Path.home() / ".config" / "hydra-orch" / "config.yaml",
    ])

    for path in paths_to_try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
                cfg = HydraConfig.model_validate(raw_data)
                _CONFIG_CACHE = cfg
                return cfg

    # If no config found, fallback to defaults
    cfg = HydraConfig()
    _CONFIG_CACHE = cfg
    return cfg
