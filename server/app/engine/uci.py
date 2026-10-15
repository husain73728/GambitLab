"""A persistent UCI engine session.

Reuses one process for many positions (never one process per move), with a
reader thread, bounded waits and graceful crash handling.
"""
from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


class EngineError(RuntimeError):
    pass


@dataclass
class EngineLine:
    rank: int
    uci: Optional[str]
    cp: Optional[int]      # white POV, or None for mate
    mate: Optional[int]    # white POV signed moves-to-mate, or None
    pv: list[str] = field(default_factory=list)
    depth: int = 0
    nodes: Optional[int] = None


_SCORE_CP = re.compile(r"score cp (-?\d+)")
_SCORE_MATE = re.compile(r"score mate (-?\d+)")
_DEPTH = re.compile(r"\bdepth (\d+)")
_MULTIPV = re.compile(r"\bmultipv (\d+)")
_NODES = re.compile(r"\bnodes (\d+)")


def _sign_for_side(fen: str) -> int:
    """+1 if white to move (score is white POV), -1 if black to move."""
    parts = fen.split()
    return 1 if len(parts) > 1 and parts[1] == "w" else -1


class UCIEngine:
    def __init__(
        self,
        path: str,
        name: str = "engine",
        threads: int = 4,
        hash_mb: int = 128,
        multipv: int = 3,
        timeout: int = 60,
    ):
        self.path = path
        self.name = name
        self.threads = threads
        self.hash_mb = hash_mb
        self.multipv = multipv
        self.timeout = timeout
        self.version: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if not Path(self.path).exists():
            raise EngineError(f"Engine binary not found: {self.path}")
        self._proc = subprocess.Popen(
            [self.path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

        self._send("uci")
        self._read_until(lambda l: l == "uciok", timeout=10)
        self._configure()
        self._send("isready")
        self._read_until(lambda l: l == "readyok", timeout=15)

    def _configure(self) -> None:
        self._send_quiet("setoption name Threads value %d" % self.threads)
        self._send_quiet("setoption name Hash value %d" % self.hash_mb)
        self._send_quiet("setoption name MultiPV value %d" % self.multipv)
        self._send_quiet("setoption name UCI_AnalyseMode value true")

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("id name"):
                self.version = line[len("id name"):].strip()
            self._q.put(line)
        self._q.put(None)  # EOF marker

    def _send(self, cmd: str) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(cmd + "\n")
        self._proc.stdin.flush()

    def _send_quiet(self, cmd: str) -> None:
        try:
            self._send(cmd)
        except Exception:
            pass

    def _read_until(self, pred, timeout: float) -> list[str]:
        out: list[str] = []
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise EngineError("engine timeout")
            try:
                line = self._q.get(timeout=remaining)
            except queue.Empty:
                raise EngineError("engine timeout")
            if line is None:
                raise EngineError("engine exited unexpectedly")
            out.append(line)
            if pred(line):
                return out

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._send("quit")
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass
        finally:
            self._proc = None

    # -- analysis ----------------------------------------------------------
    def analyse(
        self,
        fen: str,
        depth: Optional[int] = None,
        nodes: Optional[int] = None,
        movetime: Optional[int] = None,
        multipv: Optional[int] = None,
    ) -> list[EngineLine]:
        with self._lock:
            if not self.is_alive():
                self.start()
            mpv = multipv or self.multipv
            self._send(f"position fen {fen}")
            go = "go"
            if movetime:
                go += f" movetime {int(movetime)}"
            elif nodes:
                go += f" nodes {int(nodes)}"
            else:
                go += f" depth {int(depth or 14)}"
            go += f" multipv {mpv}"
            self._send(go)

            deadline = time.time() + self.timeout
            best: Optional[str] = None
            lines: dict[int, EngineLine] = {}
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._kill()
                    raise EngineError("analysis timeout")
                try:
                    line = self._q.get(timeout=remaining)
                except queue.Empty:
                    self._kill()
                    raise EngineError("analysis timeout")
                if line is None:
                    self._kill()
                    raise EngineError("engine exited unexpectedly")
                if line.startswith("info"):
                    self._parse_info(line, lines)
                elif line.startswith("bestmove"):
                    best = line.split()[1] if len(line.split()) > 1 else None
                    break

            sign = _sign_for_side(fen)
            result: list[EngineLine] = []
            for rank in sorted(lines):
                ln = lines[rank]
                ln.cp = None if ln.cp is None else ln.cp * sign
                ln.mate = None if ln.mate is None else ln.mate * sign
                result.append(ln)
            if not result and best:
                result = [EngineLine(rank=1, uci=best, cp=None, mate=None, pv=[best])]
            return result

    def _parse_info(self, line: str, lines: dict[int, EngineLine]) -> None:
        m = _MULTIPV.search(line)
        rank = int(m.group(1)) if m else 1
        d = _DEPTH.search(line)
        if not d:
            return  # skip non-score info lines (e.g. currmove)
        cp_m = _SCORE_CP.search(line)
        mate_m = _SCORE_MATE.search(line)
        if cp_m is None and mate_m is None:
            return
        pv: list[str] = []
        if " pv " in line:
            pv = line.split(" pv ", 1)[1].split()
        nodes_m = _NODES.search(line)
        lines[rank] = EngineLine(
            rank=rank,
            uci=pv[0] if pv else None,
            cp=int(cp_m.group(1)) if cp_m else None,
            mate=int(mate_m.group(1)) if mate_m else None,
            pv=pv,
            depth=int(d.group(1)),
            nodes=int(nodes_m.group(1)) if nodes_m else None,
        )

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None


def probe_engine(path: str, timeout: float = 15.0) -> dict:
    """Check availability + identity of an engine binary."""
    if not Path(path).exists():
        return {"available": False, "error": "binary not found", "name": None, "version": None}
    try:
        eng = UCIEngine(path, name="probe", timeout=timeout)
        eng.start()
        info = {"available": True, "error": None, "name": eng.name, "version": eng.version}
        eng.stop()
        return info
    except Exception as exc:
        return {"available": False, "error": str(exc), "name": None, "version": None}
