"""Chat DTOs and versioned, in-memory execution contracts for Hydra Orchestrator."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Dict, List, Literal, Optional, Union, TypeVar
from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, JsonValue,
    StringConstraints, field_validator, model_validator,
)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[str] = ""
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatCompletionRequest(BaseModel):
    model: str = "hydra-default"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None
    
    # Custom Hydra-Orch metadata / overrides passed by agent or header
    mode: Optional[Literal["swarm", "relay", "persistent"]] = None
    preferred_provider: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None


class ChatChoiceDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: ChatChoiceDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]
    usage: Optional[UsageInfo] = Field(
        default_factory=lambda: UsageInfo(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    )


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "hydra-orch"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelCard]


# Execution contracts deliberately do not import transports or touch disk.
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GitSha = Annotated[str, StringConstraints(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


def _relative_path(value: str) -> str:
    value = value.replace("\\", "/")
    if (not value or "\x00" in value or value == "." or PurePosixPath(value).is_absolute()
            or PureWindowsPath(value).drive or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("Expected a workspace-relative path without traversal")
    return value


def _absolute_path(value: str) -> str:
    if ("\x00" in value or not (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())
            or ".." in value.replace("\\", "/").split("/")):
        raise ValueError("Expected an absolute path without traversal")
    return value


RelativePath = Annotated[str, AfterValidator(_relative_path)]
AbsolutePath = Annotated[str, AfterValidator(_absolute_path)]
UtcTimestamp = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(timezone.utc))]


def _command(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value[0].strip() or any("\x00" in argument for argument in value):
        raise ValueError("Command requires a nonempty executable and arguments without NUL")
    return value


Command = Annotated[tuple[str, ...], Field(min_length=1), AfterValidator(_command)]


class ContractViolation(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class InvalidTransitionError(ContractViolation):
    def __init__(self, current: Enum, target: Enum):
        super().__init__("invalid_transition", f"Invalid {type(current).__name__} transition: {current.value} -> {target.value}")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    REVIEWING = "reviewing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    EXITED = "exited"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    CRASHED = "crashed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    NEEDS_CONTEXT = "needs_context"
    BLOCKED = "blocked"
    FAILED = "failed"
    READY_FOR_REVIEW = "ready_for_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class IntegrationStatus(str, Enum):
    NOT_INTEGRATED = "not_integrated"
    INTEGRATING = "integrating"
    INTEGRATED = "integrated"
    CONFLICTED = "conflicted"
    FAILED = "failed"
    DISCARDED = "discarded"


_TRANSITIONS = {
    RunStatus: {
        "queued": {"running", "failed", "cancelled"},
        "running": {"waiting", "reviewing", "failed", "cancelled"},
        "waiting": {"running", "failed", "cancelled"},
        "reviewing": {"running", "succeeded", "failed", "cancelled"},
    },
    ProcessStatus: {
        "queued": {"running", "cancelled", "crashed"},
        "running": {"exited", "timed_out", "cancelled", "crashed"},
    },
    TaskStatus: {
        "pending": {"running", "blocked", "failed", "cancelled"},
        "running": {"needs_context", "blocked", "failed", "ready_for_review", "cancelled"},
        "needs_context": {"running", "blocked", "failed", "cancelled"},
        "blocked": {"running", "failed", "cancelled"},
        "ready_for_review": {"accepted", "rejected", "cancelled"},
    },
    IntegrationStatus: {
        "not_integrated": {"integrating", "discarded"},
        "integrating": {"integrated", "conflicted", "failed"},
        "conflicted": {"integrating", "discarded"},
        "failed": {"discarded"},
    },
}
Status = TypeVar("Status", RunStatus, ProcessStatus, TaskStatus, IntegrationStatus)


def transition_status(current: Status, target: Status) -> Status:
    """Validate adjacency only; service commands must also enforce their guards."""
    if type(current) is not type(target) or type(current) not in _TRANSITIONS:
        raise TypeError("Transitions require states from the same execution domain")
    if target.value not in _TRANSITIONS[type(current)].get(current.value, set()):
        raise InvalidTransitionError(current, target)
    return target


class ExecutionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True, hide_input_in_errors=True)
    schema_version: Literal["1.0"] = "1.0"


class ExecutorCapability(str, Enum):
    INFERENCE = "inference"
    WORKSPACE_EXECUTION = "workspace_execution"
    TOOL_EXECUTION = "tool_execution"
    NATIVE_RESUME = "native_resume"
    CANCEL_PROCESS_TREE = "cancel_process_tree"
    FILESYSTEM_SANDBOX = "filesystem_sandbox"
    NETWORK_ISOLATION = "network_isolation"


class ExecutorCapabilities(ExecutionModel):
    executor_id: Identifier
    capabilities: tuple[ExecutorCapability, ...] = ()

    def require(self, required: tuple[ExecutorCapability, ...]) -> None:
        if set(required) - set(self.capabilities):
            raise ContractViolation("capability_mismatch", "Executor lacks required capabilities")


class BudgetPolicy(ExecutionModel):
    max_usd: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    max_tokens_in: Optional[int] = Field(default=None, ge=0, strict=True)
    max_tokens_out: Optional[int] = Field(default=None, ge=0, strict=True)
    max_wall_seconds: int = Field(default=1800, gt=0, strict=True)
    max_attempts: int = Field(default=3, gt=0, strict=True)
    max_parallel_worktrees: int = Field(default=1, gt=0, strict=True)
    alert_threshold_pct: float = Field(default=80, ge=50, le=99, allow_inf_nan=False)


class CheckSpec(ExecutionModel):
    check_id: Identifier
    command: Command
    cwd: Optional[RelativePath] = None
    description: str = ""

    @field_validator("cwd", mode="before")
    @classmethod
    def workspace_root(cls, value: Any) -> Any:
        return None if value == "." else value


class TaskSpec(ExecutionModel):
    task_id: Identifier
    run_id: Identifier
    objective: NonEmpty
    assigned_executor: Identifier
    required_capabilities: tuple[ExecutorCapability, ...] = (ExecutorCapability.WORKSPACE_EXECUTION,)
    acceptance_criteria: tuple[CheckSpec, ...] = Field(min_length=1)
    allowed_paths: tuple[RelativePath, ...] = Field(min_length=1)
    dependencies: tuple[Identifier, ...] = ()
    contract_sha256: Optional[Sha256] = None
    timeout_seconds: int = Field(default=300, ge=1, le=3600, strict=True)
    max_repair_attempts: int = Field(default=2, ge=0, le=5, strict=True)

    @model_validator(mode="after")
    def validate_identity(self) -> TaskSpec:
        if self.task_id in self.dependencies or len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("Dependencies must be unique and cannot reference the task itself")
        check_ids = [check.check_id for check in self.acceptance_criteria]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("Check IDs must be unique within a task")
        return self


class RunSpec(ExecutionModel):
    run_id: Identifier
    project_id: Identifier
    objective: NonEmpty
    repo_root: AbsolutePath
    base_sha: GitSha
    base_branch: NonEmpty
    orchestration_mode: Literal["swarm", "relay", "persistent"] = "relay"
    budget_policy: BudgetPolicy = Field(default_factory=BudgetPolicy)
    integration_policy: Literal["explicit_review"] = "explicit_review"
    idempotency_key: Annotated[str, StringConstraints(min_length=16, max_length=64)]
    tasks: tuple[TaskSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_graph(self) -> RunSpec:
        ids = {task.task_id for task in self.tasks}
        if len(ids) != len(self.tasks) or any(task.run_id != self.run_id for task in self.tasks):
            raise ValueError("Tasks must have unique IDs and belong to this run")
        pending = {task.task_id: set(task.dependencies) for task in self.tasks}
        if any(dependencies - ids for dependencies in pending.values()):
            raise ValueError("Unknown task dependency")
        while pending:
            ready = {key for key, dependencies in pending.items() if not dependencies}
            if not ready:
                raise ValueError("Task dependencies contain a cycle")
            pending = {key: dependencies - ready for key, dependencies in pending.items() if key not in ready}
        return self


class TaskAttempt(ExecutionModel):
    attempt_id: Identifier
    task_id: Identifier
    run_id: Identifier
    ordinal: int = Field(ge=1, strict=True)
    executor_id: Identifier
    provider: NonEmpty
    model: NonEmpty
    base_sha: GitSha
    workspace_path: Optional[AbsolutePath] = None
    provider_session: Optional[NonEmpty] = None
    process_status: ProcessStatus = ProcessStatus.QUEUED
    exit_code: Optional[int] = Field(default=None, strict=True)
    started_at: Optional[UtcTimestamp] = None
    finished_at: Optional[UtcTimestamp] = None
    exit_reason: Optional[NonEmpty] = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> TaskAttempt:
        active = self.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}
        if active and (self.finished_at is not None or self.exit_code is not None or self.exit_reason is not None):
            raise ValueError("Active processes cannot have terminal metadata")
        if self.process_status == ProcessStatus.QUEUED and self.started_at is not None:
            raise ValueError("Queued process has not started")
        if self.process_status in {ProcessStatus.RUNNING, ProcessStatus.EXITED, ProcessStatus.TIMED_OUT} and self.started_at is None:
            raise ValueError("Started process requires started_at")
        if not active and (self.finished_at is None or self.exit_reason is None):
            raise ValueError("Terminal process requires finished_at and exit_reason")
        if self.process_status == ProcessStatus.EXITED and self.exit_code is None:
            raise ValueError("Exited process requires an exit code")
        if self.started_at is not None and self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("Process cannot finish before it starts")
        return self


class Artifact(ExecutionModel):
    artifact_id: Identifier
    run_id: Identifier
    attempt_id: Optional[Identifier] = None
    relative_path: RelativePath
    kind: Literal["patch", "check_output", "log", "handoff", "export", "report", "pr_package"]
    sha256: Sha256
    size_bytes: int = Field(ge=0, strict=True)


class CheckResult(ExecutionModel):
    check_id: Identifier
    command: Command
    cwd: Optional[RelativePath] = None
    tested_sha: GitSha
    exit_code: int = Field(strict=True)
    duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    stdout_artifact_id: Identifier
    stderr_artifact_id: Identifier

    @field_validator("cwd", mode="before")
    @classmethod
    def workspace_root(cls, value: Any) -> Any:
        return None if value == "." else value


class ReviewDecision(ExecutionModel):
    result_id: Identifier
    actor: NonEmpty
    decision: Literal["accepted", "rejected"]
    reason: NonEmpty
    expected_revision: int = Field(ge=1, strict=True)
    created_at: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))


class FailureDetail(ExecutionModel):
    code: Identifier
    message: NonEmpty
    retryable: bool = False


class TaskResult(ExecutionModel):
    result_id: Identifier
    attempt_id: Identifier
    run_id: Identifier
    base_sha: GitSha
    process_status: ProcessStatus
    exit_code: Optional[int] = Field(default=None, strict=True)
    task_status: TaskStatus
    summary: NonEmpty
    simulated: bool = Field(default=False, strict=True)
    revision: int = Field(default=1, ge=1, strict=True)
    patch_commit_sha: Optional[GitSha] = None
    patch_artifact_id: Optional[Identifier] = None
    changed_files: tuple[RelativePath, ...] = ()
    checks_executed: tuple[CheckResult, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    failures: tuple[FailureDetail, ...] = ()
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"
    review: Optional[ReviewDecision] = None

    @model_validator(mode="after")
    def validate_evidence(self) -> TaskResult:
        if self.task_status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            raise ValueError("A terminal process cannot produce an active task result")
        if self.process_status in {ProcessStatus.QUEUED, ProcessStatus.RUNNING}:
            raise ValueError("A result requires a terminal process")
        if self.process_status == ProcessStatus.EXITED and self.exit_code is None:
            raise ValueError("Exited process requires an exit code")
        artifacts = {artifact.artifact_id: artifact for artifact in self.artifacts}
        if len(artifacts) != len(self.artifacts):
            raise ValueError("Artifact IDs must be unique")
        if any(a.run_id != self.run_id or a.attempt_id != self.attempt_id for a in self.artifacts):
            raise ValueError("Artifact belongs to another run or attempt")
        if self.patch_artifact_id is not None and (self.patch_artifact_id not in artifacts
                or artifacts[self.patch_artifact_id].kind != "patch"):
            raise ValueError("Patch must reference a patch artifact")
        check_ids = [check.check_id for check in self.checks_executed]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("Check result IDs must be unique")
        for check in self.checks_executed:
            if any(key not in artifacts or artifacts[key].kind != "check_output"
                   for key in (check.stdout_artifact_id, check.stderr_artifact_id)):
                raise ValueError("Check outputs must reference check_output artifacts")
        if self.task_status in {TaskStatus.READY_FOR_REVIEW, TaskStatus.ACCEPTED}:
            if (self.simulated or self.process_status != ProcessStatus.EXITED or self.exit_code != 0
                    or not self.changed_files or not self.patch_commit_sha or self.patch_commit_sha == self.base_sha
                    or not self.patch_artifact_id
                    or not self.checks_executed or any(check.exit_code != 0 for check in self.checks_executed)
                    or self.failures):
                raise ValueError("Reviewable results require real changes and passing checks")
        reviewed = self.task_status in {TaskStatus.ACCEPTED, TaskStatus.REJECTED}
        if reviewed:
            if (self.review is None or self.review.result_id != self.result_id
                    or self.review.decision != self.task_status.value
                    or self.review.expected_revision != self.revision - 1):
                raise ValueError("Reviewed result requires a matching explicit review and revision")
        elif self.review is not None:
            raise ValueError("Unreviewed result cannot contain a review")
        return self


def validate_result(task: TaskSpec, attempt: TaskAttempt, result: TaskResult, *, require_acceptance: bool = True) -> None:
    """Validate declared attribution; filesystem/hash verification belongs to T06."""
    if (attempt.task_id != task.task_id or attempt.run_id != task.run_id
            or attempt.executor_id != task.assigned_executor or result.attempt_id != attempt.attempt_id
            or result.run_id != task.run_id or result.base_sha != attempt.base_sha
            or result.process_status != attempt.process_status or result.exit_code != attempt.exit_code):
        raise ContractViolation("identity_mismatch", "Task, attempt and result do not describe the same execution")
    expected = {check.check_id: check for check in task.acceptance_criteria}
    observed = {check.check_id: check for check in result.checks_executed}
    if set(observed) - set(expected) or (require_acceptance and set(expected) != set(observed)):
        raise ContractViolation("checks_mismatch", "Result must account for every required check")
    for key, check in observed.items():
        spec = expected[key]
        if (check.command != spec.command or check.cwd != spec.cwd
                or check.tested_sha != result.patch_commit_sha):
            raise ContractViolation("check_evidence_mismatch", "Check command, cwd or tested SHA differs from the task/result")


def review_result(task: TaskSpec, attempt: TaskAttempt, result: TaskResult, decision: ReviewDecision) -> TaskResult:
    if decision.result_id != result.result_id or decision.expected_revision != result.revision:
        raise ContractViolation("stale_review", "Review targets a different result or revision")
    transition_status(result.task_status, TaskStatus(decision.decision))
    validate_result(task, attempt, result, require_acceptance=decision.decision == "accepted")
    return TaskResult.model_validate({
        **result.model_dump(), "task_status": decision.decision,
        "revision": result.revision + 1, "review": decision,
    })


def assert_integrable(task: TaskSpec, attempt: TaskAttempt, result: TaskResult) -> None:
    if result.task_status != TaskStatus.ACCEPTED or result.simulated:
        raise ContractViolation("result_not_accepted", "Integration requires an accepted real result")
    validate_result(task, attempt, result)


class RunEvent(ExecutionModel):
    seq: int = Field(ge=1, strict=True)
    run_id: Identifier
    correlation_id: Identifier
    task_id: Optional[Identifier] = None
    attempt_id: Optional[Identifier] = None
    session_id: Optional[Identifier] = None
    thread_id: Optional[Identifier] = None
    timestamp: UtcTimestamp = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: Literal[
        "run.created", "run.started", "run.waiting", "run.resumed", "run.finished", "run.cancelled",
        "task.queued", "task.started", "task.needs_context", "task.needs_approval", "task.ready_for_review",
        "task.accepted", "task.rejected", "task.completed", "task.failed", "task.cancelled",
        "attempt.started", "attempt.provider_selected", "attempt.rate_limited", "attempt.handoff_created", "attempt.finished",
        "artifact.created", "check.started", "check.finished", "merge.started", "merge.completed", "merge.conflicted",
        "heartbeat", "budget.alerted", "budget.frozen", "profile.snapshot_created",
        "session.created", "session.state_changed", "thread.created", "thread.state_changed", "thread.message",
        "metric.sampled",
        "hitl.requested", "hitl.resolved",
        "route.selected", "route.rejected",
    ]
    redacted_payload: dict[str, JsonValue] = Field(default_factory=dict)


class ToolEffect(ExecutionModel):
    tool: NonEmpty
    summary: NonEmpty
    status: Literal["confirmed", "unknown"]
    artifact_ids: tuple[Identifier, ...] = ()


class HandoffCheckpoint(ExecutionModel):
    checkpoint_id: Identifier
    attempt_id: Identifier
    objective: NonEmpty
    instructions: tuple[NonEmpty, ...] = Field(min_length=1)
    decisions: tuple[NonEmpty, ...] = ()
    git_sha: GitSha
    git_status: str
    affected_files: tuple[RelativePath, ...] = ()
    diff_artifact_ids: tuple[Identifier, ...] = ()
    check_artifact_ids: tuple[Identifier, ...] = ()
    tools_executed: tuple[ToolEffect, ...] = ()
    partial_output: str = ""
    next_step: NonEmpty
