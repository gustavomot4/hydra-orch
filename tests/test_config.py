"""Hermetic unit tests for hydra-orch canonical configuration (Task T01 / RT01).

Validates:
- Loading of default config.yaml with .orchestrator/ runtime paths.
- Rejection of unknown fields (DBC-9 / extra="forbid").
- Alias resolution to primary model, provider and fallbacks (GAP A01).
- Error handling on unknown alias (UnknownAliasError).
- Gateway connection modes (disabled, optional, required) and direct mode (GAP A03).
- Secret reference resolution (${ENV_VAR}) and missing secret errors.
- Backward compatibility properties for server, orchestrator, swarm and providers.
"""

import os
import pytest
from pydantic import ValidationError

from hydra_orch.config import (
    ConfigError,
    HydraConfig,
    HydraSettings,
    OmniRouteConfig,
    UnknownAliasError,
    SecretNotFoundError,
    InvalidConnectionModeError,
    load_config,
    resolve_secret_reference,
)


def test_load_default_config():
    """Valida o carregamento padrão do arquivo config.yaml."""
    config = load_config(reload=True)
    assert isinstance(config, HydraConfig)
    assert config.server.port == 8000
    assert config.server.host == "127.0.0.1"
    assert config.orchestrator.default_mode in ("relay", "swarm", "persistent")
    assert "claude_pro" in config.providers.ui_cdp
    assert config.providers.ui_cdp["claude_pro"].cdp_port == 9222


def test_runtime_paths_normalized_to_orchestrator():
    """Valida que os caminhos de runtime foram normalizados para .orchestrator/ (GAP A12)."""
    config = load_config(reload=True)
    assert config.hydra.worktree_base_dir == ".orchestrator/worktree"
    assert config.hydra.state_db == ".orchestrator/checkpoints.sqlite"
    assert config.swarm.worktrees_dir == ".orchestrator/worktree"
    assert config.swarm.base_contract_file == ".orchestrator/CONTRACT.md"


def test_extra_fields_forbidden():
    """Valida que campos desconhecidos são terminantemente rejeitados (RT01 / extra='forbid')."""
    # Campo desconhecido no nível raiz
    with pytest.raises(ValidationError):
        HydraConfig.model_validate({"unknown_root_field": 123})

    # Campo desconhecido em hydra settings
    with pytest.raises(ValidationError):
        HydraSettings.model_validate({"proxy_port": 8000, "unrecognized_option": True})

    # Campo desconhecido em omniroute config
    with pytest.raises(ValidationError):
        OmniRouteConfig.model_validate({"enabled": True, "fake_param": "bad"})


def test_resolve_alias_valid():
    """Valida a resolução de aliases lógicos configurados (GAP A01)."""
    config = load_config(reload=True)

    # 1. architect_heavy (real OmniRoute catalog model)
    target_arch = config.resolve_alias("architect_heavy")
    assert target_arch.alias == "architect_heavy"
    assert target_arch.primary == "agy/claude-opus-5-5-high"
    assert target_arch.primary_provider == "agy"
    assert target_arch.primary_model == "claude-opus-5-5-high"
    assert target_arch.preferred_adapter == "antigravity"
    assert target_arch.executor == "agy"
    assert target_arch.min_difficulty == 8
    assert "auto/best-reasoning" in target_arch.fallbacks

    # 2. fullstack_coder (real OmniRoute catalog model)
    target_coder = config.resolve_alias("fullstack_coder")
    assert target_coder.primary_provider == "codex"
    assert target_coder.primary_model == "gpt-6-astra"
    assert target_coder.preferred_adapter is None
    assert target_coder.executor == "codex"

    # 3. database_and_tests
    target_db = config.resolve_alias("database_and_tests")
    assert target_db.primary_provider == "ssh-home-gpu"
    assert target_db.preferred_adapter == "ssh_remote"


def test_resolve_alias_direct_provider():
    """Valida resolução direta de nome de provedor registrado."""
    config = load_config(reload=True)

    target = config.resolve_alias("claude_pro")
    assert target.alias == "claude_pro"
    assert target.preferred_adapter == "claude_pro"

    target_direct = config.resolve_alias("openrouter/deepseek-chat")
    assert target_direct.primary_provider == "openrouter"
    assert target_direct.primary_model == "deepseek-chat"
    assert target_direct.preferred_adapter == "openrouter"


def test_resolve_alias_unknown_raises_error():
    """Valida que aliases desconhecidos levantam UnknownAliasError com lista de aliases válidos."""
    config = load_config(reload=True)

    with pytest.raises(UnknownAliasError) as exc_info:
        config.resolve_alias("modelo_inexistente_xyz_123")

    assert "modelo_inexistente_xyz_123" in str(exc_info.value)


def test_omniroute_modes_and_direct_mode():
    """Valida políticas de gateway: disabled, optional, required e modo direto (GAP A03)."""
    # 1. Config padrão: disabled
    config = load_config(reload=True)
    assert config.is_direct_mode is True
    assert config.is_omniroute_required is False

    # 2. Config com gateway required
    cfg_required = HydraConfig.model_validate({
        "omniroute": {
            "enabled": True,
            "connection_mode": "required",
        }
    })
    assert cfg_required.is_omniroute_required is True
    assert cfg_required.is_direct_mode is False

    # A mandatory dependency must never be silently disabled.
    with pytest.raises(ValidationError):
        HydraConfig.model_validate({
            "omniroute": {"enabled": False, "connection_mode": "required"},
        })

    # 4. Modo inválido levanta InvalidConnectionModeError
    with pytest.raises(ValidationError):
        OmniRouteConfig.model_validate({
            "enabled": True,
            "connection_mode": "modo_invalido_xyz",
        })


def test_secret_reference_resolution(monkeypatch):
    """Valida resolução de segredos ${ENV_VAR} e erro quando ausente."""
    monkeypatch.setenv("TEST_API_KEY_HYDRA", "sk-secret-token-12345")

    # Resolução com sucesso
    resolved = resolve_secret_reference("${TEST_API_KEY_HYDRA}")
    assert resolved == "sk-secret-token-12345"

    # String comum não é alterada
    assert resolve_secret_reference("normal_value") == "normal_value"

    # Segredo ausente levanta SecretNotFoundError
    with pytest.raises(SecretNotFoundError) as exc_info:
        resolve_secret_reference("${UNSET_SECRET_XYZ_98765}")
    assert "UNSET_SECRET_XYZ_98765" in str(exc_info.value)


def test_providers_compat_ssh_remote():
    """Valida que providers.remote_local inclui ssh_remote mapeado para remote_ssh_gpu (GAP A13)."""
    config = load_config(reload=True)
    ssh_remote = config.provider_groups()["remote_local"]["ssh_remote"]
    assert ssh_remote.enabled is False
    assert ssh_remote.base_url == "http://127.0.0.1:11435"
    assert config.remote_ssh_gpu.ssh_port == 22


@pytest.mark.parametrize("section, values", [
    ("hydra", {"proxy_port": 0}),
    ("hydra", {"proxy_port": 65536}),
    ("hydra", {"proxy_port": True}),
    ("hydra", {"default_mode": 4}),
    ("hydra", {"default_mode": True}),
    ("hydra", {"default_mode": "2"}),
    ("hydra", {"max_heal_attempts": -1}),
    ("hydra", {"state_db": ".hydra/state.sqlite"}),
    ("hydra", {"worktree_base_dir": ".orchestrator/../outside"}),
    ("execution", {"driver": "unimplemented"}),
    ("execution", {"timeout_seconds": 0}),
    ("visual_interface", {"port": -1}),
    ("remote_ssh_gpu", {"ssh_port": 65536}),
    ("remote_ssh_gpu", {"healthcheck_interval_sec": 0}),
    ("omniroute", {"base_url": "file:///tmp/gateway"}),
    ("omniroute", {"base_url": "http://user:password@localhost"}),
    ("omniroute", {"quota_api_url": "http://localhost:99999"}),
    ("omniroute", {"api_key_env": "123-INVALID"}),
    ("omniroute", {"auto_start_daemon": True}),
    ("omniroute", {"enabled": True, "connection_mode": "disabled"}),
])
def test_invalid_runtime_configuration_rejected(section, values):
    with pytest.raises(ValidationError):
        HydraConfig.model_validate({section: values})


@pytest.mark.parametrize("mode, values", [
    ("mode_1_swarm", {"max_parallel_worktrees": 0}),
    ("mode_1_swarm", {"worker_cli": "unknown"}),
    ("mode_3_persistent", {"poll_quota_interval_sec": 0}),
    ("mode_3_persistent", {"stitch_anchor_lines": -1}),
    ("mode_2_relay", {"sequence": [{"stage": "a", "model": "unknown"}]}),
])
def test_invalid_mode_configuration_rejected(mode, values):
    with pytest.raises(ValidationError):
        HydraConfig.model_validate({"modes": {mode: values}})


def test_explicit_missing_file_never_falls_back(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


@pytest.mark.parametrize("content", [
    "hydra: [", "[]", "false", "42",
    "hydra:\n  proxy_port: 8000\n  proxy_port: 9000\n",
    "hydra: {}\nhydra: {}\n",
])
def test_invalid_yaml_has_clear_error(tmp_path, content):
    source = tmp_path / "config.yaml"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(source)


def test_explicit_config_does_not_replace_default_cache(tmp_path):
    default = load_config(reload=True)
    source = tmp_path / "config.yaml"
    source.write_text("hydra:\n  proxy_port: 9001\n", encoding="utf-8")
    assert load_config(source).server.port == 9001
    assert load_config() is default


def test_default_cache_follows_working_directory(tmp_path, monkeypatch):
    load_config(reload=True)
    (tmp_path / "config.yaml").write_text("hydra:\n  proxy_port: 9002\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert load_config().server.port == 9002


def test_enabled_api_requires_credential_reference(monkeypatch):
    monkeypatch.delenv("HYDRA_TEST_MISSING_KEY", raising=False)
    with pytest.raises(ValidationError, match="Missing credential"):
        HydraConfig.model_validate({"providers": {"api_gateway": {
            "test": {"enabled": True, "base_url": "https://example.invalid/v1",
                     "api_key_env": "HYDRA_TEST_MISSING_KEY"},
        }}})


def test_unknown_adapter_reference_and_duplicate_provider_rejected():
    with pytest.raises(ValidationError, match="Unknown inference adapter"):
        HydraConfig.model_validate({"omniroute": {"logical_models": {
            "example": {"primary": "codex/model", "adapter": "missing"},
        }}})
    with pytest.raises(ValidationError, match="unique across"):
        HydraConfig.model_validate({"providers": {
            "ui_cdp": {"same": {}},
            "remote_local": {"same": {"base_url": "http://localhost:11434"}},
        }})
    with pytest.raises(ValidationError, match="Unknown model alias"):
        HydraConfig.model_validate({"omniroute": {"logical_models": {
            "typo": {"primary": "unregistered/model"},
        }}})


def test_codex_configuration_does_not_create_browser_adapter():
    config = HydraConfig.model_validate({"execution": {"driver": "codex"}})
    assert config.resolve_alias("codex/model").executor == "codex"
    assert config.resolve_alias("codex/model").preferred_adapter is None
    assert config.providers.ui_cdp == {}


@pytest.mark.parametrize("raw_alias, expected_primary, expected_provider, expected_model", [
    ("gemini-4-argon", "agy/gemini-4-argon-high", "agy", "gemini-4-argon-high"),
    ("gemini/gemini-4-argon", "agy/gemini-4-argon-high", "agy", "gemini-4-argon-high"),
    ("agy/gemini-4-argon", "agy/gemini-4-argon-high", "agy", "gemini-4-argon-high"),
    ("agy/gemini-4-argon-high", "agy/gemini-4-argon-high", "agy", "gemini-4-argon-high"),
    ("gemini-4-argon-medium", "agy/gemini-4-argon-medium", "agy", "gemini-4-argon-medium"),
    ("gemini-4-argon-low", "agy/gemini-4-argon-low", "agy", "gemini-4-argon-low"),
    ("antigravity/gemini-4-argon", "antigravity/gemini-4-argon-high", "antigravity", "gemini-4-argon-high"),
])
def test_resolve_alias_gemini_4_argon_normalization(raw_alias, expected_primary, expected_provider, expected_model):
    """Valida que Gemini 4 Argon é normalizado para os tiers suportados pelo perfil CLI (agy)."""
    config = load_config(reload=True)
    resolved = config.resolve_alias(raw_alias)
    assert resolved.primary == expected_primary
    assert resolved.primary_provider == expected_provider
    assert resolved.primary_model == expected_model
    assert resolved.preferred_adapter == "antigravity"
