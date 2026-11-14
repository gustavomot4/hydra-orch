"""T19: hermetic tests for SkillRegistry, SecretRef, SecretResolver, literal scrubbing, and McpClient."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio

from hydra_orch.bridge.mcp_client import McpClient
from hydra_orch.bridge.worker_runner import WorkerRunner
from hydra_orch.core.checkpointer import ExecutionStore
from hydra_orch.core.discovery import DiscoveryService
from hydra_orch.core.git_workspace import GitWorkspaceService
from hydra_orch.core.metrics import MetricsService
from hydra_orch.core.profile_service import ProfileDefinition
from hydra_orch.core.redaction import REDACTED, redact_text
from hydra_orch.core.route_selector import RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.core.skill_registry import (
    DeclaredTool,
    McpDefinition,
    SecretBundle,
    SecretRef,
    SecretResolver,
    SkillDefinition,
    SkillRegistry,
)
from hydra_orch.engine.orchestration import Orchestrator
from hydra_orch.model import CheckSpec, ContractViolation, ExecutorCapability as Capability, RunSpec, TaskSpec, TaskStatus
from test_checkpointer import _make_run_spec
from test_profile import profiles
from test_server import _init_temp_git_repo


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_mcp_fixture(directory: Path, *, mode: str = "normal") -> Path:
    script = directory / f"mcp_fixture_{mode}.py"
    script.write_text(
        f"""
import json
import os
import sys
import time

MODE = {mode!r}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    req_id = msg.get("id")
    if method == "initialize":
        resp = {{"jsonrpc": "2.0", "id": req_id, "result": {{"protocolVersion": "2024-11-05", "serverInfo": {{"name": "fixture", "secret": os.environ.get("MCP_API_KEY", "")}}}}}}
        print(json.dumps(resp), flush=True)
    elif method == "tools/list":
        tools = [{{"name": "echo", "description": "Echo tool"}}]
        if MODE == "normal":
            tools.append({{"name": "undeclared_extra", "description": "Extra"}})
        elif MODE == "missing_declared":
            tools = []
        resp = {{"jsonrpc": "2.0", "id": req_id, "result": {{"tools": tools}}}}
        print(json.dumps(resp), flush=True)
    elif method == "tools/call":
        if MODE == "slow":
            time.sleep(5.0)
        args = msg.get("params", {{}}).get("arguments", {{}})
        resp = {{
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {{
                "content": [{{"type": "text", "text": args.get("text", "")}}],
                "env_seen": bool(os.environ.get("MCP_API_KEY")),
                "host_leaked": "HOST_UNRELATED_SECRET" in os.environ,
                "token": "sk-supersecret12345678",
            }},
        }}
        print(json.dumps(resp), flush=True)
""",
        encoding="utf-8",
    )
    return script


@pytest.mark.asyncio
async def test_secret_ref_rejects_raw_value_and_unavailable_providers(tmp_path):
    store = ExecutionStore(tmp_path / "secrets.sqlite")
    registry = SkillRegistry(store)

    for bad_key in ("sk-live1234567890", "ghp_1234567890abcdef", "aB3dE9fG2hJ5kL8mN1pQ4rS7tU0vW3xY"):
        with pytest.raises(ContractViolation) as exc:
            await registry.create_secret_ref(
                secret_name="API_TOKEN",
                provider_type="env",
                source_key=bad_key,
                principal_id="operator",
            )
        assert exc.value.code == "secret_value_rejected"

    vault_ref = await registry.create_secret_ref(
        secret_name="VAULT_TOK",
        provider_type="vault",
        source_key="secret/data/ci",
        principal_id="operator",
    )
    keyring_ref = await registry.create_secret_ref(
        secret_name="KEYRING_TOK",
        provider_type="keyring",
        source_key="hydra.ci.token",
        principal_id="operator",
    )
    resolver = SecretResolver(registry, env_source={})
    for ref in (vault_ref, keyring_ref):
        with pytest.raises(ContractViolation) as exc:
            await resolver.resolve([ref.secret_id], principal_id="operator")
        assert exc.value.code == "secret_provider_unavailable"


@pytest.mark.asyncio
async def test_secret_never_persisted_and_bundle_not_serializable(profiles):
    service, definition, repository, run = profiles
    sentinel = "OPAQUE_SENTINEL_SECRET_9911"
    registry = SkillRegistry(service.store)
    ref = await registry.create_secret_ref(
        secret_name="EXT_SERVICE_KEY",
        provider_type="env",
        source_key="HYDRA_TEST_EXT_KEY",
        principal_id="operator",
    )
    skill = SkillDefinition(
        name="deploy-helper",
        version="1.0.0",
        manifest_ref="skills/deploy.json",
        permissions_declared=("fs:read", f"secret:{ref.secret_id}"),
        checksum=_sha256(b"deploy-helper"),
    )
    await registry.register_skill(skill, principal_id="operator")
    updated_profile = ProfileDefinition.model_validate({
        **definition.model_dump(mode="json"),
        "skills_refs": [skill.skill_id],
    })
    await service.update_profile(updated_profile, expected_revision=1)
    snapshot = await service.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")

    resolver = SecretResolver(registry, env_source={"HYDRA_TEST_EXT_KEY": sentinel})
    bundle = await resolver.resolve([ref.secret_id], principal_id="operator")
    assert sentinel not in repr(bundle)
    assert sentinel not in str(bundle)
    with pytest.raises(TypeError):
        pickle.dumps(bundle)
    assert sentinel not in snapshot.effective_config_json

    raw_db = Path(service.store.db_path).read_bytes()
    assert sentinel.encode("utf-8") not in raw_db


@pytest.mark.asyncio
async def test_missing_secret_and_reserved_env_block_spawn(tmp_path):
    store = ExecutionStore(tmp_path / "missing.sqlite")
    registry = SkillRegistry(store)
    missing_ref = await registry.create_secret_ref(
        secret_name="MISSING_VAR",
        provider_type="env",
        source_key="NO_SUCH_ENV_VAR_XYZ",
        principal_id="operator",
    )
    reserved_ref = await registry.create_secret_ref(
        secret_name="PATH",
        provider_type="env",
        source_key="SAFE_SOURCE_VAR",
        principal_id="operator",
    )
    resolver = SecretResolver(registry, env_source={"SAFE_SOURCE_VAR": "val"})

    with pytest.raises(ContractViolation) as exc1:
        await resolver.resolve([missing_ref.secret_id], principal_id="operator")
    assert exc1.value.code == "secret_unavailable"

    with pytest.raises(ContractViolation) as exc2:
        await resolver.resolve([reserved_ref.secret_id], principal_id="operator")
    assert exc2.value.code == "invalid_env_var"


@pytest.mark.asyncio
async def test_resolve_at_spawn_filtered_env_and_worker_echo_scrubbed(tmp_path, monkeypatch):
    repo, base_sha = _init_temp_git_repo(tmp_path)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    git_ws = GitWorkspaceService(repo, runtime_dir=tmp_path / ".orchestrator")
    git_ws._run_git_cmd(["add", "."], cwd=repo)
    git_ws._run_git_cmd(["commit", "-m", "add src"], cwd=repo)
    base_sha = git_ws.resolve_commit_sha("HEAD")

    store = ExecutionStore(tmp_path / "run.sqlite")
    registry = SkillRegistry(store)
    sentinel = "opaque-secret-sentinel-7788"
    monkeypatch.setenv("HOST_UNRELATED_SECRET", "must-not-leak-to-worker")
    ref = await registry.create_secret_ref(
        secret_name="WORKER_API_KEY",
        provider_type="env",
        source_key="SOURCE_WORKER_KEY",
        principal_id="operator",
    )
    resolver = SecretResolver(registry, env_source={"SOURCE_WORKER_KEY": sentinel})
    bundle = await resolver.resolve([ref.secret_id], principal_id="operator")

    base_spec = _make_run_spec(str(repo))
    task_tpl = base_spec.tasks[0].model_dump(mode="json")
    task_tpl.update(
        task_id="t1",
        run_id=base_spec.run_id,
        assigned_executor="custom",
        allowed_paths=["src/**"],
        acceptance_criteria=[CheckSpec(check_id="ok", command=(sys.executable, "-c", "print('ok')")).model_dump(mode="json")],
    )
    run_spec = RunSpec.model_validate({
        **base_spec.model_dump(mode="json"),
        "base_sha": base_sha,
        "tasks": [task_tpl],
    })
    await store.submit_run_idempotent(run_spec)

    worker_code = (
        "import os, pathlib; "
        "assert os.environ.get('WORKER_API_KEY') == 'opaque-secret-sentinel-7788'; "
        "assert 'HOST_UNRELATED_SECRET' not in os.environ; "
        "print('leaked:', os.environ['WORKER_API_KEY']); "
        "pathlib.Path('src/app.py').write_text('x = 2\\n')"
    )
    run_service = RunService(
        store=store,
        repo_root=repo,
        worker_runner=WorkerRunner(),
        runtime_dir=tmp_path / ".orchestrator",
    )
    outcome = await run_service.execute_task_attempt(
        run_spec.run_id,
        "t1",
        custom_command=[sys.executable, "-c", worker_code],
        secret_bundle=bundle,
    )
    assert outcome.result.task_status == TaskStatus.READY_FOR_REVIEW
    stdout_artifacts = [a for a in outcome.result.artifacts if a.kind == "log" and "stdout" in a.relative_path]
    assert stdout_artifacts
    log_path = tmp_path / stdout_artifacts[0].relative_path
    log_bytes = log_path.read_bytes()
    assert sentinel.encode("utf-8") not in log_bytes
    assert REDACTED.encode("utf-8") in log_bytes
    assert _sha256(log_bytes) == stdout_artifacts[0].sha256


@pytest.mark.asyncio
async def test_secret_in_patch_rejected(tmp_path):
    repo, _ = _init_temp_git_repo(tmp_path)
    (repo / "src").mkdir(exist_ok=True)
    (repo / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    git_ws = GitWorkspaceService(repo, runtime_dir=tmp_path / ".orchestrator")
    git_ws._run_git_cmd(["add", "."], cwd=repo)
    git_ws._run_git_cmd(["commit", "-m", "add src"], cwd=repo)
    base_sha = git_ws.resolve_commit_sha("HEAD")

    store = ExecutionStore(tmp_path / "patch.sqlite")
    registry = SkillRegistry(store)
    sentinel = "opaque-patch-secret-5544"
    ref = await registry.create_secret_ref(
        secret_name="WORKER_API_KEY",
        provider_type="env",
        source_key="SOURCE_PATCH_KEY",
        principal_id="operator",
    )
    bundle = await SecretResolver(registry, env_source={"SOURCE_PATCH_KEY": sentinel}).resolve(
        [ref.secret_id], principal_id="operator"
    )
    base_spec = _make_run_spec(str(repo))
    task_tpl = base_spec.tasks[0].model_dump(mode="json")
    task_tpl.update(
        assigned_executor="custom",
        allowed_paths=["src/**"],
        acceptance_criteria=[CheckSpec(check_id="ok", command=(sys.executable, "-c", "print('ok')")).model_dump(mode="json")],
    )
    run_spec = RunSpec.model_validate({
        **base_spec.model_dump(mode="json"),
        "base_sha": base_sha,
        "tasks": [task_tpl],
    })
    await store.submit_run_idempotent(run_spec)
    task_id = run_spec.tasks[0].task_id
    run_service = RunService(store=store, repo_root=repo, worker_runner=WorkerRunner(), runtime_dir=tmp_path / ".orchestrator")
    worker_code = "import os, pathlib; pathlib.Path('src/app.py').write_text(os.environ['WORKER_API_KEY'])"
    outcome = await run_service.execute_task_attempt(
        run_spec.run_id,
        task_id,
        custom_command=[sys.executable, "-c", worker_code],
        secret_bundle=bundle,
    )
    assert outcome.result.task_status == TaskStatus.FAILED
    assert any(f.code == "secret_in_patch" for f in outcome.result.failures)


@pytest.mark.asyncio
async def test_discovered_skill_hash_and_revocation_gates(profiles, tmp_path):
    service, definition, repository, run = profiles
    root = tmp_path / "disc_skills"
    root.mkdir()
    manifest = root / "skill.json"
    manifest.write_text('{"capabilities": ["workspace_execution"]}', encoding="utf-8")
    discovery = DiscoveryService(service.store, allowed_roots=[root], enabled=True)
    discovered = (await discovery.scan(root, principal_id="operator"))[0]
    registry = SkillRegistry(service.store, discovery=discovery)

    skill = SkillDefinition(
        name="disc-skill",
        version="1.0.0",
        manifest_ref=str(manifest),
        discovered_resource_id=discovered.discovery_id,
        permissions_declared=("fs:read",),
        checksum=discovered.content_hash,
    )
    # Untrusted before approval
    with pytest.raises(ContractViolation, match="approved"):
        await registry.register_skill(skill, principal_id="operator")

    await discovery.approve(discovered.discovery_id, discovered.content_hash, principal_id="operator")
    # Hash mismatch rejected
    bad_hash_skill = SkillDefinition(
        name="disc-skill",
        version="1.0.1",
        manifest_ref=str(manifest),
        discovered_resource_id=discovered.discovery_id,
        permissions_declared=("fs:read",),
        checksum="0" * 64,
    )
    with pytest.raises(ContractViolation, match="checksum"):
        await registry.register_skill(bad_hash_skill, principal_id="operator")

    await registry.register_skill(skill, principal_id="operator")

    # External net permission incompatible with network_isolation
    net_skill = SkillDefinition(
        name="net-skill",
        version="1.0.0",
        manifest_ref="skills/net.json",
        permissions_declared=("net:external",),
        checksum=_sha256(b"net"),
    )
    await registry.register_skill(net_skill, principal_id="operator")
    prof_svc = service
    prof_svc.discovery = discovery
    net_profile = ProfileDefinition.model_validate({
        **definition.model_dump(mode="json"),
        "skills_refs": [net_skill.skill_id],
        "required_capabilities": [Capability.WORKSPACE_EXECUTION.value, Capability.NETWORK_ISOLATION.value],
    })
    await prof_svc.update_profile(net_profile, expected_revision=1)
    with pytest.raises(ContractViolation) as cap_err:
        await prof_svc.resolve_effective(definition.profile_id, repository["id"], principal_id="operator")
    assert cap_err.value.code == "capability_mismatch"

    # Revoking skill after snapshot blocks orchestration admission
    ok_profile = ProfileDefinition.model_validate({
        **definition.model_dump(mode="json"),
        "skills_refs": [skill.skill_id],
        "required_capabilities": [Capability.WORKSPACE_EXECUTION.value, Capability.CANCEL_PROCESS_TREE.value],
    })
    await prof_svc.update_profile(ok_profile, expected_revision=2)
    snapshot = await prof_svc.snapshot(definition.profile_id, run.run_id, repository["id"], principal_id="operator")
    await registry.revoke_skill(skill.skill_id, principal_id="operator")

    run_service = RunService(store=service.store, repo_root=run.repo_root, worker_runner=WorkerRunner(), runtime_dir=tmp_path / ".orchestrator")
    routes = RouteSelector(service.store, prof_svc.agents, MetricsService(service.store))
    orch = Orchestrator(run_service, prof_svc, routes)
    scoped_tasks = tuple(TaskSpec.model_validate({**t.model_dump(mode="json"), "allowed_paths": ["src/**"]}) for t in run.tasks)
    scoped_run = RunSpec.model_validate({**run.model_dump(mode="json"), "tasks": [t.model_dump(mode="json") for t in scoped_tasks]})
    plan = SimpleNamespace(run=scoped_run, profile_id=definition.profile_id, repository_id=repository["id"])
    with pytest.raises(ContractViolation) as rev_err:
        await orch._admit(plan, ProfileDefinition.model_validate(snapshot.effective_config["profile"]), "operator")
    assert rev_err.value.code == "component_revoked"


@pytest.mark.asyncio
async def test_mcp_stdio_handshake_tools_permissions_and_redaction(tmp_path, monkeypatch):
    store = ExecutionStore(tmp_path / "mcp.sqlite")
    registry = SkillRegistry(store)
    monkeypatch.setenv("HOST_UNRELATED_SECRET", "host-secret-must-not-appear")
    ref = await registry.create_secret_ref(
        secret_name="MCP_API_KEY",
        provider_type="env",
        source_key="HYDRA_MCP_SRC_KEY",
        principal_id="operator",
    )
    bundle = await SecretResolver(registry, env_source={"HYDRA_MCP_SRC_KEY": "mcp-secret-val-123"}).resolve(
        [ref.secret_id], principal_id="operator"
    )
    server_script = _write_mcp_fixture(tmp_path, mode="normal")
    mcp = McpDefinition(
        server_name="local-echo",
        transport_type="stdio",
        endpoint=f"{sys.executable} {server_script}",
        secret_ref=ref.secret_id,
        declared_tools=(DeclaredTool(name="echo"),),
        permissions=("fs:read", f"secret:{ref.secret_id}"),
    )
    await registry.register_mcp(mcp, principal_id="operator")

    async with McpClient(
        mcp,
        secret_bundle=bundle,
        granted_permissions=("fs:read", f"secret:{ref.secret_id}"),
        timeout_seconds=5.0,
    ) as client:
        assert client.verified_tools == ("echo",)
        assert client.ignored_undeclared_tools == ("undeclared_extra",)
        out = await client.call_tool("echo", {"text": "hello"})
        assert out["env_seen"] is True
        assert out["host_leaked"] is False
        assert out["token"] == REDACTED
        with pytest.raises(ContractViolation) as undecl_err:
            await client.call_tool("undeclared_extra", {})
        assert undecl_err.value.code == "mcp_permission_denied"

    # Insufficient permissions rejected before spawn
    denied = McpClient(mcp, granted_permissions=("fs:read",))
    with pytest.raises(ContractViolation) as perm_err:
        await denied.connect()
    assert perm_err.value.code == "mcp_permission_denied"

    # Missing declared tool fails handshake
    missing_script = _write_mcp_fixture(tmp_path, mode="missing_declared")
    mcp_missing = McpDefinition(
        server_name="missing-tools",
        transport_type="stdio",
        endpoint=f"{sys.executable} {missing_script}",
        declared_tools=(DeclaredTool(name="echo"),),
        permissions=("fs:read",),
    )
    with pytest.raises(ContractViolation) as mismatch_err:
        async with McpClient(mcp_missing, timeout_seconds=5.0):
            pass
    assert mismatch_err.value.code == "mcp_tools_mismatch"


@pytest.mark.asyncio
async def test_mcp_remote_transports_refused_and_timeout_tree_kill(tmp_path):
    for transport in ("sse", "websocket"):
        remote = McpDefinition(
            server_name=f"remote-{transport}",
            transport_type=transport,
            endpoint="https://127.0.0.1:9000/mcp",
            declared_tools=(DeclaredTool(name="echo"),),
            permissions=("net:loopback",),
        )
        with pytest.raises(ContractViolation) as exc:
            await McpClient(remote).connect()
        assert exc.value.code == "mcp_transport_uncertified"

    with pytest.raises(ValueError):
        McpDefinition(
            server_name="bad-endpoint",
            transport_type="sse",
            endpoint="https://user:pass@example.com/mcp",
            declared_tools=(),
            permissions=("net:external",),
        )

    slow_script = _write_mcp_fixture(tmp_path, mode="slow")
    slow_mcp = McpDefinition(
        server_name="slow",
        transport_type="stdio",
        endpoint=f"{sys.executable} {slow_script}",
        declared_tools=(DeclaredTool(name="echo"),),
        permissions=("fs:read",),
    )
    async with McpClient(slow_mcp, timeout_seconds=1.0) as client:
        with pytest.raises(ContractViolation) as timeout_err:
            await client.call_tool("echo", {"text": "wait"})
        assert timeout_err.value.code == "mcp_timeout"


@pytest.mark.asyncio
async def test_audit_atomic_rollback_on_revoked_secret(tmp_path):
    store = ExecutionStore(tmp_path / "rollback.sqlite")
    registry = SkillRegistry(store)
    ref = await registry.create_secret_ref(
        secret_name="REVOKED_KEY",
        provider_type="env",
        source_key="REVOKED_SOURCE",
        principal_id="operator",
    )
    await registry.revoke_secret_ref(ref.secret_id, principal_id="operator")
    bad_skill = SkillDefinition(
        name="blocked-skill",
        version="1.0.0",
        manifest_ref="skills/blocked.json",
        permissions_declared=(f"secret:{ref.secret_id}",),
        checksum=_sha256(b"blocked"),
    )
    with pytest.raises(ContractViolation) as exc:
        await registry.register_skill(bad_skill, principal_id="operator")
    assert exc.value.code == "component_revoked"
    async with store._connect() as db:
        assert (await (await db.execute("SELECT count(*) FROM skill_definitions")).fetchone())[0] == 0
        assert (
            await (
                await db.execute(
                    "SELECT count(*) FROM commands WHERE scope='skill_registry' AND json_extract(response_json,'$.event')='skill.registered'"
                )
            ).fetchone()
        )[0] == 0
