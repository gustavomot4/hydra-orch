"""Offline CLI checks for configuration policy; no agent processes are launched."""

import httpx
from typer.testing import CliRunner

from hydra_orch import cli
from hydra_orch.config import HydraConfig


def test_missing_inference_route_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: HydraConfig())
    result = CliRunner().invoke(cli.app, ["run", "test", "--mode", "relay"])
    assert result.exit_code == 1
    assert "provider_unavailable" in result.output


def test_disabled_quota_displays_unknown_without_network(monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda: HydraConfig())

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled gateway cannot make HTTP calls")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    result = CliRunner().invoke(cli.app, ["quota"])
    assert result.exit_code == 0
    assert "unknown" in result.output
    assert "100%" not in result.output
