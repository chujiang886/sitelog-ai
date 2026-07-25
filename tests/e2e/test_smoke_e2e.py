"""Socket-level smoke test against a real uvicorn subprocess."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
BACKEND_ROOT: Path = PROJECT_ROOT / "backend"


def _reserve_port() -> int:
    """Ask the operating system for an available local TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="module")
def live_backend_url() -> Iterator[str]:
    """Start uvicorn, wait for readiness, and always terminate the child process."""

    port: int = _reserve_port()
    base_url: str = f"http://127.0.0.1:{port}"
    environment: dict[str, str] = os.environ.copy()
    for coverage_key in (
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COV_CORE_SOURCE",
    ):
        environment.pop(coverage_key, None)
    python_path: list[str] = [str(BACKEND_ROOT), str(PROJECT_ROOT)]
    existing_python_path: str = environment.get("PYTHONPATH", "").strip()
    if existing_python_path:
        python_path.append(existing_python_path)
    environment["PYTHONPATH"] = os.pathsep.join(python_path)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline: float = time.monotonic() + 10.0  # infrastructure-config
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1.0)
                pytest.fail(
                    "uvicorn exited before readiness: "
                    f"returncode={process.returncode}\nstdout={stdout}\nstderr={stderr}"
                )
            try:
                response = httpx.get(f"{base_url}/health", timeout=0.5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                continue
        else:
            pytest.fail("uvicorn did not become ready before the test timeout")

        yield base_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)


@pytest.mark.e2e
def test_backend_http_smoke(live_backend_url: str) -> None:
    """Call health, projects, and Agents through the real HTTP transport."""

    with httpx.Client(base_url=live_backend_url, timeout=2.0) as client:
        responses: tuple[httpx.Response, ...] = (
            client.get("/health"),
            client.get("/api/projects"),
            client.get("/api/agents"),
        )

    for response in responses:
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert "data" in payload
