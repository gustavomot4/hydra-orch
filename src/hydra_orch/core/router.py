"""Intelligent Router directing prompts across Swarm, Relay, and Persistent modes."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional
from hydra_orch.config import HydraConfig, load_config
from hydra_orch.models import ChatCompletionRequest, ChatMessage
from hydra_orch.adapters.base import BaseAdapter, LimitHitException
from hydra_orch.adapters.ui_cdp import UiCdpAdapter
from hydra_orch.adapters.ide_bridge import IdeBridgeAdapter
from hydra_orch.adapters.api_gateway import ApiGatewayAdapter
from hydra_orch.adapters.remote_local import RemoteLocalAdapter
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
        providers = self.config.providers

        # 1. UI CDP adapters
        for name, cfg in providers.ui_cdp.items():
            if cfg.enabled:
                self.adapters[name] = UiCdpAdapter(name, cfg.model_dump())

        # 2. IDE Bridge adapters
        for name, cfg in providers.ide_bridge.items():
            if cfg.enabled:
                self.adapters[name] = IdeBridgeAdapter(name, cfg.model_dump())

        # 3. API Gateway adapters
        for name, cfg in providers.api_gateway.items():
            if cfg.enabled:
                self.adapters[name] = ApiGatewayAdapter(name, cfg.model_dump())

        # 4. Remote Local / SSH adapters
        for name, cfg in providers.remote_local.items():
            if cfg.enabled:
                self.adapters[name] = RemoteLocalAdapter(name, cfg.model_dump())

        logger.info(f"Initialized adapters: {list(self.adapters.keys())}")

    def list_available_adapters(self) -> List[str]:
        return list(self.adapters.keys())

    def get_adapter(self, name: str) -> Optional[BaseAdapter]:
        return self.adapters.get(name)

    def select_provider_for_complexity(self, complexity: int) -> str:
        """Maps complexity score (1-10) to configured preferred provider."""
        thresholds = self.config.swarm.difficulty_thresholds
        if complexity <= thresholds.get("simple", {}).max_complexity:
            provider = thresholds["simple"].preferred_provider
        elif complexity <= thresholds.get("moderate", {}).max_complexity:
            provider = thresholds["moderate"].preferred_provider
        else:
            provider = thresholds["complex"].preferred_provider

        # Fallback if preferred provider is not configured/available
        if provider in self.adapters:
            return provider
        for fallback in self.config.orchestrator.resilience.handoff_fallback_chain:
            if fallback in self.adapters:
                return fallback
        return list(self.adapters.keys())[0] if self.adapters else "mock"

    async def stream_chat_completion(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[str]:
        """Entry point for handling chat completion requests according to selected mode."""
        mode = request.mode or self.config.orchestrator.default_mode
        session_id = request.session_id or f"sess-{uuid.uuid4().hex[:10]}"

        logger.info(f"Executing request in mode: '{mode}' (Session ID: {session_id})")

        if mode == "swarm":
            async for chunk in self._execute_swarm_mode(request, session_id):
                yield chunk
        elif mode == "persistent":
            async for chunk in self._execute_persistent_mode(request, session_id):
                yield chunk
        else:
            # Default: Mode 2 - Relay (Pipeline with Hot-Handoff)
            async for chunk in self._execute_relay_mode(request, session_id):
                yield chunk

    async def _execute_relay_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 2: Relay Pipeline with tolerance and hot-swap handoff if limits hit."""
        fallback_chain = self.config.orchestrator.resilience.handoff_fallback_chain
        
        # Determine starting provider
        preferred = request.preferred_provider or (fallback_chain[0] if fallback_chain else None)
        providers_to_try = [p for p in fallback_chain if p in self.adapters]
        if preferred and preferred in providers_to_try:
            providers_to_try.remove(preferred)
            providers_to_try.insert(0, preferred)

        if not providers_to_try:
            yield "Error: No active adapters configured in hydra-orch."
            return

        accumulated_text = ""
        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        current_messages = list(request.messages)

        for idx, provider_name in enumerate(providers_to_try):
            adapter = self.adapters[provider_name]

            # Check if this provider has an active rate-limit hold
            if await self.checkpointer.is_provider_limited(provider_name):
                wait_sec = await self.checkpointer.get_remaining_limit_seconds(provider_name)
                logger.info(f"Skipping {provider_name} (rate-limited for {wait_sec}s)")
                continue

            try:
                logger.info(f"Routing request to provider: {provider_name}")
                async for chunk in adapter.generate_stream(
                    current_messages,
                    options={"model": request.model, "temperature": request.temperature},
                ):
                    accumulated_text += chunk
                    yield chunk

                # Save success checkpoint
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
                logger.warning(f"Limit hit on {provider_name}: {e.message}. Initiating Hot-Handoff...")
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

                # Hot-handoff: prepare handover prompt for next model in chain
                handoff_prompt = self.checkpointer.build_hot_handoff_prompt(
                    original_prompt=user_prompt,
                    partial_output=accumulated_text,
                    failed_provider=provider_name,
                )
                current_messages = [ChatMessage(role="user", content=handoff_prompt)]
                yield f"\n\n[Hydra Orchestrator: Quota limit hit on {provider_name}. Hot-Handoff to next model...]\n\n"

            except Exception as e:
                logger.error(f"Error on provider {provider_name}: {e}. Retrying next in chain.")
                yield f"\n[Hydra: Provider {provider_name} failed: {e}. Switching to fallback...]\n"

        yield "\n[Hydra Error: All configured providers in the fallback chain exhausted.]"

    async def _execute_persistent_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 3: Persistent Focus with active timer wait and auto-resume."""
        primary_provider = request.preferred_provider or "claude_pro"
        adapter = self.adapters.get(primary_provider)
        if not adapter:
            yield f"Error: Primary provider '{primary_provider}' not found."
            return

        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        accumulated_text = ""
        current_messages = list(request.messages)

        while True:
            # Check if limited
            if await self.checkpointer.is_provider_limited(primary_provider):
                rem_seconds = await self.checkpointer.get_remaining_limit_seconds(primary_provider)
                yield f"\n[Hydra Persistent: Provider {primary_provider} in rate-limit sleep. Resumes in {rem_seconds}s...]\n"
                poll_interval = min(self.config.orchestrator.resilience.auto_resume_check_interval_seconds, rem_seconds or 60)
                await asyncio.sleep(poll_interval)
                continue

            try:
                async for chunk in adapter.generate_stream(
                    current_messages,
                    options={"model": request.model, "temperature": request.temperature},
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
                yield f"\n[Hydra Persistent: Quota reached. Auto-Resume scheduled in {wait_sec} seconds... Waiting.]\n"
                # Loop will sleep and resume when timer expires

    async def _execute_swarm_mode(
        self, request: ChatCompletionRequest, session_id: str
    ) -> AsyncIterator[str]:
        """Mode 1: Swarm Parallel decomposition, Git Worktree isolation and parallel merge."""
        user_prompt = "\n".join([m.content or "" for m in request.messages if m.role == "user"])
        yield f"--- [HYDRA SWARM INITIATED] ---\nAnalyzing task and partitioning into isolated Git Worktrees...\n\n"

        # 1. Decompose task into subtasks
        subtasks = self.swarm.decompose_prompt(user_prompt)
        yield f"Decomposed into {len(subtasks)} parallel sub-tasks:\n"
        for st in subtasks:
            assigned = self.select_provider_for_complexity(st.complexity)
            st.preferred_provider = assigned
            yield f"- [{st.name}] Complexity {st.complexity}/10 -> Assigned to: **{assigned}**\n"

        # 2. Generate Base Contract
        contract = self.swarm.generate_base_contract(user_prompt, subtasks)
        yield f"\nGenerated Base Contract at `{self.config.swarm.base_contract_file}`.\n"

        # 3. Create worktrees and dispatch parallel tasks
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
            adapter = self.adapters.get(provider_name)
            if not adapter:
                adapter = list(self.adapters.values())[0]

            out = await adapter.generate([ChatMessage(role="user", content=task_prompt)])
            task.result_summary = f"Finished ({len(out)} chars)"
            task.status = "completed"
            return out

        yield "\nLaunching parallel swarm execution...\n"
        results = await asyncio.gather(*[run_subtask(t) for t in subtasks], return_exceptions=True)

        # 4. Merge results and execute tests
        yield "\nSwarm execution completed. Processing branches and merging...\n"
        for task in subtasks:
            merged = self.swarm.merge_worktree_branch(task)
            status_text = "Merged successfully" if merged else "Merge skipped / conflict"
            yield f"- Branch `{task.branch_name}`: {status_text}\n"
            self.swarm.cleanup_worktree(task)

        yield "\n--- [HYDRA SWARM COMPLETED ALL WORKFLOWS] ---\n"
