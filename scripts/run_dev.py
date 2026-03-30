import os
import subprocess
import sys
import time


def _terminate_process(process: subprocess.Popen[str], name: str) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    print(f"{name} stopped.", flush=True)


def main() -> None:
    backend_env = os.environ.copy()
    backend_env["MME_SCHEDULER_ENABLED"] = "false"

    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ],
        env=backend_env,
    )
    scheduler = subprocess.Popen([sys.executable, "scripts/run_scheduler.py"], env=os.environ.copy())

    print("Development stack started.", flush=True)
    print("- Backend: http://127.0.0.1:8000", flush=True)
    print("- Scheduler: python scripts/run_scheduler.py", flush=True)

    try:
        while True:
            backend_exit = backend.poll()
            scheduler_exit = scheduler.poll()
            if backend_exit is not None:
                raise SystemExit(f"Backend exited with code {backend_exit}.")
            if scheduler_exit is not None:
                raise SystemExit(f"Scheduler exited with code {scheduler_exit}.")
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate_process(backend, "Backend")
        _terminate_process(scheduler, "Scheduler")


if __name__ == "__main__":
    main()
