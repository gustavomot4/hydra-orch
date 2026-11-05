"""Configuration loading and models for hydra-orch (v5.0 with OmniRoute & Engine)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class HydraSettings(BaseModel):
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8000
    default_mode: int = 1  # 1: Swarm, 2: Relay, 3: Persistent
    preferred_primary_model: str = "claude-pro"
    worktree_base_dir: str = ".hydra/worktree"
    state_db: str = ".hydra/state.db"
    auto_heal_build_errors: bool = True
    max_heal_attempts: int = 3


class LogicalModelMapping(BaseModel):
    primary: str
    fallbacks: List[str] = Field(default_factory=list)
    min_difficulty: int = 1


class OmniRouteConfig(BaseModel):
    auto_start_daemon: bool = False
    base_url: str = "http://127.0.0.1:20128/v1"
    quota_api_url: str = "http://127.0.0.1:20128/api/usage/quota"
    default_routing_strategy: str = "auto/thrifty"
    logical_models: Dict[str, LogicalModelMapping] = Field(default_factory=dict)


class RemoteSshGpuConfig(BaseModel):
    enabled: bool = False
    ssh_target: str = "usuario@192.168.1.100"
    ssh_port: int = 22
    ssh_key: str = "~/.ssh/id_ed25519"
    local_port: int = 11435
    remote_port: int = 11434
    healthcheck_interval_sec: int = 10
    auto_register_in_omniroute: bool = True
    host: Optional[str] = None
    port: int = 22


RemoteLocalConfig = RemoteSshGpuConfig


class SwarmModeConfig(BaseModel):
    max_parallel_worktrees: int = 4
    worker_cli: str = "opencode"
    symlink_dirs: List[str] = Field(default_factory=lambda: ["node_modules", ".venv", "vendor"])
    roles: Dict[str, str] = Field(
        default_factory=lambda: {
            "backend_core": "architect_heavy",
            "frontend_ui": "fullstack_coder",
            "db_and_tests": "database_and_tests",
            "docs_and_review": "context_and_docs",
        }
    )


class RelayStage(BaseModel):
    stage: str
    model: str


class RelayModeConfig(BaseModel):
    sequence: List[RelayStage] = Field(default_factory=list)
    mid_stream_hot_swap: bool = True


class PersistentModeConfig(BaseModel):
    locked_model: str = "architect_heavy"
    wait_for_5h_quota_reset: bool = True
    poll_quota_interval_sec: int = 30
    stitch_anchor_lines: int = 15


class ModesConfig(BaseModel):
    mode_1_swarm: SwarmModeConfig = Field(default_factory=SwarmModeConfig)
    mode_2_relay: RelayModeConfig = Field(default_factory=RelayModeConfig)
    mode_3_persistent: PersistentModeConfig = Field(default_factory=PersistentModeConfig)


class HydraConfig(BaseModel):
    version: str = "5.0"
    hydra: HydraSettings = Field(default_factory=HydraSettings)
    omniroute: OmniRouteConfig = Field(default_factory=OmniRouteConfig)
    remote_ssh_gpu: RemoteSshGpuConfig = Field(default_factory=RemoteSshGpuConfig)
    modes: ModesConfig = Field(default_factory=ModesConfig)

    @property
    def providers(self):
        class ProvidersCompat:
            ui_cdp = {
                "claude_pro": type("CdpCfg", (), {"enabled": True, "cdp_port": 9222, "model_dump": lambda: {"cdp_port": 9222}}),
                "chatgpt_plus": type("CdpCfg", (), {"enabled": True, "cdp_port": 9223, "model_dump": lambda: {"cdp_port": 9223}}),
                "gemini_pro": type("CdpCfg", (), {"enabled": True, "cdp_port": 9224, "model_dump": lambda: {"cdp_port": 9224}}),
            }
            ide_bridge = {
                "antigravity": type("IdeCfg", (), {"enabled": True, "bridge_url": "http://127.0.0.1:9330", "model_dump": lambda: {"bridge_url": "http://127.0.0.1:9330"}}),
            }
            api_gateway = {
                "openrouter": type("ApiCfg", (), {"enabled": True, "base_url": "https://openrouter.ai/api/v1", "model_dump": lambda: {"base_url": "https://openrouter.ai/api/v1"}}),
                "deepseek": type("ApiCfg", (), {"enabled": True, "base_url": "https://api.deepseek.com/v1", "model_dump": lambda: {"base_url": "https://api.deepseek.com/v1"}}),
            }
            remote_local = {
                "ollama_local": type("LocalCfg", (), {"enabled": True, "base_url": "http://127.0.0.1:11434", "model_dump": lambda: {"base_url": "http://127.0.0.1:11434"}}),
            }
        return ProvidersCompat()

    # Backward compatibility helpers
    @property
    def server(self):
        class ServerCompat:
            host = self.hydra.proxy_host
            port = self.hydra.proxy_port
            title = "Hydra Orchestrator API"
            description = "Universal Autonomous LLM Orchestrator"
        return ServerCompat()

    @property
    def orchestrator(self):
        class OrchCompat:
            default_mode = {1: "swarm", 2: "relay", 3: "persistent"}.get(
                self.hydra.default_mode, "swarm"
            )
            class ResilienceCompat:
                database_path = self.hydra.state_db
                on_limit_action = "hot_handoff"
                handoff_fallback_chain = ["architect_heavy", "fullstack_coder", "database_and_tests"]
                auto_resume_check_interval_seconds = self.modes.mode_3_persistent.poll_quota_interval_sec
            resilience = ResilienceCompat()
        return OrchCompat()

    @property
    def swarm(self):
        class SwarmCompat:
            worktrees_dir = self.hydra.worktree_base_dir
            base_contract_file = ".hydra/contracts/CONTRACT.md"
            auto_merge = True
            run_tests_before_merge = True
            test_command = "pytest"
            difficulty_thresholds = {
                "simple": type("Diff", (), {"max_complexity": 3, "preferred_provider": "database_and_tests"}),
                "moderate": type("Diff", (), {"max_complexity": 7, "preferred_provider": "fullstack_coder"}),
                "complex": type("Diff", (), {"max_complexity": 10, "preferred_provider": "architect_heavy"}),
            }
        return SwarmCompat()


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

    cfg = HydraConfig()
    _CONFIG_CACHE = cfg
    return cfg
