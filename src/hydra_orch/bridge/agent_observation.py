"""Read-only normalization of CLI delegation frames; never starts an agent."""
from hydra_orch.core.redaction import redact_text


def observations(driver, event, known):
    def text(value, limit=4000):
        return redact_text(str(value or ""))[:limit]

    if driver == "codex":
        item = event.get("item", {})
        if event.get("type") not in {"item.started", "item.updated", "item.completed"} or item.get("type") != "collab_tool_call":
            return []
        states = item.get("agents_states") or {}
        if not isinstance(states, dict):
            states = {}
        receivers = item.get('receiver_thread_ids') or []
        if not isinstance(receivers, list):
            receivers = []
        result = []
        for identifier in sorted({value for value in receivers if isinstance(value, str)} | set(states)):
            if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
                continue
            previous = known.get(identifier, {})
            state = states.get(identifier) or {}
            if not isinstance(state, dict):
                state = {"status": state}
            raw_status = state.get('status') if isinstance(state.get('status'), str) else None
            status = {"pending_init": "starting", "errored": "failed", "shutdown": "stopped", "interrupted": "stopped", "not_found": "unavailable"}.get(raw_status, raw_status)
            # Tool completion means the call returned, not that its child finished.
            status = status or previous.get("state") or ("starting" if item.get("tool") == "spawn_agent" else "unknown")
            result.append({**previous, "id": identifier, "parent_id": text(item.get("sender_thread_id"), 200) or previous.get('parent_id', ''),
                           "title": previous.get("title") or text(item.get("prompt"), 160) or "Subagente Codex",
                           "state": status, "executor": driver, "model": text(item.get("model"), 200) or previous.get("model", "Não informado pela CLI"),
                           "summary": text(state.get("message")) or previous.get("summary", "Criação observada na CLI"), "source": "cli"})
        return result
    if driver != "claude" or event.get("type") != "system" or event.get("ambient"):
        return []
    subtype = event.get("subtype")
    identifier = event.get("task_id")
    if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
        return []
    previous = known.get(identifier)
    if subtype == "task_started" and event.get("task_type") in {"local_agent", "remote_agent"}:
        return [{"id": identifier, "parent_id": text(event.get("parent_task_id"), 200), "title": text(event.get("description"), 160) or "Subagente Claude",
                 "state": "running", "executor": driver, "model": "Não informado pela CLI", "summary": "Criação observada na CLI", "source": "cli"}]
    if not previous or subtype not in {"task_progress", "task_notification", "task_updated"}:
        return []
    patch = event.get("patch") or {}
    status = patch.get("status") or event.get("status") or previous["state"]
    return [{**previous, "state": "stopped" if status == "killed" else status,
             "summary": text(event.get("summary") or patch.get("description") or event.get("description")) or previous["summary"]}]
