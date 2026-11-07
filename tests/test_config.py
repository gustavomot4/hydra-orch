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

    # 1. architect_heavy
    target_arch = config.resolve_alias("architect_heavy")
    assert target_arch.alias == "architect_heavy"
    assert target_arch.primary == "claude-code/claude-3-7-sonnet"
    assert target_arch.primary_provider == "claude-code"
    assert target_arch.primary_model == "claude-3-7-sonnet"
    assert target_arch.preferred_adapter == "claude_pro"
    assert target_arch.min_difficulty == 8
    assert len(target_arch.fallbacks) >= 1

    # 2. fullstack_coder
    target_coder = config.resolve_alias("fullstack_coder")
    assert target_coder.primary_provider == "codex"
    assert target_coder.primary_model == "gpt-4o-plus"
    assert target_coder.preferred_adapter == "chatgpt_plus"

    # 3. database_and_tests
    target_db = config.resolve_alias("database_and_tests")
    assert target_db.primary_provider == "ssh-home-gpu"
    assert target_db.preferred_adapter == "ollama_local"


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
    assert "architect_heavy" in str(exc_info.value)


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

    # 3. Config com enabled=False harmoniza connection_mode para disabled
    cfg_disabled = HydraConfig.model_validate({
        "omniroute": {
            "enabled": False,
            "connection_mode": "required",
        }
    })
    assert cfg_disabled.omniroute.connection_mode == "disabled"
    assert cfg_disabled.is_direct_mode is True

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
    ssh_remote = config.providers.remote_local.get("ssh_remote")
    assert ssh_remote is not None
    assert ssh_remote.ssh_port == 22
    assert ssh_remote.local_port == 11435
    assert hasattr(ssh_remote, "model_dump")
