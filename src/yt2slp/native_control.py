"""Private socket transport; game stdout/stderr can never become protocol data."""
from pathlib import Path
import socket
import subprocess
import time


class ControlSession:
    """Own one live native process. Closing drops the connection and reaps it."""
    def __init__(self, command: list[str], run_dir: Path, timeout: float):
        self.timeout = timeout
        self.process = None
        self.socket, child = socket.socketpair()
        self.buffer = b""
        try:
            with (run_dir / "host.log").open("wb") as log:
                self.process = subprocess.Popen(
                    command + ["--control-fd", str(child.fileno())], cwd=run_dir,
                    pass_fds=(child.fileno(),), stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT)
        except BaseException:
            self.socket.close()
            raise
        finally:
            child.close()

    def receive(self) -> str:
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native control response timed out")
            self.socket.settimeout(remaining)
            chunk = self.socket.recv(4096)
            if not chunk:
                raise OSError("native control connection closed")
            self.buffer += chunk
            if len(self.buffer) > 8192:
                raise ValueError("native control response too long")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line.decode("ascii")

    def send(self, line: str) -> None:
        self.socket.settimeout(self.timeout)
        self.socket.sendall((line + "\n").encode("ascii"))

    def close(self) -> None:
        self.socket.close()
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
