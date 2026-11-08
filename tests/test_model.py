import pytest
from datetime import datetime, timedelta, timezone
from enum import Enum
from pydantic import ValidationError
from hydra_orch.model import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChunk,
    Artifact, BudgetPolicy, CheckResult, CheckSpec, ContractViolation, ExecutorCapabilities,
    ExecutorCapability, FailureDetail, HandoffCheckpoint, IntegrationStatus, InvalidTransitionError,
    ModelCard, ModelListResponse, ProcessStatus, ReviewDecision, RunEvent, RunSpec, RunStatus,
    TaskAttempt, TaskResult, TaskSpec, TaskStatus, ToolEffect, assert_integrable,
    review_result, transition_status, validate_result,
)


def test_chat_message_schema():
    msg = ChatMessage(role="user", content="Build a barbershop SaaS app")
    assert msg.role == "user"
    assert msg.content == "Build a barbershop SaaS app"


def test_chat_completion_request_modes():
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Hello")],
        mode="swarm",
    )
    assert req.mode == "swarm"
    assert req.stream is False


BASE_SHA, PATCH_SHA = "a" * 40, "b" * 40
NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def task_data():
    return {
        "task_id": "task-1", "run_id": "run-1", "objective": "Fix the sum function",
        "assigned_executor": "codex", "allowed_paths": ["src/sum.py", "tests/test_sum.py"],
        "acceptance_criteria": [{"check_id": "unit", "command": ["python", "-m", "pytest"]}],
    }


@pytest.fixture
def run_data(task_data):
    return {
        "run_id": "run-1", "project_id": "project-1", "objective": "Fix the sum function",
        "repo_root": "C:/workspace/project", "base_sha": BASE_SHA, "base_branch": "main",
        "idempotency_key": "unique-request-0001", "tasks": [task_data],
    }


@pytest.fixture
def attempt_data():
    return {
        "attempt_id": "attempt-1", "task_id": "task-1", "run_id": "run-1", "ordinal": 1,
        "executor_id": "codex", "provider": "codex", "model": "test-model", "base_sha": BASE_SHA,
        "workspace_path": "C:/workspace/worktree", "process_status": "exited", "exit_code": 0,
        "started_at": NOW, "finished_at": NOW + timedelta(seconds=1), "exit_reason": "completed",
    }


@pytest.fixture
def result_data():
    def artifact(key, kind, path):
        return {"artifact_id": key, "run_id": "run-1", "attempt_id": "attempt-1",
                "relative_path": path, "kind": kind, "sha256": "c" * 64, "size_bytes": 4}

    return {
        "result_id": "result-1", "attempt_id": "attempt-1", "run_id": "run-1", "base_sha": BASE_SHA,
        "process_status": "exited", "exit_code": 0, "task_status": "ready_for_review", "summary": "Sum fixed",
        "patch_commit_sha": PATCH_SHA, "patch_artifact_id": "patch", "changed_files": ["src/sum.py"],
        "checks_executed": [{"check_id": "unit", "command": ["python", "-m", "pytest"], "tested_sha": PATCH_SHA,
                             "exit_code": 0, "duration_seconds": 0.5,
                             "stdout_artifact_id": "stdout", "stderr_artifact_id": "stderr"}],
        "artifacts": [artifact("patch", "patch", "result/diff.patch"),
                      artifact("stdout", "check_output", "check/stdout.txt"),
                      artifact("stderr", "check_output", "check/stderr.txt")],
    }


def test_chat_response_models_remain_compatible():
    message = ChatMessage(role="assistant", content="Hello")
    response = ChatCompletionResponse(model="hydra-default", choices=[{"message": message}])
    chunk = ChatCompletionChunk(model="hydra-default", choices=[{"delta": {"content": "Hello"}}])
    models = ModelListResponse(data=[ModelCard(id="hydra-default")])
    assert response.id.startswith("chatcmpl-") and chunk.id.startswith("chatcmpl-")
    assert response.usage.total_tokens == 0
    assert models.data[0].id == "hydra-default"
    assert response.created > 0 and chunk.created > 0


def test_execution_specs_round_trip_and_nested_immutability(run_data):
    run = RunSpec.model_validate(run_data)
    assert RunSpec.model_validate_json(run.model_dump_json()) == run
    assert run.orchestration_mode == "relay"
    assert run.integration_policy == "explicit_review"
    assert run.tasks[0].acceptance_criteria[0].command == ("python", "-m", "pytest")
    with pytest.raises(ValidationError, match="frozen"):
        run.base_sha = PATCH_SHA
    with pytest.raises(ValidationError, match="frozen"):
        run.tasks[0].objective = "Changed"
    with pytest.raises(TypeError):
        run.tasks[0].allowed_paths[0] = "other.py"
    assert RunSpec.model_json_schema()["properties"]["schema_version"]["const"] == "1.0"


@pytest.mark.parametrize("change", [
    {"schema_version": "2.0"}, {"run_id": "bad/id"}, {"base_sha": "abc"},
    {"objective": " "}, {"idempotency_key": "short"}, {"integration_policy": "automatic"},
    {"repo_root": "relative/project"}, {"repo_root": "C:/workspace/../other"},
    {"extra": True}, {"tasks": []},
])
def test_invalid_run_schema_rejected(run_data, change):
    with pytest.raises(ValidationError):
        RunSpec.model_validate({**run_data, **change})


@pytest.mark.parametrize("path", ["../secret", "/outside", "C:/outside", "C:relative", "a/../b", "a//b", ".", "a\x00b"])
def test_invalid_workspace_paths_rejected(task_data, path):
    with pytest.raises(ValidationError):
        TaskSpec.model_validate({**task_data, "allowed_paths": [path]})


def test_windows_paths_and_posix_root_are_lexically_supported(task_data, run_data):
    task = TaskSpec.model_validate({**task_data, "allowed_paths": ["src\\sum.py", "tests/**/*.py"]})
    assert task.allowed_paths == ("src/sum.py", "tests/**/*.py")
    assert RunSpec.model_validate({**run_data, "repo_root": "/workspace/project", "base_sha": "d" * 64})


@pytest.mark.parametrize("change", [
    {"dependencies": ["task-1"]}, {"dependencies": ["other", "other"]},
    {"acceptance_criteria": []}, {"allowed_paths": []}, {"timeout_seconds": 0},
    {"timeout_seconds": True}, {"max_repair_attempts": 6}, {"contract_sha256": "bad"},
    {"acceptance_criteria": [{"check_id": "unit", "command": ["pytest"]}] * 2},
])
def test_invalid_task_contracts_rejected(task_data, change):
    with pytest.raises(ValidationError):
        TaskSpec.model_validate({**task_data, **change})


def test_run_rejects_invalid_dependency_graphs(run_data, task_data):
    for tasks in ([task_data, task_data], [{**task_data, "run_id": "other"}],
                  [{**task_data, "dependencies": ["missing"]}],
                  [{**task_data, "dependencies": ["task-2"]}, {**task_data, "task_id": "task-2", "dependencies": ["task-1"]}]):
        with pytest.raises(ValidationError):
            RunSpec.model_validate({**run_data, "tasks": tasks})
    run = RunSpec.model_validate({**run_data, "tasks": [
        {**task_data, "task_id": "task-2", "dependencies": ["task-1"]}, task_data,
    ]})
    assert len(run.tasks) == 2


@pytest.mark.parametrize("command", [[], "pytest -q", [" "], ["python", "bad\x00arg"]])
def test_check_argv_rejects_invalid_commands(command):
    with pytest.raises(ValidationError):
        CheckSpec(check_id="unit", command=command)


def test_command_arguments_preserve_spaces_and_empty_values():
    check = CheckSpec(check_id="unit", command=["python", "-c", " print('hi') ", ""], cwd=".")
    assert check.command[-2:] == (" print('hi') ", "")
    assert check.cwd is None


@pytest.mark.parametrize("limits", [
    {"max_usd": -1}, {"max_usd": float("inf")}, {"max_tokens_in": -1},
    {"max_tokens_out": True}, {"max_wall_seconds": 0}, {"max_attempts": 0},
    {"max_parallel_worktrees": 0}, {"alert_threshold_pct": 100},
])
def test_budget_rejects_invalid_limits(limits):
    with pytest.raises(ValidationError):
        BudgetPolicy(**limits)


def test_capability_requirements_are_explicit():
    capabilities = ExecutorCapabilities(executor_id="test", capabilities=["inference"])
    capabilities.require((ExecutorCapability.INFERENCE,))
    with pytest.raises(ContractViolation) as exc:
        capabilities.require((ExecutorCapability.WORKSPACE_EXECUTION,))
    assert exc.value.code == "capability_mismatch"


EDGES = {
    RunStatus: {"queued": {"running", "failed", "cancelled"}, "running": {"waiting", "reviewing", "failed", "cancelled"},
                "waiting": {"running", "failed", "cancelled"}, "reviewing": {"running", "succeeded", "failed", "cancelled"}},
    ProcessStatus: {"queued": {"running", "cancelled", "crashed"}, "running": {"exited", "timed_out", "cancelled", "crashed"}},
    TaskStatus: {"pending": {"running", "blocked", "failed", "cancelled"},
                 "running": {"needs_context", "blocked", "failed", "ready_for_review", "cancelled"},
                 "needs_context": {"running", "blocked", "failed", "cancelled"},
                 "blocked": {"running", "failed", "cancelled"}, "ready_for_review": {"accepted", "rejected", "cancelled"}},
    IntegrationStatus: {"not_integrated": {"integrating", "discarded"}, "integrating": {"integrated", "conflicted", "failed"},
                        "conflicted": {"integrating", "discarded"}, "failed": {"discarded"}},
}


@pytest.mark.parametrize("domain", list(EDGES))
def test_all_state_pairs_against_contract(domain):
    for current in domain:
        for target in domain:
            if target.value in EDGES[domain].get(current.value, set()):
                assert transition_status(current, target) is target
            else:
                with pytest.raises(InvalidTransitionError) as exc:
                    transition_status(current, target)
                assert exc.value.code == "invalid_transition"


def test_state_domains_cannot_be_mixed():
    with pytest.raises(TypeError):
        transition_status(RunStatus.RUNNING, ProcessStatus.RUNNING)
    class Other(str, Enum):
        RUNNING = "running"
    with pytest.raises(TypeError):
        transition_status(Other.RUNNING, Other.RUNNING)


@pytest.mark.parametrize("change", [
    {"ordinal": 0}, {"finished_at": NOW - timedelta(seconds=1)},
    {"process_status": "running"}, {"started_at": None}, {"exit_code": None},
    {"exit_reason": None}, {"finished_at": None}, {"started_at": datetime(2026, 1, 1)},
    {"workspace_path": "relative"},
])
def test_invalid_attempt_lifecycle_rejected(attempt_data, change):
    with pytest.raises(ValidationError):
        TaskAttempt.model_validate({**attempt_data, **change})


def test_queued_running_and_prestart_cancellation(attempt_data):
    queued = {**attempt_data, "process_status": "queued", "exit_code": None,
              "started_at": None, "finished_at": None, "exit_reason": None}
    assert TaskAttempt.model_validate(queued).process_status is ProcessStatus.QUEUED
    with pytest.raises(ValidationError, match="has not started"):
        TaskAttempt.model_validate({**queued, "started_at": NOW})
    assert TaskAttempt.model_validate({**queued, "process_status": "running", "started_at": NOW})
    assert TaskAttempt.model_validate({**queued, "process_status": "cancelled", "finished_at": NOW, "exit_reason": "cancelled"})


def test_timestamps_normalized_to_utc(attempt_data):
    attempt = TaskAttempt.model_validate({**attempt_data, "started_at": NOW.astimezone(timezone(timedelta(hours=-3)))})
    assert attempt.started_at.utcoffset() == timedelta(0)
    assert TaskAttempt.model_validate_json(attempt.model_dump_json()) == attempt


@pytest.mark.parametrize("change", [
    {"process_status": "running"}, {"exit_code": None}, {"exit_code": 1},
    {"task_status": "running"}, {"simulated": True}, {"simulated": "false"},
    {"patch_commit_sha": None}, {"patch_commit_sha": BASE_SHA}, {"patch_artifact_id": None}, {"patch_artifact_id": "missing"},
    {"patch_artifact_id": "stdout"}, {"changed_files": []}, {"checks_executed": []},
    {"task_status": "accepted"}, {"failures": [{"code": "error", "message": "failure"}]},
])
def test_invalid_reviewable_evidence_rejected(result_data, change):
    with pytest.raises(ValidationError):
        TaskResult.model_validate({**result_data, **change})


def test_zero_exit_does_not_automatically_accept_result(result_data):
    failed = TaskResult.model_validate({**result_data, "task_status": "failed", "changed_files": [],
                                      "patch_commit_sha": None, "patch_artifact_id": None, "checks_executed": []})
    assert failed.exit_code == 0 and failed.task_status is TaskStatus.FAILED
    ready = TaskResult.model_validate(result_data)
    assert ready.task_status is TaskStatus.READY_FOR_REVIEW and ready.review is None


def test_result_validates_artifact_attribution_and_outputs(result_data):
    result_data["artifacts"].append(result_data["artifacts"][0])
    with pytest.raises(ValidationError, match="unique"):
        TaskResult.model_validate(result_data)
    result_data["artifacts"].pop()
    result_data["artifacts"][0]["run_id"] = "wrong"
    with pytest.raises(ValidationError, match="another run"):
        TaskResult.model_validate(result_data)
    result_data["artifacts"][0]["run_id"] = "run-1"
    result_data["checks_executed"][0]["stdout_artifact_id"] = "patch"
    with pytest.raises(ValidationError, match="check_output"):
        TaskResult.model_validate(result_data)


def test_result_rejects_duplicate_and_failed_checks(result_data):
    result_data["checks_executed"].append(result_data["checks_executed"][0])
    with pytest.raises(ValidationError, match="unique"):
        TaskResult.model_validate(result_data)
    result_data["checks_executed"].pop()
    result_data["checks_executed"][0]["exit_code"] = 1
    with pytest.raises(ValidationError, match="passing checks"):
        TaskResult.model_validate(result_data)


def test_explicit_review_and_integration_guard(task_data, attempt_data, result_data):
    task, attempt, result = TaskSpec(**task_data), TaskAttempt(**attempt_data), TaskResult(**result_data)
    validate_result(task, attempt, result)
    with pytest.raises(ContractViolation, match="accepted"):
        assert_integrable(task, attempt, result)
    review = ReviewDecision(result_id=result.result_id, actor="operator", decision="accepted", reason="Checks reviewed", expected_revision=1)
    accepted = review_result(task, attempt, result, review)
    assert accepted.task_status is TaskStatus.ACCEPTED and accepted.revision == 2
    assert result.task_status is TaskStatus.READY_FOR_REVIEW and result.revision == 1
    assert_integrable(task, attempt, accepted)
    assert TaskResult.model_validate_json(accepted.model_dump_json()) == accepted
    rejected = review_result(task, attempt, result, review.model_copy(update={"decision": "rejected"}))
    with pytest.raises(ContractViolation, match="accepted"):
        assert_integrable(task, attempt, rejected)
    with pytest.raises(ContractViolation) as exc:
        review_result(task, attempt, accepted, review)
    assert exc.value.code == "stale_review"


def test_review_requires_matching_metadata(task_data, attempt_data, result_data):
    task, attempt, result = TaskSpec(**task_data), TaskAttempt(**attempt_data), TaskResult(**result_data)
    with pytest.raises(ContractViolation) as exc:
        validate_result(task, attempt.model_copy(update={"task_id": "wrong"}), result)
    assert exc.value.code == "identity_mismatch"
    with pytest.raises(ContractViolation) as exc:
        validate_result(task, attempt, result.model_copy(update={"checks_executed": ()}))
    assert exc.value.code == "checks_mismatch"
    bad_check = result.checks_executed[0].model_copy(update={"tested_sha": BASE_SHA})
    with pytest.raises(ContractViolation) as exc:
        validate_result(task, attempt, result.model_copy(update={"checks_executed": (bad_check,)}))
    assert exc.value.code == "check_evidence_mismatch"


@pytest.mark.parametrize("change", [
    {"task_id": "wrong"}, {"run_id": "wrong"}, {"executor_id": "other"},
    {"base_sha": "d" * 40}, {"process_status": "crashed"}, {"exit_code": 1},
])
def test_attempt_mismatch_blocks_review(task_data, attempt_data, result_data, change):
    task, attempt, result = TaskSpec(**task_data), TaskAttempt(**{**attempt_data, **change}), TaskResult(**result_data)
    decision = ReviewDecision(result_id="result-1", actor="operator", decision="accepted", reason="review", expected_revision=1)
    with pytest.raises(ContractViolation) as exc:
        review_result(task, attempt, result, decision)
    assert exc.value.code == "identity_mismatch"


@pytest.mark.parametrize("change", [
    {"command": ["python", "-m", "pytest", "--ignore=tests"]},
    {"cwd": "other"}, {"tested_sha": BASE_SHA},
])
def test_check_metadata_mismatch_blocks_review(task_data, attempt_data, result_data, change):
    result_data["checks_executed"][0].update(change)
    with pytest.raises(ContractViolation) as exc:
        validate_result(TaskSpec(**task_data), TaskAttempt(**attempt_data), TaskResult(**result_data))
    assert exc.value.code == "check_evidence_mismatch"


def test_check_result_normalizes_workspace_root(result_data):
    check = CheckResult(**{**result_data["checks_executed"][0], "cwd": "."})
    assert check.cwd is None


def test_incomplete_result_can_be_rejected_but_not_accepted(task_data, attempt_data, result_data):
    task = TaskSpec(**{**task_data, "acceptance_criteria": task_data["acceptance_criteria"] + [
        {"check_id": "lint", "command": ["ruff", "check"]},
    ]})
    attempt, result = TaskAttempt(**attempt_data), TaskResult(**result_data)
    review = ReviewDecision(result_id="result-1", actor="operator", decision="accepted", reason="review", expected_revision=1)
    with pytest.raises(ContractViolation, match="every required check"):
        review_result(task, attempt, result, review)
    assert review_result(task, attempt, result, review.model_copy(update={"decision": "rejected"})).task_status is TaskStatus.REJECTED


def test_simulated_result_cannot_integrate(task_data, attempt_data, result_data):
    result = TaskResult(**{**result_data, "simulated": True, "task_status": "failed"})
    with pytest.raises(ContractViolation):
        assert_integrable(TaskSpec(**task_data), TaskAttempt(**attempt_data), result)


def test_review_cannot_be_attached_to_unreviewed_result(result_data):
    review = ReviewDecision(result_id="result-1", actor="operator", decision="accepted", reason="review", expected_revision=1)
    with pytest.raises(ValidationError, match="Unreviewed"):
        TaskResult(**{**result_data, "review": review})
    with pytest.raises(ValidationError, match="matching explicit review"):
        TaskResult(**{**result_data, "task_status": "accepted", "revision": 2,
                      "review": review.model_copy(update={"result_id": "wrong"})})


def test_event_and_handoff_round_trip():
    event = RunEvent(seq=1, run_id="run-1", correlation_id="attempt-1", event_type="attempt.started",
                     redacted_payload={"ready": True, "metrics": {"tokens": None}})
    assert RunEvent.model_validate_json(event.model_dump_json()) == event
    with pytest.raises(ValidationError):
        RunEvent(seq=0, run_id="run-1", correlation_id="attempt-1", event_type="unknown")
    checkpoint = HandoffCheckpoint(checkpoint_id="handoff-1", attempt_id="attempt-1", objective="Fix sum",
                                   instructions=["Preserve completed work"], git_sha=BASE_SHA, git_status=" M src/sum.py",
                                   next_step="Reconcile the tool effect before retrying",
                                   tools_executed=[ToolEffect(tool="edit", summary="Interrupted edit", status="unknown")])
    assert HandoffCheckpoint.model_validate_json(checkpoint.model_dump_json()) == checkpoint
    assert checkpoint.tools_executed[0].status == "unknown"
    assert FailureDetail(code="timeout", message="Deadline expired").retryable is False


def test_run_level_artifact_cannot_be_used_as_attempt_evidence(result_data):
    artifact = Artifact(artifact_id="export", run_id="run-1", relative_path="export/dossier.json",
                        kind="export", sha256="d" * 64, size_bytes=0)
    assert artifact.attempt_id is None
    result_data["artifacts"].append(artifact)
    with pytest.raises(ValidationError, match="another run or attempt"):
        TaskResult(**result_data)
