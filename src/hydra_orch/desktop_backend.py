"""Backend owned by the Windows launcher: same-origin UI and graceful stop."""
import argparse
import os
import uvicorn


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runtime-dir", default=None)
    args = parser.parse_args()
    from hydra_orch.server import app
    from hydra_orch import server as api
    # The ordinary/manual server stays offline-first. The desktop launcher is
    # the user's explicit one-click start of Hydra and its local gateway.
    if os.environ.get('HYDRA_OMNIROUTE_AUTOSTART', '1').lower() not in {'0', 'false', 'no'}:
        api.config.omniroute.enabled = True
        api.config.omniroute.connection_mode = 'optional'
        api.config.omniroute.auto_start_daemon = True
    else:
        api.config.omniroute.auto_start_daemon = False
    if args.runtime_dir:
        from pathlib import Path
        from hydra_orch.core.checkpointer import ExecutionStore
        from hydra_orch.core.run_service import RunService
        store = ExecutionStore(Path(args.runtime_dir) / "checkpoints.sqlite")
        api.router.checkpointer = store
        api.set_run_service(RunService(Path.cwd(), store=store, runtime_dir=args.runtime_dir))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=3))
    app.state.desktop_shutdown = lambda: setattr(server, "should_exit", True)
    server.run()


if __name__ == "__main__":
    main()
