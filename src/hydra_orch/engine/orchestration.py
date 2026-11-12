"""Contract-driven orchestration over durable execution, review and Git evidence.

The caller supplies a plan and explicit CLI arguments. Model text is never a
substitute for a worker process, a check result, or a review decision.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Awaitable, Callable, Literal, Optional

from pydantic import Field, model_validator

from hydra_orch.core.identifier import new_id
from hydra_orch.core.profile_service import ProfileDefinition, ProfileService, canonical_json
from hydra_orch.core.redaction import redact, redact_text
from hydra_orch.core.skill_registry import validate_profile_component
from hydra_orch.core.route_selector import RouteCandidate, RouteSelector
from hydra_orch.core.run_service import RunService
from hydra_orch.engine.decomposer import LOCKED_DEPENDENCY_MANIFESTS
from hydra_orch.model import (
    CheckSpec, ContractViolation, ExecutionModel, HandoffCheckpoint, Identifier,
    IntegrationStatus, ProcessStatus, RelativePath, ReviewDecision, RunSpec,
    TaskResult, TaskSpec, TaskStatus, ToolEffect,
)


def _covers(owner: str, path: str) -> bool:
    """Conservative literal-prefix containment; arbitrary glob implication is unsafe."""
    return path == owner or (owner.endswith('/**') and path.startswith(owner[:-2]))


def _state_hash(path: Path, base_sha: str) -> str:
    digest = hashlib.sha256(subprocess.run(['git', 'diff', '--binary', '--no-ext-diff', base_sha],
        cwd=path, capture_output=True, check=True).stdout)
    names = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'],
        cwd=path, capture_output=True, check=True).stdout
    for name in sorted(n for n in names.split(b'\0') if n):
        file = path / name.decode('utf-8')
        if file.is_symlink() or not file.is_file():
            raise ContractViolation('handoff_invalid', 'Untracked handoff files must be regular files')
        digest.update(name + b'\0' + file.read_bytes() + b'\0')
    return digest.hexdigest()


def _git_text(path: Path, *args: str) -> str:
    return subprocess.run(['git', *args], cwd=path, capture_output=True, text=True, check=True).stdout


class TaskOwnership(ExecutionModel):
    task_id: Identifier
    paths: tuple[RelativePath, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def literal_roots(self):
        if any(any(char in (p[:-3] if p.endswith('/**') else p) for char in '*?[') for p in self.paths):
            raise ValueError('Ownership must use literal file paths or literal directory/** roots')
        return self


class CommandBinding(ExecutionModel):
    route_id: Identifier
    # Arguments after the executable certified by AgentRegistry. No shell.
    args: tuple[str, ...] = Field(min_length=1)


class OrchestrationPlan(ExecutionModel):
    run: RunSpec
    profile_id: Identifier
    repository_id: Identifier
    routes: tuple[RouteCandidate, ...] = Field(min_length=1)
    commands: tuple[CommandBinding, ...] = Field(min_length=1)
    ownership: tuple[TaskOwnership, ...] = Field(min_length=1)
    foundation_task_id: Optional[Identifier] = None
    foundation_checks: tuple[CheckSpec, ...] = ()
    quota_wait_seconds: float = Field(default=0, ge=0, le=300, allow_inf_nan=False)
    quota_poll_seconds: float = Field(default=1, gt=0, le=30, allow_inf_nan=False)

    @model_validator(mode='after')
    def coherent(self):
        tasks = {t.task_id: t for t in self.run.tasks}
        owners = {o.task_id: o.paths for o in self.ownership}
        bindings = {b.route_id: b for b in self.commands}
        if len(owners) != len(self.ownership) or set(owners) != set(tasks):
            raise ValueError('Every task requires unique ownership')
        if (len(bindings) != len(self.commands) or set(bindings) != {r.route_id for r in self.routes}
                or len({r.route_id for r in self.routes}) != len(self.routes)):
            raise ValueError('Routes require unique command bindings')
        for route in self.routes:
            if route.mode != 'direct':
                raise ValueError('Gateway inference has no certified workspace execution transport')
            if route.model_ref not in bindings[route.route_id].args:
                raise ValueError('CLI arguments must explicitly bind the selected model')
        for task in tasks.values():
            if any(not any(_covers(root, path) for root in owners[task.task_id]) for path in task.allowed_paths):
                raise ValueError('Task paths must be contained in declared ownership')
        if self.run.orchestration_mode == 'swarm':
            foundation = tasks.get(self.foundation_task_id)
            if foundation is None or foundation.dependencies or not self.foundation_checks:
                raise ValueError('Swarm requires one independent foundation and executable checks')
            workers = [t for t in self.run.tasks if t.task_id != foundation.task_id]
            if not workers or any(t.dependencies != (foundation.task_id,) for t in workers):
                raise ValueError('Every Wave 1 task must depend on the foundation')
            for i, task in enumerate(workers):
                for other in workers[i + 1:]:
                    if any(_covers(a, b) or _covers(b, a) for a in owners[task.task_id] for b in owners[other.task_id]):
                        raise ValueError('Wave 1 ownership overlaps')
        elif self.foundation_task_id is not None or self.foundation_checks:
            raise ValueError('Foundation settings belong to swarm mode')
        if redact(self.model_dump(mode='json')) != self.model_dump(mode='json'):
            raise ValueError('Plans cannot contain raw credentials')
        return self


class OrchestrationReport(ExecutionModel):
    run_id: Identifier
    status: Literal['needs_review', 'blocked', 'ready_to_integrate', 'succeeded', 'failed']
    accepted_tasks: tuple[Identifier, ...] = ()
    reason: str = ''
    result_sha: Optional[str] = None


Reviewer = Callable[[TaskResult], Awaitable[Optional[ReviewDecision]]]
HandoffReconciler = Callable[[HandoffCheckpoint], Awaitable[bool]]


class Orchestrator:
    def __init__(self, runs: RunService, profiles: ProfileService, routes: RouteSelector):
        if runs.store is not profiles.store or routes.store is not runs.store or routes.agents is not profiles.agents:
            raise ValueError('Orchestration requires shared canonical services')
        self.runs, self.profiles, self.routes, self.store = runs, profiles, routes, runs.store

    async def _claim(self, plan: OrchestrationPlan) -> str:
        """Durable single-coordinator lease. Crash recovery requires reconciliation."""
        token = new_id()
        digest = hashlib.sha256(canonical_json(plan.model_dump(mode='json')).encode()).hexdigest()
        async with self.store._connect() as db:
            async with self.store._transaction(db):
                old = await (await db.execute("SELECT * FROM commands WHERE scope='orchestration' AND idempotency_key=?", (plan.run.run_id,))).fetchone()
                if old is not None:
                    if old['request_hash'] != digest:
                        raise ContractViolation('plan_changed', 'A run cannot change its persisted orchestration plan')
                    if old['status'] == 'pending':
                        raise ContractViolation('coordinator_active', 'Coordinator is active or requires crash reconciliation')
                    state = json.loads(old['response_json'])
                    state['token'] = token
                    await db.execute("UPDATE commands SET status='pending',response_json=?,updated_at=datetime('now') WHERE id=?", (json.dumps(state), old['id']))
                else:
                    await self.store._record_command_in_tx(db, scope='orchestration', idempotency_key=plan.run.run_id,
                        request_hash=digest, run_id=plan.run.run_id, status='pending',
                        response_payload={'token': token, 'started_at': datetime.now(timezone.utc).isoformat(), 'plan': plan.model_dump(mode='json')})
        return token

    async def _release(self, run_id: str, token: str):
        async with self.store._connect() as db:
            await db.execute("""UPDATE commands SET status='completed',updated_at=datetime('now')
                WHERE scope='orchestration' AND idempotency_key=? AND json_extract(response_json,'$.token')=?""", (run_id, token))

    async def _seconds_left(self, run: RunSpec, profile: ProfileDefinition) -> float:
        async with self.store._connect() as db:
            row = await (await db.execute("SELECT response_json FROM commands WHERE scope='orchestration' AND idempotency_key=?", (run.run_id,))).fetchone()
        started = datetime.fromisoformat(json.loads(row[0])['started_at'])
        return min(run.budget_policy.max_wall_seconds, profile.resource_limits.max_wall_seconds) - (datetime.now(timezone.utc) - started).total_seconds()

    async def _review(self, result: TaskResult, reviewer: Optional[Reviewer]) -> TaskResult:
        if result.task_status != TaskStatus.READY_FOR_REVIEW or reviewer is None:
            return result
        decision = await reviewer(result)
        if decision is None:
            return result
        if decision.result_id != result.result_id:
            raise ContractViolation('review_mismatch', 'Reviewer returned a decision for another result')
        return await self.runs.review_task_result(result.run_id, result.result_id, actor=decision.actor,
            decision=decision.decision, reason=decision.reason, expected_revision=decision.expected_revision)

    async def _admit(self, plan, profile, principal_id):
        await self.profiles.verify_discovered_components(profile, principal_id=principal_id)
        repository = await self.profiles.workspaces.resolve_repository(plan.repository_id, principal_id=principal_id, scope='execute')
        grants = json.loads(repository['allowed_paths_json'])
        if any(not any(_covers(grant, path) for grant in grants) for task in plan.run.tasks for path in task.allowed_paths):
            raise ContractViolation('scope_violation', 'Task contract exceeds current repository paths')
        # Validate the pinned configuration, even if the editable profile changed.
        await self.profiles.agents.resolve_capabilities(profile.agent_ref)
        await self.profiles.agents.resolve_capabilities(profile.executor_ref, required=profile.required_capabilities)
        async with self.store._connect() as db:
            if profile.memory_policy.enabled:
                consent = await (await db.execute('SELECT * FROM consent_records WHERE id=?', (profile.memory_policy.consent_id,))).fetchone()
                if (consent is None or consent['status'] != 'granted' or consent['revoked_at'] is not None
                        or consent['principal_id'] != principal_id or consent['purpose'] != 'memory'
                        or consent['scope'] != f'project:{plan.run.project_id}'):
                    raise ContractViolation('consent_required', 'Pinned memory policy requires current matching consent')
            for table, refs in (('skill_definitions', profile.skills_refs), ('mcp_definitions', profile.mcp_refs)):
                for ref in refs:
                    row = await (await db.execute(f'SELECT * FROM {table} WHERE id=?', (ref,))).fetchone()
                    if row is not None:
                        await validate_profile_component(db, kind='skill' if table == 'skill_definitions' else 'mcp', ref=ref, row=row, required_capabilities=profile.required_capabilities)
                    trust = None
                    if row is not None and row['discovered_resource_id']:
                        trust = await (await db.execute('SELECT trust_status FROM discovered_resources WHERE id=?', (row['discovered_resource_id'],))).fetchone()
                    if row is None or row['discovered_resource_id'] and (trust is None or trust[0] not in {'approved', 'active'}):
                        raise ContractViolation('component_untrusted', 'Pinned component is missing or no longer approved')

    async def _checkpoint(self, task: TaskSpec, attempt, result: TaskResult):
        old = await self.store.get_handoff_checkpoint(attempt.attempt_id)
        if old is not None:
            return old
        ws = self.runs._get_git_workspace((await self.store.get_run(task.run_id))['spec'].repo_root)
        path = Path(attempt.workspace_path)
        sha = ws.resolve_commit_sha('HEAD', cwd=path)
        status = _git_text(path, 'status', '--porcelain=v1')
        changed = _git_text(path, 'diff', '--name-only', '-z', attempt.base_sha).split('\0')
        untracked = _git_text(path, 'ls-files', '--others', '--exclude-standard', '-z').split('\0')
        checkpoint = HandoffCheckpoint(checkpoint_id=new_id(), attempt_id=attempt.attempt_id,
            objective=task.objective, instructions=(task.model_dump_json(),),
            decisions=('Preserve source worktree; restore verified Git state into a new attempt', _state_hash(path, attempt.base_sha)),
            git_sha=sha, git_status=redact_text(status), affected_files=tuple(sorted(set(p for p in changed + untracked if p))),
            diff_artifact_ids=tuple(a.artifact_id for a in result.artifacts if a.kind == 'patch'),
            check_artifact_ids=tuple(a.artifact_id for a in result.artifacts if a.kind == 'check_output'),
            tools_executed=(ToolEffect(tool='worker_process', summary=f'{attempt.process_status.value}; exit={attempt.exit_code}', status='confirmed'),
                ToolEffect(tool='provider_tools', summary='No certified tool-effect telemetry available', status='unknown')),
            next_step='Reconcile unknown external effects, then repair within the same task scope and re-run all checks')
        return await self.store.save_handoff_checkpoint_atomic(checkpoint, task.run_id)

    async def _execute_task(self, plan, profile, task, base_sha, principal_id, reviewer, semaphore, handoff_reconciler):
        attempts = await self.store.list_attempts(task.task_id)
        previous = attempts[-1] if attempts else None
        if previous:
            if previous.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}:
                raise ContractViolation('attempt_active', 'An existing worker needs reconciliation')
            result = await self.store.get_result_by_attempt(previous.attempt_id)
            if result is None:
                raise ContractViolation('result_missing', 'Terminal worker has no canonical result')
            result = await self._review(result, reviewer)
            if result.task_status in {TaskStatus.ACCEPTED, TaskStatus.READY_FOR_REVIEW, TaskStatus.REJECTED, TaskStatus.CANCELLED}:
                return result
        limit = min(plan.run.budget_policy.max_attempts, profile.resource_limits.max_attempts, task.max_repair_attempts + 1)
        while len(attempts) < limit:
            await self._admit(plan, profile, principal_id)
            remaining = await self._seconds_left(plan.run, profile)
            if remaining <= 0:
                raise ContractViolation('wall_budget_exceeded', 'Orchestration wall-time budget exhausted')
            # Bounded polling in persistent mode never reserves a worker semaphore.
            deadline = asyncio.get_running_loop().time() + min(remaining, plan.quota_wait_seconds if plan.run.orchestration_mode == 'persistent' else 0)
            excluded = set()
            if previous is not None:
                excluded = {r.route_id for r in plan.routes if r.model_ref == previous.model}
            candidates = tuple(r for r in plan.routes if r.route_id not in excluded) or plan.routes
            while True:
                try:
                    decision = await self.routes.select(plan.run.run_id, candidates,
                        required_capabilities=tuple(set(task.required_capabilities + profile.required_capabilities)))
                    break
                except ContractViolation as exc:
                    delay = deadline - asyncio.get_running_loop().time()
                    if exc.code != 'no_eligible_route' or delay <= 0:
                        raise
                    await asyncio.sleep(min(delay, plan.quota_poll_seconds))
            selected = next(r for r in plan.routes if r.route_id == decision.selected_route)
            resolved = await self.profiles.agents.resolve_capabilities(selected.agent_id,
                required=tuple(set(task.required_capabilities + profile.required_capabilities)))
            if decision.execution_driver != task.assigned_executor:
                raise ContractViolation('executor_mismatch', 'Fallback driver requires a new immutable task contract')
            command = next(b for b in plan.commands if b.route_id == selected.route_id)
            checkpoint = None
            if previous is not None:
                checkpoint = await self._checkpoint(task, previous, result)
                if handoff_reconciler is None or not await handoff_reconciler(checkpoint):
                    return result
                # A changed source tree invalidates the handoff captured for that attempt.
                ws = self.runs._get_git_workspace(plan.run.repo_root)
                if (ws.resolve_commit_sha('HEAD', cwd=Path(previous.workspace_path)) != checkpoint.git_sha
                        or redact_text(_git_text(Path(previous.workspace_path), 'status', '--porcelain=v1')) != checkpoint.git_status
                        or _state_hash(Path(previous.workspace_path), previous.base_sha) != checkpoint.decisions[-1]):
                    raise ContractViolation('handoff_changed', 'Source worktree changed after checkpoint')
            forbidden = ()
            if plan.run.orchestration_mode == 'swarm' and task.task_id != plan.foundation_task_id:
                forbidden = tuple(LOCKED_DEPENDENCY_MANIFESTS) + tuple('**/' + p for p in LOCKED_DEPENDENCY_MANIFESTS)
            async with semaphore:
                await self._admit(plan, profile, principal_id)
                resolved = await self.profiles.agents.resolve_capabilities(selected.agent_id,
                    required=tuple(set(task.required_capabilities + profile.required_capabilities)))
                remaining = await self._seconds_left(plan.run, profile)
                if remaining <= 0:
                    raise ContractViolation('wall_budget_exceeded', 'Orchestration wall-time budget exhausted')
                # Includes subprocess cancellation/kill in WorkerRunner on timeout.
                outcome = await asyncio.wait_for(self.runs.execute_task_attempt(plan.run.run_id, task.task_id,
                    model=decision.model_ref, provider='local_cli', custom_command=(resolved.executable, *command.args),
                    prompt=task.objective + ('\nGit handoff checkpoint:\n' + checkpoint.model_dump_json() if checkpoint else ''),
                    forbidden_paths=forbidden, allow_retry_from_terminal=previous is not None,
                    execution_base_sha=base_sha, resume_from_attempt_id=previous.attempt_id if previous else None), timeout=remaining)
            result = await self._review(outcome.result, reviewer)
            if result.task_status != TaskStatus.FAILED:
                return result
            previous = outcome.attempt
            attempts = await self.store.list_attempts(task.task_id)
            # Scope/security failures require inspection; do not restore them automatically.
            if any(f.code in {'scope_violation', 'forbidden_file_modified', 'workspace_invalid'} or not f.retryable for f in result.failures):
                await self._checkpoint(task, previous, result)
                return result
        if previous is not None:
            await self._checkpoint(task, previous, result)
            return result
        raise ContractViolation('max_attempts_exceeded', 'Task attempt budget exhausted')

    async def _stage(self, plan, results, extra_checks=()):
        """Verified intermediate consolidation; never changes the operator checkout."""
        digest = hashlib.sha256(','.join(r.result_id for r in results).encode()).hexdigest()[:16]
        stage_id = f'stage_{plan.run.run_id}_{digest}'
        async with self.store._connect() as db:
            old = await (await db.execute('SELECT * FROM integrations WHERE id=?', (stage_id,))).fetchone()
            bases = tuple(r[0] for r in await (await db.execute("SELECT result_sha FROM integrations WHERE run_id=? AND status='integrated'", (plan.run.run_id,))).fetchall())
        if old is not None:
            if old['status'] != 'integrated':
                raise ContractViolation('stage_failed', 'Failed consolidation requires explicit repair')
            return old['result_sha']
        task_ids = {(await self.store.get_attempt(r.attempt_id)).task_id for r in results}
        checks = tuple(c for t in plan.run.tasks if t.task_id in task_ids for c in t.acceptance_criteria) + tuple(extra_checks)
        check_runner = self.runs._get_check_runner(plan.run.repo_root)
        async def check(path, sha, specs):
            return await check_runner.run_checks(run_id=plan.run.run_id, attempt_id=None, workspace_path=path,
                tested_sha=sha, checks=specs, scope_prefix=stage_id)
        outcome = await self.runs._get_git_workspace(plan.run.repo_root).integrate_results(run_id=plan.run.run_id,
            expected_base_sha=plan.run.base_sha, results=results, integration_id=stage_id,
            verified_base_shas=bases, post_merge_checks=checks, check_runner=check)
        if outcome.status != IntegrationStatus.INTEGRATED:
            raise ContractViolation('stage_failed', 'Consolidated checks or merge failed; evidence preserved')
        return outcome.result_sha

    async def execute(self, plan: OrchestrationPlan, *, principal_id: str, reviewer: Optional[Reviewer] = None,
                      handoff_reconciler: Optional[HandoffReconciler] = None, integrate: bool = False) -> OrchestrationReport:
        record = await self.store.get_run(plan.run.run_id)
        if record is None or record['spec'] != plan.run:
            raise ContractViolation('run_mismatch', 'Submit this immutable run before orchestration')
        if record['status'] in {'succeeded', 'failed', 'cancelled'}:
            raise ContractViolation('run_terminal', 'Run is already terminal')
        snapshot = await self.profiles.snapshot(plan.profile_id, plan.run.run_id, plan.repository_id, principal_id=principal_id)
        profile = ProfileDefinition.model_validate(snapshot.effective_config['profile'])
        if profile.orchestration_mode != plan.run.orchestration_mode:
            raise ContractViolation('mode_mismatch', 'Run and effective profile modes must match')
        grants = json.loads(snapshot.effective_config['repository']['allowed_paths_json'])
        if any(not any(_covers(grant, path) for grant in grants) for t in plan.run.tasks for path in t.allowed_paths):
            raise ContractViolation('scope_violation', 'Task contract exceeds registered repository paths')
        token = await self._claim(plan)
        accepted = {}
        semaphore = asyncio.Semaphore(min(plan.run.budget_policy.max_parallel_worktrees, profile.resource_limits.max_parallel_worktrees))
        try:
            pending = list(plan.run.tasks)
            base_sha = plan.run.base_sha
            if plan.run.orchestration_mode == 'swarm':
                foundation = next(t for t in pending if t.task_id == plan.foundation_task_id)
                pending.remove(foundation)
                result = await self._execute_task(plan, profile, foundation, base_sha, principal_id, reviewer, semaphore, handoff_reconciler)
                if result.task_status != TaskStatus.ACCEPTED:
                    return OrchestrationReport(run_id=plan.run.run_id, status='needs_review' if result.task_status == TaskStatus.READY_FOR_REVIEW else 'blocked', reason='Foundation requires accepted checks and review')
                accepted[foundation.task_id] = result
                base_sha = await self._stage(plan, list(accepted.values()), plan.foundation_checks)
            while pending:
                ready = [t for t in pending if set(t.dependencies) <= set(accepted)]
                if not ready:
                    raise ContractViolation('dependencies_blocked', 'No task has accepted dependencies')
                if plan.run.orchestration_mode != 'swarm':
                    ready = ready[:1]
                # Wait for every started task even if a sibling fails; no orphan workers.
                results = await asyncio.gather(*(self._execute_task(plan, profile, t, base_sha, principal_id, reviewer, semaphore, handoff_reconciler) for t in ready), return_exceptions=True)
                for task, result in zip(ready, results):
                    if isinstance(result, BaseException):
                        raise result
                    if result.task_status == TaskStatus.ACCEPTED:
                        accepted[task.task_id] = result
                        pending.remove(task)
                incomplete = [r for r in results if r.task_status != TaskStatus.ACCEPTED]
                if incomplete:
                    return OrchestrationReport(run_id=plan.run.run_id, status='needs_review' if any(r.task_status == TaskStatus.READY_FOR_REVIEW for r in incomplete) else 'blocked', accepted_tasks=tuple(accepted), reason='Unaccepted results preserved for review or repair')
                if plan.run.orchestration_mode != 'swarm' and pending:
                    base_sha = await self._stage(plan, list(accepted.values()))
            if not integrate:
                return OrchestrationReport(run_id=plan.run.run_id, status='ready_to_integrate', accepted_tasks=tuple(accepted))
            outcome = await self.runs.integrate_run(plan.run.run_id, cleanup_on_success=False)
            return OrchestrationReport(run_id=plan.run.run_id, status='succeeded' if outcome.status == IntegrationStatus.INTEGRATED else 'failed', accepted_tasks=tuple(accepted), result_sha=outcome.result_sha)
        finally:
            await self._release(plan.run.run_id, token)
