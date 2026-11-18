"""Rank available targets and normalize model IDs observed in provider events."""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation


FAMILIES = (
    (r"(?:gpt-|o[1-9](?:-|$)|codex-)", "openai", "chatgpt_plus"),
    (r"claude-", "anthropic", "claude_pro"),
    (r"gemini-", "google", "gemini_pro"),
    (r"deepseek-", "deepseek", "deepseek"),
    (r"qwen(?:[0-9.-]|$)", "alibaba", "qwen"),
    (r"llama(?:[0-9.-]|$)", "meta", "meta"),
    (r"grok-", "xai", "xai"),
    (r"(?:mistral|codestral|devstral)-", "mistral", "mistral"),
)


def model_family(model: str) -> tuple[str, str]:
    leaf = model.casefold().rsplit('/', 1)[-1]
    return next(((company, quota) for pattern, company, quota in FAMILIES if re.match(pattern, leaf)), ('', ''))


def observed_identity(value, source: str, route: dict) -> dict | None:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:+-]{0,199}', value):
        return None
    if value.casefold() in {'default', 'native-default', 'sonnet', 'opus', 'haiku'}:
        return None
    company, _ = model_family(value)
    if route.get('connection_mode') == 'omniroute' and value == route.get('target_ref'):
        if route.get('target_kind') == 'combo' or not company:
            return None
    return {'model': value, 'company': company or None, 'source': source}


def cli_reported_model(executor: str, event: dict):
    if event.get('parent_tool_use_id') or event.get('parent_thread_id'):
        return None
    kind = event.get('type')
    if executor == 'codex' and kind in {'thread.started', 'turn.started', 'turn.completed'}:
        return event.get('model')
    if executor == 'claude':
        if kind == 'assistant' and isinstance(event.get('message'), dict):
            return event['message'].get('model')
        if kind == 'stream_event' and isinstance(event.get('event'), dict):
            inner = event['event']
            if inner.get('type') == 'message_start' and isinstance(inner.get('message'), dict):
                return inner['message'].get('model')
    return None


def model_rank(model: str, metadata: dict, category: str, quota: dict, image: bool, context: int):
    """Use catalog capabilities first, then deterministic family/size hints."""
    architecture = metadata.get('architecture') or {}
    if not isinstance(architecture, dict):
        architecture = {}
    modalities = metadata.get('input_modalities', architecture.get('input_modalities', []))
    vision = metadata.get('supports_vision') is True or isinstance(modalities, list) and 'image' in modalities
    if image and not vision:
        return None
    parameters = metadata.get('supported_parameters')
    if metadata.get('supports_tools') is False or isinstance(parameters, list) and parameters and 'tools' not in parameters:
        return None
    window = metadata.get('context_length', metadata.get('context_window'))
    if isinstance(window, int) and window > 0 and window < context:
        return None
    _, quota_key = model_family(model)
    provider_key = model.split('/', 1)[0] if '/' in model else quota_key
    measured = quota.get(provider_key, quota.get(quota_key, {}))
    capacity = measured.get('remaining_percent') if isinstance(measured, dict) and measured.get('status') != 'unknown' else None
    if isinstance(capacity, (int, float)) and math.isfinite(capacity) and capacity <= 0:
        return None
    name = model.casefold().rsplit('/', 1)[-1]
    small = bool(re.search(r'mini|nano|flash|haiku|lite|small', name))
    reasoning = metadata.get('supports_reasoning') is True or bool(re.search(r'reason|thinking|opus|\bpro\b|^o[1-9]', name))
    coding = bool(re.search(r'codex|codestral|devstral|coder|sonnet', name))
    profile = {
        'planning': (reasoning, not small, coding),
        'review': (reasoning, not small, coding),
        'ui': (vision, coding, not small),
        'code': (coding, not small, reasoning),
        'tests': (coding, small, reasoning),
        'docs': (small, not reasoning, coding),
    }[category]
    return (*profile, float(capacity) if isinstance(capacity, (int, float)) and math.isfinite(capacity) else -1)


def unit_price(metadata: dict) -> tuple[Decimal, Decimal] | None:
    pricing = metadata.get('pricing')
    if not isinstance(pricing, dict):
        return None
    try:
        prompt = Decimal(str(pricing.get('prompt')))
        completion = Decimal(str(pricing.get('completion')))
    except InvalidOperation:
        return None
    if prompt.is_finite() and completion.is_finite() and prompt >= 0 and completion >= 0:
        return prompt, completion
    return None
