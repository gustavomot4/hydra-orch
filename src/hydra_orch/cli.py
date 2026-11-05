"""CLI for hydra-orch: serve, run, status and init."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.markdown import Markdown

from hydra_orch.config import load_config
from hydra_orch.model import ChatCompletionRequest, ChatMessage
from hydra_orch.core.router import HydraRouter

app = typer.Typer(
    name="hydra",
    help="hydra-orch: Universal Autonomous LLM Orchestrator CLI",
    add_completion=False,
)
console = Console()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
):
    """Start the OpenAI-compatible proxy server (http://localhost:8000/v1)."""
    banner = (
        "[bold cyan]HYDRA ORCHESTRATOR[/bold cyan]\n"
        "[dim]Universal Autonomous LLM Orchestrator & Middleware[/dim]\n\n"
        f"API Endpoint: [green]http://{host}:{port}/v1[/green]\n"
        f"Compatible with Cline, Aider, OpenCode, Cursor, and OpenAI SDKs."
    )
    console.print(Panel(banner, border_style="cyan"))

    import uvicorn
    uvicorn.run("hydra_orch.server:app", host=host, port=port, reload=reload)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Prompt or task instruction to execute"),
    mode: Optional[str] = typer.Option(
        None, "--mode", "-m", help="Execution mode: swarm | relay | persistent"
    ),
    provider: Optional[str] = typer.Option(
        None, "--provider", "-P", help="Specific adapter to target (e.g. claude_pro, deepseek, ollama_local)"
    ),
):
    """Run an instruction directly through hydra-orch (Swarm, Relay, or Persistent)."""
    cfg = load_config()
    chosen_mode = mode or cfg.orchestrator.default_mode

    console.print(
        Panel(
            f"[bold green]Starting Task in Mode:[/bold green] [yellow]{chosen_mode.upper()}[/yellow]\n"
            f"[bold]Prompt:[/bold] {prompt}",
            border_style="green",
        )
    )

    router = HydraRouter(cfg)
    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content=prompt)],
        mode=chosen_mode,
        preferred_provider=provider,
        stream=True,
    )

    async def _execute():
        await router.checkpointer.initialize()
        accumulated = []
        with Live(console=console, refresh_per_second=8) as live:
            async for chunk in router.stream_chat_completion(request):
                accumulated.append(chunk)
                full_text = "".join(accumulated)
                live.update(Markdown(full_text))

    asyncio.run(_execute())


@app.command()
def status():
    """Display status of all configured adapters, ports, and resilience checkpoints."""
    cfg = load_config()
    router = HydraRouter(cfg)

    table = Table(title="Hydra Orchestrator - Adapter Statuses", border_style="cyan")
    table.add_column("Adapter Name", style="bold white")
    table.add_column("Type", style="cyan")
    table.add_column("Health / Status", style="green")
    table.add_column("Details", style="dim")

    async def _check():
        async def _probe(name, adapter):
            avail = await adapter.is_available()
            status_text = "[green]ONLINE[/green]" if avail else "[red]OFFLINE[/red]"
            details = adapter.last_error or "Ready"
            if hasattr(adapter, "cdp_port"):
                details = f"Port: {adapter.cdp_port} | {details}"
            elif hasattr(adapter, "base_url"):
                details = f"URL: {adapter.base_url} | {details}"
            return (name, adapter.__class__.__name__, status_text, details)

        results = await asyncio.gather(
            *[_probe(name, adapter) for name, adapter in router.adapters.items()]
        )
        for row in results:
            table.add_row(*row)

    asyncio.run(_check())
    console.print(table)


@app.command()
def quota():
    """Display real-time 5-hour subscription quota windows (Claude, ChatGPT, Gemini)."""
    from hydra_orch.bridge.omniroute_client import OmniRouteClient
    cfg = load_config()
    client = OmniRouteClient(
        base_url=cfg.omniroute.base_url,
        quota_api_url=cfg.omniroute.quota_api_url,
    )

    table = Table(title="OmniRoute 5h Quota Tracker", border_style="green")
    table.add_column("Subscription / Model", style="bold white")
    table.add_column("Remaining Quota", style="cyan")
    table.add_column("Resets In", style="yellow")
    table.add_column("Status", style="green")

    async def _fetch():
        data = await client.get_quota_status()
        for k, v in data.items():
            if isinstance(v, dict):
                rem = f"{v.get('remaining_percent', 100)}%"
                resets = f"{v.get('resets_in_seconds', 0)}s"
                status_str = "ACTIVE" if v.get("remaining_percent", 100) > 0 else "QUOTA_LIMITED"
                table.add_row(k.replace("_", " ").title(), rem, resets, status_str)

    asyncio.run(_fetch())
    console.print(table)


if __name__ == "__main__":
    app()
