"""Configuration loading, validation, and domain models for hydra-orch.

Conforms to RT01 (Canonical typed config with strict validation and alias resolution).
Enforces Design by Contract (DBC-9) with extra="forbid" to reject unknown fields.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# EXCEÇÕES DE CONFIGURAÇÃO (RT01)
# ============================================================================

class ConfigError(ValueError):
    """Exceção base para erros de validação e carga de configuração."""
    pass


class UnknownAliasError(ConfigError):
    """Levantada quando um alias de modelo/provedor não é encontrado no mapeamento."""
    pass


class SecretNotFoundError(ConfigError):
    """Levantada quando uma referência de segredo (${ENV_VAR}) não está definida."""
    pass


class InvalidConnectionModeError(ConfigError):
    """Levantada quando o modo de conexão do gateway é inválido."""
    pass


# ============================================================================
# RESOLUÇÃO DE SEGREDOS EXTERNOS (SecretRef / Env)
# ============================================================================

_SECRET_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def resolve_secret_reference(value: str) -> str:
    """Resolve referências externas de segredo no formato `${VAR_NAME}`.

    Se a string não for uma referência, retorna o valor original.
    Se for uma referência e a variável de ambiente não existir, levanta SecretNotFoundError.
    """
    if not isinstance(value, str):
        return value
    match = _SECRET_ENV_PATTERN.match(value.strip())
    if match:
        var_name = match.group(1)
        if var_name not in os.environ:
            raise SecretNotFoundError(
                f"Referência de segredo '${{{var_name}}}' não encontrada nas variáveis de ambiente."
            )
        return os.environ[var_name]
    return value


def _resolve_secrets_recursive(data: Any) -> Any:
    """Aplica resolução de segredos recursivamente em dicionários e listas."""
    if isinstance(data, dict):
        return {k: _resolve_secrets_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_secrets_recursive(item) for item in data]
    elif isinstance(data, str):
        return resolve_secret_reference(data)
    return data


# ============================================================================
# MODELOS DE DOMÍNIO DE CONFIGURAÇÃO (DBC-9 / extra="forbid")
# ============================================================================

class HydraSettings(BaseModel):
    """Configurações centrais do orquestrador Hydra."""
    model_config = ConfigDict(extra="forbid")

    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8000
    default_mode: int = 1  # 1: Swarm (Wave 0 + Wave 1), 2: Relay, 3: Persistente
    preferred_primary_model: str = "claude-pro"
    worktree_base_dir: str = ".orchestrator/worktree"
    state_db: str = ".orchestrator/checkpoints.sqlite"
    auto_heal_build_errors: bool = True
    max_heal_attempts: int = 2


class LogicalModelMapping(BaseModel):
    """Mapeamento de modelo lógico (alias) para modelo primário e fallbacks."""
    model_config = ConfigDict(extra="forbid")

    primary: str
    fallbacks: List[str] = Field(default_factory=list)
    min_difficulty: int = 1


class ResolvedTarget(BaseModel):
    """Alvo resolvido a partir de um alias lógico."""
    model_config = ConfigDict(extra="forbid")

    alias: str
    primary: str
    primary_provider: str
    primary_model: str
    fallbacks: List[str] = Field(default_factory=list)
    min_difficulty: int = 1
    preferred_adapter: Optional[str] = None


class OmniRouteConfig(BaseModel):
    """Configurações da integração com o gateway de inferência OmniRoute."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    auto_start_daemon: bool = False
    connection_mode: str = "disabled"  # disabled | optional | required
    base_url: str = "http://127.0.0.1:20128/v1"
    quota_api_url: str = "http://127.0.0.1:20128/api/usage/quota"
    default_routing_strategy: str = "auto/thrifty"
    logical_models: Dict[str, LogicalModelMapping] = Field(default_factory=dict)

    @field_validator("connection_mode")
    @classmethod
    def validate_connection_mode(cls, v: str) -> str:
        valid_modes = {"disabled", "optional", "required"}
        if v not in valid_modes:
            raise InvalidConnectionModeError(
                f"Modo de conexão '{v}' inválido. Valores permitidos: {sorted(valid_modes)}"
            )
        return v

    @model_validator(mode="after")
    def harmonize_enabled_mode(self) -> OmniRouteConfig:
        if not self.enabled and self.connection_mode != "disabled":
            # Quando enabled é False, connection_mode opera em disabled
            self.connection_mode = "disabled"
        return self


class RemoteSshGpuConfig(BaseModel):
    """Configuração de túnel SSH para execução remota em GPU."""
    model_config = ConfigDict(extra="forbid")

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

    @model_validator(mode="after")
    def sync_host_port(self) -> RemoteSshGpuConfig:
        if self.host is None and "@" in self.ssh_target:
            self.host = self.ssh_target.split("@")[-1]
        elif self.host is None:
            self.host = self.ssh_target
        if self.ssh_port != 22 and self.port == 22:
            self.port = self.ssh_port
        return self


RemoteLocalConfig = RemoteSshGpuConfig


class SwarmModeConfig(BaseModel):
    """Configuração do modo Swarm em Duas Ondas (Wave 0 Fundação + Wave 1 Paralela)."""
    model_config = ConfigDict(extra="forbid")

    max_parallel_worktrees: int = 4
    worker_cli: str = "opencode"
    wave_0_foundation_enabled: bool = True
    lock_dependency_manifests_in_wave_1: bool = True
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
    """Etapa sequencial de pipeline no modo Relay."""
    model_config = ConfigDict(extra="forbid")

    stage: str
    model: str


class RelayModeConfig(BaseModel):
    """Configuração do modo Relay de handoff estruturado."""
    model_config = ConfigDict(extra="forbid")

    sequence: List[RelayStage] = Field(default_factory=list)
    mid_stream_hot_swap: bool = True
    handoff_strategy: Literal["worktree_state", "atomic_turn_retry"] = "worktree_state"


class PersistentModeConfig(BaseModel):
    """Configuração do modo Persistente de auto-resume pós-cota."""
    model_config = ConfigDict(extra="forbid")

    locked_model: str = "architect_heavy"
    wait_for_5h_quota_reset: bool = True
    poll_quota_interval_sec: int = 30
    resume_strategy: Literal["worktree_state", "atomic_turn_retry"] = "worktree_state"
    stitch_anchor_lines: int = 15


class ModesConfig(BaseModel):
    """Agrupamento dos três modos de orquestração."""
    model_config = ConfigDict(extra="forbid")

    mode_1_swarm: SwarmModeConfig = Field(default_factory=SwarmModeConfig)
    mode_2_relay: RelayModeConfig = Field(default_factory=RelayModeConfig)
    mode_3_persistent: PersistentModeConfig = Field(default_factory=PersistentModeConfig)


class VisualInterfaceConfig(BaseModel):
    """Configuração do control plane visual."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 5173
    api_base_path: str = "/v1"
    expose_projects: bool = True
    expose_runs: bool = True
    expose_worktrees: bool = True
    expose_diffs: bool = True
    expose_quota: bool = True


# Mapeamento canônico de provedores de inferência conhecidos
_KNOWN_PROVIDER_ADAPTERS: Dict[str, str] = {
    "claude-code": "claude_pro",
    "claude_code": "claude_pro",
    "claude-pro": "claude_pro",
    "claude_pro": "claude_pro",
    "codex": "chatgpt_plus",
    "chatgpt-plus": "chatgpt_plus",
    "chatgpt_plus": "chatgpt_plus",
    "gemini-cli": "gemini_pro",
    "gemini_cli": "gemini_pro",
    "gemini-pro": "gemini_pro",
    "gemini_pro": "gemini_pro",
    "antigravity": "antigravity",
    "openrouter": "openrouter",
    "deepseek": "deepseek",
    "local-ollama": "ollama_local",
    "local_ollama": "ollama_local",
    "ssh-home-gpu": "ollama_local",
    "ssh_home_gpu": "ollama_local",
    "ollama_local": "ollama_local",
}


class HydraConfig(BaseModel):
    """Configuração canônica e tipada do Hydra Orchestrator (RT01)."""
    model_config = ConfigDict(extra="forbid")

    version: str = "5.0"
    hydra: HydraSettings = Field(default_factory=HydraSettings)
    omniroute: OmniRouteConfig = Field(default_factory=OmniRouteConfig)
    remote_ssh_gpu: RemoteSshGpuConfig = Field(default_factory=RemoteSshGpuConfig)
    modes: ModesConfig = Field(default_factory=ModesConfig)
    visual_interface: VisualInterfaceConfig = Field(default_factory=VisualInterfaceConfig)

    # ------------------------------------------------------------------------
    # MÉTODOS DE RESOLUÇÃO DE ALIASES (RT01 / GAP A01)
    # ------------------------------------------------------------------------

    def resolve_alias(self, alias: str) -> ResolvedTarget:
        """Resolve um alias lógico de modelo para executor, provedor e modelo real."""
        logical_models = self.omniroute.logical_models

        if alias in logical_models:
            mapping = logical_models[alias]
            primary_str = mapping.primary
            if "/" in primary_str:
                provider_part, model_part = primary_str.split("/", 1)
            else:
                provider_part, model_part = primary_str, primary_str
            adapter = _KNOWN_PROVIDER_ADAPTERS.get(provider_part)
            return ResolvedTarget(
                alias=alias,
                primary=mapping.primary,
                primary_provider=provider_part,
                primary_model=model_part,
                fallbacks=mapping.fallbacks,
                min_difficulty=mapping.min_difficulty,
                preferred_adapter=adapter,
            )

        if alias in _KNOWN_PROVIDER_ADAPTERS:
            return ResolvedTarget(
                alias=alias,
                primary=alias,
                primary_provider=alias,
                primary_model=alias,
                fallbacks=[],
                min_difficulty=1,
                preferred_adapter=_KNOWN_PROVIDER_ADAPTERS[alias],
            )

        if "/" in alias:
            provider_part, model_part = alias.split("/", 1)
            adapter = _KNOWN_PROVIDER_ADAPTERS.get(provider_part)
            return ResolvedTarget(
                alias=alias,
                primary=alias,
                primary_provider=provider_part,
                primary_model=model_part,
                fallbacks=[],
                min_difficulty=1,
                preferred_adapter=adapter,
            )

        known_aliases = list(logical_models.keys()) + list(_KNOWN_PROVIDER_ADAPTERS.keys())
        raise UnknownAliasError(
            f"Alias de modelo '{alias}' desconhecido. Aliases configurados: {sorted(set(known_aliases))}"
        )

    # ------------------------------------------------------------------------
    # PROPRIEDADES DE ESTADO OPERACIONAL DO GATEWAY (RT01 / GAP A03)
    # ------------------------------------------------------------------------

    @property
    def is_omniroute_required(self) -> bool:
        """Indica se o gateway OmniRoute é obrigatório para execução."""
        return self.omniroute.enabled and self.omniroute.connection_mode == "required"

    @property
    def is_direct_mode(self) -> bool:
        """Indica se o Hydra está operando em Modo Direto (sem gateway intermediário)."""
        return not self.omniroute.enabled or self.omniroute.connection_mode == "disabled"

    # ------------------------------------------------------------------------
    # COMPATIBILIDADE RETRÓGRADA COM INTERFACES EXISTENTES
    # ------------------------------------------------------------------------

    @property
    def providers(self):
        """Camada de compatibilidade para adaptadores instanciados pelo router."""
        ssh_cfg = self.remote_ssh_gpu
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
                "ssh_remote": type("SshCfg", (), {
                    "enabled": ssh_cfg.enabled,
                    "ssh_target": ssh_cfg.ssh_target,
                    "ssh_port": ssh_cfg.ssh_port,
                    "ssh_key": ssh_cfg.ssh_key,
                    "local_port": ssh_cfg.local_port,
                    "remote_port": ssh_cfg.remote_port,
                    "host": ssh_cfg.host,
                    "port": ssh_cfg.port,
                    "model_dump": lambda: ssh_cfg.model_dump(),
                }),
            }
        return ProvidersCompat()

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
            base_contract_file = ".orchestrator/CONTRACT.md"
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


def load_config(config_path: Optional[str | Path] = None, reload: bool = False) -> HydraConfig:
    """Carrega configuração de arquivo YAML ou retorna instância em cache."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and config_path is None and not reload:
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
                resolved_data = _resolve_secrets_recursive(raw_data)
                cfg = HydraConfig.model_validate(resolved_data)
                _CONFIG_CACHE = cfg
                return cfg

    cfg = HydraConfig()
    _CONFIG_CACHE = cfg
    return cfg
