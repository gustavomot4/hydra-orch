"""Configuration loading, validation, and domain models for hydra-orch.

Conforms to RT01 (Canonical typed config with strict validation and alias resolution).
Enforces Design by Contract (DBC-9) with extra="forbid" to reject unknown fields.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlsplit
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# EXCEÇÕES DE CONFIGURAÇÃO (RT01)
# ============================================================================

class ConfigError(ValueError):
    """Exceção base para erros de validação e carga de configuração."""
    code = "invalid_configuration"
    status_code = 400


class UnknownAliasError(ConfigError):
    """Levantada quando um alias de modelo/provedor não é encontrado no mapeamento."""
    pass


class SecretNotFoundError(ConfigError):
    """Levantada quando uma referência de segredo (${ENV_VAR}) não está definida."""
    pass


class InvalidConnectionModeError(ConfigError):
    """Levantada quando o modo de conexão do gateway é inválido."""
    pass


class ProviderUnavailableError(ConfigError):
    """No configured inference route can satisfy the request."""

    code = "provider_unavailable"
    status_code = 503


class GatewayUnavailableError(ConfigError):
    """A required gateway failed its preflight check."""

    code = "gateway_unavailable"
    status_code = 503


class UnsupportedModeError(ConfigError):
    code = "unsupported_mode"
    status_code = 422


def _http_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid HTTP endpoint") from exc
    if (any(c.isspace() for c in value) or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or (port is not None and port < 1)):
        raise ValueError("Expected an HTTP(S) endpoint without credentials or fragment")
    return value.rstrip("/")


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, hide_input_in_errors=True)


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

class HydraSettings(StrictConfig):
    """Configurações centrais do orquestrador Hydra."""
    proxy_host: str = "127.0.0.1"
    proxy_port: int = Field(default=8000, ge=1, le=65535, strict=True)
    default_mode: Literal[1, 2, 3] = 2
    preferred_primary_model: Optional[str] = None
    inference_fallback_chain: List[str] = Field(default_factory=list)
    worktree_base_dir: str = ".orchestrator/worktree"
    state_db: str = ".orchestrator/checkpoints.sqlite"
    auto_heal_build_errors: bool = True
    max_heal_attempts: int = Field(default=2, ge=0, strict=True)

    @field_validator("default_mode", mode="before")
    @classmethod
    def validate_mode(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("default_mode must be 1, 2 or 3")
        return value

    @field_validator("worktree_base_dir", "state_db")
    @classmethod
    def validate_runtime_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if len(parts) < 2 or parts[0] != ".orchestrator" or any(p in {"", ".", ".."} or ":" in p for p in parts):
            raise ValueError("Runtime paths must stay under .orchestrator/; migrate legacy data explicitly")
        return normalized


class LogicalModelMapping(StrictConfig):
    """Mapeamento de modelo lógico (alias) para modelo primário e fallbacks."""
    primary: str = Field(min_length=1)
    fallbacks: List[str] = Field(default_factory=list)
    min_difficulty: int = Field(default=1, ge=1, le=10, strict=True)
    adapter: Optional[str] = None


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
    executor: Optional[str] = None


class ExecutionConfig(StrictConfig):
    """Driver configuration; capability/certification validation belongs to AgentRegistry (T12)."""

    driver: Literal["codex", "claude-code", "gemini", "opencode", "aider"] = "codex"
    model: Optional[str] = Field(default=None, min_length=1)
    timeout_seconds: int = Field(default=300, gt=0, strict=True)


class OmniRouteConfig(StrictConfig):
    """Configurações da integração com o gateway de inferência OmniRoute."""
    enabled: bool = False
    auto_start_daemon: bool = False
    connection_mode: str = "disabled"  # disabled | optional | required
    base_url: str = "http://127.0.0.1:20128/v1"
    quota_api_url: str = "http://127.0.0.1:20128/api/usage/quota"
    api_key_env: str = Field(default="OMNIROUTE_API_KEY", min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    default_routing_strategy: str = "auto/thrifty"
    logical_models: Dict[str, LogicalModelMapping] = Field(default_factory=dict)

    _validate_urls = field_validator("base_url", "quota_api_url")(_http_url)

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
            raise ValueError("Gateway optional/required requires enabled=true")
        if self.enabled and self.connection_mode == "disabled":
            raise ValueError("Gateway enabled=true requires optional or required mode")
        if self.auto_start_daemon:
            raise ValueError("Automatic gateway startup is not implemented; start it externally")
        return self


class RemoteSshGpuConfig(StrictConfig):
    """Configuração de túnel SSH para execução remota em GPU."""
    enabled: bool = False
    ssh_target: str = "usuario@192.168.1.100"
    ssh_port: int = Field(default=22, ge=1, le=65535, strict=True)
    ssh_key: str = "~/.ssh/id_ed25519"
    local_port: int = Field(default=11435, ge=1, le=65535, strict=True)
    remote_port: int = Field(default=11434, ge=1, le=65535, strict=True)
    healthcheck_interval_sec: int = Field(default=10, gt=0, strict=True)
    auto_register_in_omniroute: bool = True
    host: Optional[str] = None
    port: int = Field(default=22, ge=1, le=65535, strict=True)

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


class CdpProviderConfig(StrictConfig):
    enabled: bool = False
    cdp_port: int = Field(default=9222, ge=1, le=65535, strict=True)


class IdeProviderConfig(StrictConfig):
    enabled: bool = False
    bridge_url: str = "http://127.0.0.1:9330"
    _validate_url = field_validator("bridge_url")(_http_url)


class HttpProviderConfig(StrictConfig):
    enabled: bool = False
    base_url: str
    default_model: str = ""
    timeout_seconds: float = Field(default=120.0, gt=0, allow_inf_nan=False)
    _validate_url = field_validator("base_url")(_http_url)


class ApiProviderConfig(HttpProviderConfig):
    api_key_env: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class ProvidersConfig(StrictConfig):
    ui_cdp: Dict[str, CdpProviderConfig] = Field(default_factory=dict)
    ide_bridge: Dict[str, IdeProviderConfig] = Field(default_factory=dict)
    api_gateway: Dict[str, ApiProviderConfig] = Field(default_factory=dict)
    remote_local: Dict[str, HttpProviderConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_names(self) -> ProvidersConfig:
        names = []
        for group in (self.ui_cdp, self.ide_bridge, self.api_gateway, self.remote_local):
            for name in group:
                if not name.strip() or "/" in name or name == "ssh_remote":
                    raise ValueError("Provider names must be nonempty, contain no slash, and not use reserved ssh_remote")
                names.append(name)
        if len(names) != len(set(names)):
            raise ValueError("Provider names must be unique across transports")
        return self

    def names(self) -> set[str]:
        return set(self.ui_cdp) | set(self.ide_bridge) | set(self.api_gateway) | set(self.remote_local)


class SwarmModeConfig(StrictConfig):
    """Configuração do modo Swarm em Duas Ondas (Wave 0 Fundação + Wave 1 Paralela)."""
    max_parallel_worktrees: int = Field(default=4, gt=0, strict=True)
    worker_cli: Literal["codex", "opencode", "aider", "claude-code", "gemini", "antigravity"] = "codex"
    wave_0_foundation_enabled: bool = True
    lock_dependency_manifests_in_wave_1: bool = True
    symlink_dirs: List[str] = Field(default_factory=lambda: ["node_modules", ".venv", "vendor"])
    roles: Dict[str, str] = Field(default_factory=dict)


class RelayStage(StrictConfig):
    """Etapa sequencial de pipeline no modo Relay."""
    stage: str = Field(min_length=1)
    model: str = Field(min_length=1)


class RelayModeConfig(StrictConfig):
    """Configuração do modo Relay de handoff estruturado."""
    sequence: List[RelayStage] = Field(default_factory=list)
    mid_stream_hot_swap: bool = True
    handoff_strategy: Literal["worktree_state", "atomic_turn_retry"] = "worktree_state"


class PersistentModeConfig(StrictConfig):
    """Configuração do modo Persistente de auto-resume pós-cota."""
    locked_model: Optional[str] = None
    wait_for_5h_quota_reset: bool = True
    poll_quota_interval_sec: int = Field(default=30, gt=0, strict=True)
    resume_strategy: Literal["worktree_state", "atomic_turn_retry"] = "worktree_state"
    stitch_anchor_lines: int = Field(default=15, gt=0, strict=True)


class ModesConfig(StrictConfig):
    """Agrupamento dos três modos de orquestração."""
    mode_1_swarm: SwarmModeConfig = Field(default_factory=SwarmModeConfig)
    mode_2_relay: RelayModeConfig = Field(default_factory=RelayModeConfig)
    mode_3_persistent: PersistentModeConfig = Field(default_factory=PersistentModeConfig)


class VisualInterfaceConfig(StrictConfig):
    """Configuração do control plane visual."""
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(default=5173, ge=1, le=65535, strict=True)
    api_base_path: str = "/v1"
    expose_projects: bool = True
    expose_runs: bool = True
    expose_worktrees: bool = True
    expose_diffs: bool = True
    expose_quota: bool = True


_ARGON_TIERS = {"gemini-4-argon-high", "gemini-4-argon-medium", "gemini-4-argon-low"}


def normalize_gemini_argon_target(target: str) -> str:
    """Normalize Gemini 4 Argon model targets to tiered Antigravity CLI ('agy') IDs.

    Google AI Studio ('gemini/gemini-4-argon') has 0 free/API-key quota for Argon 4,
    and Cloud Code / Antigravity only serves tiered IDs ('gemini-4-argon-high',
    '-medium', '-low') under the CLI clientProfile ('agy').
    """
    stripped = target.strip()
    if stripped != target or not stripped:
        return target
    if stripped == "gemini-4-argon":
        return "agy/gemini-4-argon-high"
    if stripped in _ARGON_TIERS:
        return f"agy/{stripped}"
    provider, sep, model = stripped.partition("/")
    if not sep:
        return target
    if provider in {"gemini", "agy"} and model == "gemini-4-argon":
        return "agy/gemini-4-argon-high"
    if provider == "antigravity" and model == "gemini-4-argon":
        return "antigravity/gemini-4-argon-high"
    if provider == "gemini" and model in _ARGON_TIERS:
        return f"agy/{model}"
    return target


class HydraConfig(StrictConfig):
    """Configuração canônica e tipada do Hydra Orchestrator (RT01)."""
    version: str = "5.0"
    hydra: HydraSettings = Field(default_factory=HydraSettings)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    omniroute: OmniRouteConfig = Field(default_factory=OmniRouteConfig)
    remote_ssh_gpu: RemoteSshGpuConfig = Field(default_factory=RemoteSshGpuConfig)
    modes: ModesConfig = Field(default_factory=ModesConfig)
    visual_interface: VisualInterfaceConfig = Field(default_factory=VisualInterfaceConfig)

    # ------------------------------------------------------------------------
    # MÉTODOS DE RESOLUÇÃO DE ALIASES (RT01 / GAP A01)
    # ------------------------------------------------------------------------

    def resolve_alias(self, alias: str) -> ResolvedTarget:
        """Resolve inference adapters separately from configured CLI executors."""
        alias = alias.strip()
        mapping = self.omniroute.logical_models.get(alias)
        raw_primary = mapping.primary if mapping else alias
        if raw_primary != raw_primary.strip():
            raise UnknownAliasError("Invalid provider/model target")
        primary = normalize_gemini_argon_target(raw_primary)
        provider, _, model = primary.partition("/")
        if any(c.isspace() for c in provider):
            raise UnknownAliasError("Invalid provider/model target")
        if not mapping and not model:
            for group in self.provider_groups().values():
                if provider in group:
                    model = getattr(group[provider], "default_model", "")
                    break
        model = model or provider
        adapter = mapping.adapter if mapping else None
        known = self.providers.names() | {"ssh_remote"}
        if adapter is None:
            if provider in known:
                adapter = provider
            elif provider == "agy" and "antigravity" in known:
                adapter = "antigravity"
        executor = provider if provider in {"codex", "claude-code", "gemini", "agy", "opencode", "aider"} else None
        is_omniroute_combo = "/" in primary and provider == "auto"
        if not primary.strip() or not provider or ("/" in primary and not primary.partition("/")[2].strip()):
            raise UnknownAliasError("Expected a nonempty provider/model target")
        if (
            (mapping is None or mapping.adapter is None)
            and provider not in known
            and executor is None
            and not is_omniroute_combo
        ):
            raise UnknownAliasError(f"Unknown model alias '{alias}'")
        fallbacks = [normalize_gemini_argon_target(fb) for fb in mapping.fallbacks] if mapping else []
        return ResolvedTarget(
            alias=alias, primary=primary, primary_provider=provider, primary_model=model,
            fallbacks=fallbacks,
            min_difficulty=mapping.min_difficulty if mapping else 1,
            preferred_adapter=adapter, executor=executor,
        )

    @model_validator(mode="after")
    def validate_references(self) -> HydraConfig:
        known = self.providers.names() | {"ssh_remote"}
        for provider in self.providers.api_gateway.values():
            if provider.enabled and not os.environ.get(provider.api_key_env):
                raise SecretNotFoundError(f"Missing credential environment variable: {provider.api_key_env}")
        for alias, mapping in self.omniroute.logical_models.items():
            if not alias.strip() or "/" in alias:
                raise ValueError("Logical model aliases must be nonempty and contain no slash")
            if mapping.adapter is not None and mapping.adapter not in known:
                raise ValueError(f"Unknown inference adapter for alias '{alias}'")
            self.resolve_alias(alias)
            for fallback in mapping.fallbacks:
                self.resolve_alias(fallback)
        references = list(self.hydra.inference_fallback_chain)
        references += [stage.model for stage in self.modes.mode_2_relay.sequence]
        references += list(self.modes.mode_1_swarm.roles.values())
        references += [self.hydra.preferred_primary_model, self.modes.mode_3_persistent.locked_model]
        for reference in references:
            if reference is not None:
                self.resolve_alias(reference)
        stages = [stage.stage for stage in self.modes.mode_2_relay.sequence]
        if len(stages) != len(set(stages)):
            raise ValueError("Relay stage names must be unique")
        return self

    def provider_groups(self) -> Dict[str, Dict[str, Any]]:
        """Return configured transports and the canonical optional SSH adapter."""
        ssh = self.remote_ssh_gpu
        remote = dict(self.providers.remote_local)
        remote["ssh_remote"] = HttpProviderConfig(
            enabled=ssh.enabled, base_url=f"http://127.0.0.1:{ssh.local_port}",
        )
        return {
            "ui_cdp": self.providers.ui_cdp,
            "ide_bridge": self.providers.ide_bridge,
            "api_gateway": self.providers.api_gateway,
            "remote_local": remote,
        }

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
            default_mode = {1: "swarm", 2: "relay", 3: "persistent"}[self.hydra.default_mode]
            class ResilienceCompat:
                database_path = self.hydra.state_db
                on_limit_action = "hot_handoff"
                handoff_fallback_chain = list(dict.fromkeys(
                    ([self.hydra.preferred_primary_model] if self.hydra.preferred_primary_model else [])
                    + [stage.model for stage in self.modes.mode_2_relay.sequence]
                    + self.hydra.inference_fallback_chain
                ))
                auto_resume_check_interval_seconds = self.modes.mode_3_persistent.poll_quota_interval_sec
            resilience = ResilienceCompat()
        return OrchCompat()

    @property
    def swarm(self):
        class SwarmCompat:
            worktrees_dir = self.hydra.worktree_base_dir
            base_contract_file = ".orchestrator/CONTRACT.md"
            auto_merge = False
            run_tests_before_merge = True
            test_command = "pytest"
        return SwarmCompat()


class _UniqueLoader(yaml.SafeLoader):
    """Reject duplicate configuration keys rather than silently dropping values."""


def _unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ConfigError("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)
_CONFIG_CACHE: Optional[HydraConfig] = None
_CONFIG_CACHE_PATH: Optional[Path] = None


def load_config(config_path: Optional[str | Path] = None, reload: bool = False) -> HydraConfig:
    """Explicit paths never fall back to another file or pollute the default cache."""
    global _CONFIG_CACHE, _CONFIG_CACHE_PATH
    if config_path is not None:
        selected = Path(config_path).expanduser().resolve()
        if not selected.is_file():
            raise ConfigError(f"Configuration file not found: {selected}")
    else:
        candidates = [Path("config.yaml"), Path("config.yml"),
                      Path.home() / ".config" / "hydra-orch" / "config.yaml"]
        selected = next((p.resolve() for p in candidates if p.is_file()), None)
        if not reload and _CONFIG_CACHE is not None and selected == _CONFIG_CACHE_PATH:
            return _CONFIG_CACHE

    raw_data = {}
    if selected is not None:
        try:
            with selected.open(encoding="utf-8") as stream:
                raw_data = yaml.load(stream, Loader=_UniqueLoader)
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError("Cannot read configuration YAML") from exc
        if raw_data is None:
            raw_data = {}
        if not isinstance(raw_data, dict):
            raise ConfigError("Configuration YAML must contain an object")
    cfg = HydraConfig.model_validate(_resolve_secrets_recursive(raw_data))
    if config_path is None:
        _CONFIG_CACHE, _CONFIG_CACHE_PATH = cfg, selected
    return cfg
