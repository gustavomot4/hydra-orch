"""Intelligent Router directing prompts across Swarm, Relay, and Persistent modes."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator, Dict, List, Optional
from hydra_orch.config import (
    HydraConfig, UnknownAliasError, ProviderUnavailableError, GatewayUnavailableError,
    UnsupportedModeError, load_config,
)
from hydra_orch.bridge.omniroute_client import OmniRouteClient
from hydra_orch.model import ChatCompletionRequest, ChatMessage
from hydra_orch.adapter.base import BaseAdapter, LimitHitException
from hydra_orch.adapter.ui_cdp import UiCdpAdapter
from hydra_orch.adapter.ide_bridge import IdeBridgeAdapter
from hydra_orch.adapter.api_gateway import ApiGatewayAdapter
from hydra_orch.adapter.remote_local import RemoteLocalAdapter
from hydra_orch.core.checkpointer import StreamCheckpointer
from hydra_orch.core.swarm import SwarmOrchestrator, SubTask

logger = logging.getLogger(__name__)


class HydraRouter:
    """Core routing engine coordinating adapters, resilience checkpointer, and execution modes."""

    def __init__(self, config: Optional[HydraConfig] = None):
        self.config = config or load_config()
        self.checkpointer = StreamCheckpointer(self.config.orchestrator.resilience.database_path)
        self.swarm = SwarmOrchestrator(
            worktrees_base_dir=self.config.swarm.worktrees_dir,
            contract_path=self.config.swarm.base_contract_file,
            test_command=self.config.swarm.test_command,
        )
        self.adapters: Dict[str, BaseAdapter] = {}
        self._initialize_adapters()

    def _initialize_adapters(self) -> None:
        """Instantiate all enabled adapters based on configuration."""
        providers = self.config.provider_groups()

        # 1. UI CDP adapters
        for name, cfg in providers["ui_cdp"].items():
            if cfg.enabled:
                self.adapters[name] = UiCdpAdapter(name, cfg.model_dump())

        # 2. IDE Bridge adapters
        for name, cfg in providers["ide_bridge"].items():
            if cfg.enabled:
                self.adapters[name] = IdeBridgeAdapter(name, cfg.model_dump())

        # 3. API Gateway adapters
        for name, cfg in providers["api_gateway"].items():
            if cfg.enabled:
                self.adapters[name] = ApiGatewayAdapter(name, cfg.model_dump())

        # 4. Remote Local / SSH adapters
        for name, cfg in providers["remote_local"].items():
            if cfg.enabled:
                self.adapters[name] = RemoteLocalAdapter(name, cfg.model_dump())

        logger.info(f"Initialized adapters: {list(self.adapters.keys())}")

    def list_available_adapters(self) -> List[str]:
        return list(self.adapters.keys())

    def resolve_provider_name(self, name_or_alias: str) -> Optional[str]:
        """Resolves either a direct adapter name or a logical model alias to an active adapter name (GAP A01)."""
        if name_or_alias in self.adapters:
            return name_or_alias
        try:
            target = self.config.resolve_alias(name_or_alias)
            if target.preferred_adapter and target.preferred_adapter in self.adapters:
                return target.preferred_adapter
        except UnknownAliasError:
            pass
        return None

    def get_adapter(self, name: str) -> Optional[BaseAdapter]:
        resolved = self.resolve_provider_name(name)
        return self.adapters.get(resolved) if resolved else None

    def select_provider_for_complexity(self, complexity: int) -> str:
        """Maps complexity score (1-10) to configured preferred provider."""
        if type(complexity) is not int or not 1 <= complexity <= 10:
            raise ValueError("complexity must be an integer between 1 and 10")
        candidates = sorted(
            self.config.omniroute.logical_models.items(),
            key=lambda item: item[1].min_difficulty, reverse=True,
        )
        for alias, mapping in candidates:
            if mapping.min_difficulty <= complexity:
                resolved = self.resolve_provider_name(alias)
                if resolved:
                    return resolved

        for fallback in self.config.orchestrator.resilience.handoff_fallback_chain:
            fb_resolved = self.resolve_provider_name(fallback)
            if fb_resolved:
                return fb_resolved

        raise ProviderUnavailableError("No eligible inference adapter is configured")

    async def ensure_gateway(self) -> None:
        """Required is fail-closed; disabled/optional never need a preflight call."""
        if self.config.is_omniroute_required:
            gateway = OmniRouteClient(
                base_url=self.config.omniroute.base_url,
                quota_api_url=self.config.omniroute.quota_api_url,
                api_key_env=self.config.omniroute.api_key_env,
            )
            if not await gateway.is_available():
                raise GatewayUnavailableError("Required OmniRoute gateway is unavailable")

    def validate_request(self, request: ChatCompletionRequest) -> None:
        mode = request.mode or self.config.orchestrator.default_mode
        if mode == "swarm":
            raise UnsupportedModeError("Verified swarm execution is not available in the inference proxy")
        if request.preferred_provider and not self.resolve_provider_name(request.preferred_provider):
            raise ProviderUnavailableError("Requested route has no enabled inference adapter; CLI drivers are separate")
        if not self.adapters:
            raise ProviderUnavailableError("No inference adapters are enabled")
        if mode == "relay" and not self._inference_routes(request.preferred_provider):
            raise ProviderUnavailableError("No eligible inference route is configured")
        if mode == "persistent":
            target = request.preferred_provider or self.config.modes.mode_3_persistent.locked_model
            if not target or not self.resolve_provider_name(target):
                raise ProviderUnavailableError("Persistent inference route is not enabled")

    def _inference_routes(self, preferred: Optional[str] = None) -> list:
        references = ([preferred] if preferred else []) + self.config.orchestrator.resilience.handoff_fallback_chain
        routes = []
        seen = set()
        for reference in references:
            target = self.config.resolve_alias(reference)
            for route in [target] + [self.config.resolve_alias(f) for f in target.fallbacks]:
                name = route.preferred_adapter
                identity = (name, route.primary_model)
                if name in self.adapters and identity not in seen:
                    routes.append((name, route.primary_model))
                    seen.add(identity)
        return routes

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Entry point for handling chat completion requests according to selected mode."""
        if request.mode is None:
            request = request.model_copy(update={"mode": self.config.orchestrator.default_mode})
        self.validate_request(request)
        await self.ensure_gateway()
        mode = request.mode
        session_id = request.session_id or f"sess-{uuid.uuid4().hex[:10]}"

        logger.info(f"Executing request in mode: '{mode}' (Session ID: {session_id})")

        if mode == "swarm":
            async for chunk in self._execute_swarm_mode(request, session_id):
                yield chunk
        elif mode == "persistent":
            async for chunk in self._execute_persistent_mode(request, session_id):
                yield chunk
        else:
            async for chunk in self._execute_relay_mode(request, session_id):
                yield chunk

    async def _execute_relay_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 2: Relay Pipeline with alias resolution and structured handoff on limit hit."""
        providers_to_try = self._inference_routes(request.preferred_provider)
        if not providers_to_try:
            raise ProviderUnavailableError("No eligible inference route is configured")

        accumulated_text = ""
        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        current_messages = list(request.messages)

        for provider_name, resolved_model in providers_to_try:
            adapter = self.adapters[provider_name]

            if await self.checkpointer.is_provider_limited(provider_name):
                wait_sec = await self.checkpointer.get_remaining_limit_seconds(provider_name)
                logger.info(f"Skipping {provider_name} (rate-limited for {wait_sec}s)")
                continue

            try:
                logger.info(f"Routing request to provider: {provider_name}")
                async for chunk in adapter.generate_stream(
                    current_messages,
                    options={"model": resolved_model if request.model.startswith("hydra-") else request.model,
                             "temperature": request.temperature},
                ):
                    accumulated_text += chunk
                    yield chunk

                await self.checkpointer.save_checkpoint(
                    session_id=session_id,
                    task_id=request.task_id,
                    provider=provider_name,
                    prompt=user_prompt,
                    accumulated_content=accumulated_text,
                    status="completed",
                )
                return

            except LimitHitException as e:
                logger.warning(f"Limit hit on {provider_name}: {e.message}. Initiating Structured Handoff...")
                await self.checkpointer.record_provider_limit(
                    provider=provider_name,
                    reset_in_seconds=e.reset_in_seconds or 3600,
                    reason=e.message,
                )
                await self.checkpointer.save_checkpoint(
                    session_id=session_id,
                    task_id=request.task_id,
                    provider=provider_name,
                    prompt=user_prompt,
                    accumulated_content=accumulated_text,
                    status="limit_paused",
                    reset_at=time.time() + (e.reset_in_seconds or 3600),
                )

                handoff_prompt = self.checkpointer.build_hot_handoff_prompt(
                    original_prompt=user_prompt,
                    partial_output=accumulated_text,
                    failed_provider=provider_name,
                )
                # Preserve system instructions across handoff
                system_msgs = [m for m in request.messages if m.role == "system"]
                current_messages = system_msgs + [ChatMessage(role="user", content=handoff_prompt)]
                yield f"\n\n[Hydra Orchestrator: Quota limit hit on {provider_name}. Handoff to next model...]\n\n"

            except Exception as e:
                logger.error(f"Error on provider {provider_name}: {e}. Retrying next in chain.")
                yield f"\n[Hydra: Provider {provider_name} failed: {e}. Switching to fallback...]\n"

        yield "\n[Hydra Error: All configured providers in the fallback chain exhausted.]"

    async def _execute_persistent_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 3: Persistent Focus with active timer wait and auto-resume."""
        raw_primary = request.preferred_provider or self.config.modes.mode_3_persistent.locked_model
        primary_provider = self.resolve_provider_name(raw_primary) or raw_primary
        adapter = self.adapters.get(primary_provider)
        if not adapter:
            raise ProviderUnavailableError("Persistent inference route is not enabled")

        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        accumulated_text = ""
        current_messages = list(request.messages)

        while True:
            if await self.checkpointer.is_provider_limited(primary_provider):
                rem_seconds = await self.checkpointer.get_remaining_limit_seconds(primary_provider)
                yield f"\n[Hydra Persistent: Provider {primary_provider} in rate-limit sleep. Resumes in {rem_seconds}s...]\n"
                poll_interval = min(self.config.orchestrator.resilience.auto_resume_check_interval_seconds, rem_seconds or 60)
                await asyncio.sleep(poll_interval)
                continue

            try:
                async for chunk in adapter.generate_stream(
                    current_messages,
                    options={"model": self.config.resolve_alias(raw_primary).primary_model
                             if request.model.startswith("hydra-") else request.model,
                             "temperature": request.temperature},
                ):
                    accumulated_text += chunk
                    yield chunk

                await self.checkpointer.save_checkpoint(
                    session_id=session_id,
                    task_id=request.task_id,
                    provider=primary_provider,
                    prompt=user_prompt,
                    accumulated_content=accumulated_text,
                    status="completed",
                )
                break

            except LimitHitException as e:
                wait_sec = e.reset_in_seconds or 3600
                await self.checkpointer.record_provider_limit(primary_provider, wait_sec, e.message)
                await self.checkpointer.save_checkpoint(
                    session_id=session_id,
                    task_id=request.task_id,
                    provider=primary_provider,
                    prompt=user_prompt,
                    accumulated_content=accumulated_text,
                    status="auto_resume_waiting",
                    reset_at=time.time() + wait_sec,
                )
                if accumulated_text:
                    handoff_prompt = self.checkpointer.build_hot_handoff_prompt(
                        original_prompt=user_prompt,
                        partial_output=accumulated_text,
                        failed_provider=primary_provider,
                    )
                    system_msgs = [m for m in request.messages if m.role == "system"]
                    current_messages = system_msgs + [ChatMessage(role="user", content=handoff_prompt)]
                yield f"\n[Hydra Persistent: Quota reached. Auto-Resume scheduled in {wait_sec} seconds... Waiting.]\n"

    async def _execute_swarm_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 1: Swarm Parallel decomposition, Git Worktree isolation and verified merge."""
        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        yield "--- [HYDRA SWARM INITIATED] ---\nAnalyzing task and partitioning into isolated Git Worktrees...\n\n"

        subtasks = self.swarm.decompose_prompt(user_prompt)
        yield f"Decomposed into {len(subtasks)} parallel sub-tasks:\n"
        for st in subtasks:
            assigned = self.select_provider_for_complexity(st.complexity)
            st.preferred_provider = assigned
            yield f"- [{st.name}] Complexity {st.complexity}/10 -> Assigned to: **{assigned}**\n"

        contract = self.swarm.generate_base_contract(user_prompt, subtasks)
        yield f"\nGenerated Base Contract at `{self.config.swarm.base_contract_file}`.\n"

        async def run_subtask(task: SubTask) -> str:
            worktree_path = self.swarm.create_worktree(task)
            task_prompt = (
                f"Worktree Directory: {worktree_path}\n"
                f"Task: {task.description}\n"
                f"Target Files: {', '.join(task.target_files)}\n"
                f"Contract Rules:\n{contract}\n\n"
                f"Generate full implementation for your target files."
            )
            provider_name = task.preferred_provider or "ollama_local"
            adapter = self.get_adapter(provider_name) or list(self.adapters.values())[0]

            out = await adapter.generate([ChatMessage(role="user", content=task_prompt)])
            task.result_summary = f"Finished ({len(out)} chars)"
            task.status = "completed"
            return out

        yield "\nLaunching parallel swarm execution...\n"
        results = await asyncio.gather(*[run_subtask(t) for t in subtasks], return_exceptions=True)

        yield "\nSwarm execution completed. Validating outcomes before merging...\n"
        for task, res in zip(subtasks, results):
            if isinstance(res, Exception) or task.status != "completed":
                yield f"- Branch `{task.branch_name}`: Task failed ({res}); preserving worktree.\n"
                continue
            merged = self.swarm.merge_worktree_branch(task)
            status_text = "Merged successfully" if merged else "Merge skipped / conflict"
            yield f"- Branch `{task.branch_name}`: {status_text}\n"
            if merged:
                self.swarm.cleanup_worktree(task)

        yield "\n--- [HYDRA SWARM COMPLETED ALL WORKFLOWS] ---\n"
