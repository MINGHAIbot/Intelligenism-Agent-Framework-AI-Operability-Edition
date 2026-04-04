#!/usr/bin/env python3
"""
Tube Runner — Signal topology engine for Intelligenism Agent Framework.

The third dimension: connects agents, dispatches, and other tubes via
declarative signal pathways defined in tubes.json.

Polls tubes.json every cycle, checks trigger conditions (OR logic across
a tube's triggers array), and executes step chains sequentially via
subprocess isolation.

Usage:
    python3 tube/tube_runner.py [--interval 15]
"""

import os
import sys
import json
import time
import threading
import subprocess
import argparse
import importlib.util
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TUBE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TUBE_DIR)
TUBES_JSON = os.path.join(TUBE_DIR, "tubes.json")
LOG_FILE = os.path.join(TUBE_DIR, "tube_log.jsonl")
FLAG_DIR = os.path.join(TUBE_DIR, "manual_triggers")
TRIGGERS_DIR = os.path.join(TUBE_DIR, "triggers")
TARGETS_DIR = os.path.join(TUBE_DIR, "targets")

MAX_CHAIN_DEPTH = 5
STEP_TIMEOUT = 3600  # 1 hour per step


# ---------------------------------------------------------------------------
# TubeRunner
# ---------------------------------------------------------------------------

class TubeRunner:

    def __init__(self, interval=15):
        self.interval = interval
        self.running_tubes = {}     # tube_id → Thread
        self.last_triggered = {}    # tube_id → datetime (cron dedup)
        self.lock = threading.Lock()
        self._trigger_cache = {}    # trigger_type → module
        self._target_cache = {}     # target_type → module

    # -------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------

    def _load_tubes(self):
        """Load and return tubes.json. Hot-reloaded every cycle."""
        if not os.path.isfile(TUBES_JSON):
            return []
        try:
            with open(TUBES_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self._log("load_error", error=str(e))
            return []

    def _get_trigger_module(self, trigger_type):
        """Load a trigger module from triggers/, with simple caching."""
        if trigger_type in self._trigger_cache:
            return self._trigger_cache[trigger_type]

        path = os.path.join(TRIGGERS_DIR, f"{trigger_type}.py")
        if not os.path.isfile(path):
            return None

        spec = importlib.util.spec_from_file_location(
            f"trigger_{trigger_type}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return None

        self._trigger_cache[trigger_type] = module
        return module

    def _find_tube(self, tube_id):
        """Look up a tube definition by ID."""
        for t in self._load_tubes():
            if t.get("id") == tube_id:
                return t
        return None

    def _get_target_module(self, target_type):
        """Load a target module from targets/, with simple caching."""
        if target_type in self._target_cache:
            return self._target_cache[target_type]

        path = os.path.join(TARGETS_DIR, f"{target_type}.py")
        if not os.path.isfile(path):
            return None

        spec = importlib.util.spec_from_file_location(
            f"target_{target_type}", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            return None

        self._target_cache[target_type] = module
        return module

    # -------------------------------------------------------------------
    # Trigger checking
    # -------------------------------------------------------------------

    def _check_triggers(self, tube):
        """Return True if ANY trigger in the tube's array fires (OR)."""
        tube_id = tube["id"]
        now = datetime.now(timezone.utc)

        for trigger in tube.get("triggers", []):
            ttype = trigger.get("type")
            config = trigger.get("config", {})
            module = self._get_trigger_module(ttype)
            if module is None:
                continue

            state = {
                "now": now,
                "last_triggered": self.last_triggered.get(tube_id),
                "tube_id": tube_id,
                "flag_dir": FLAG_DIR,
            }

            try:
                if module.check(config, state):
                    return True
            except Exception as e:
                self._log("trigger_error", tube_id=tube_id,
                          trigger_type=ttype, error=str(e))

        return False

    # -------------------------------------------------------------------
    # Step execution
    # -------------------------------------------------------------------

    def _execute_tube(self, tube, depth=0):
        """Run all steps of a tube sequentially. Called in its own thread."""
        tube_id = tube["id"]
        steps = tube.get("steps", [])
        start = time.time()

        self._log("tube_triggered", tube_id=tube_id, step_count=len(steps))

        for i, step in enumerate(steps):
            ok = self._execute_step(tube_id, i, step, depth)
            if not ok:
                self._log("tube_stopped", tube_id=tube_id,
                          stopped_at_step=i,
                          duration_sec=round(time.time() - start, 2))
                break
        else:
            self._log("tube_completed", tube_id=tube_id,
                      duration_sec=round(time.time() - start, 2))

        # Release the running lock
        with self.lock:
            self.running_tubes.pop(tube_id, None)

    def _execute_step(self, tube_id, step_index, step, depth=0):
        """Execute one step. Returns True on success, False to halt."""
        stype = step.get("type")
        sid = step.get("id", "")
        payload = step.get("payload", {})

        # --- Tube-chains-tube (inline, no subprocess) ---
        if stype == "tube":
            if depth >= MAX_CHAIN_DEPTH:
                self._log("step_failed", tube_id=tube_id,
                          step_index=step_index,
                          error=f"Chain depth {MAX_CHAIN_DEPTH} exceeded")
                return False

            target = self._find_tube(sid)
            if target is None:
                self._log("step_failed", tube_id=tube_id,
                          step_index=step_index,
                          error=f"Target tube '{sid}' not found")
                return False

            self._log("step_started", tube_id=tube_id,
                      step_index=step_index, step_type="tube", target=sid)

            for j, sub_step in enumerate(target.get("steps", [])):
                if not self._execute_step(
                        tube_id, f"{step_index}.{j}", sub_step, depth + 1):
                    return False
            return True

        # --- Any other type: pluggable targets/ module ---
        target_module = self._get_target_module(stype)
        if target_module is None:
            self._log("step_failed", tube_id=tube_id,
                      step_index=step_index,
                      error=f"No target module for type: {stype}")
            return False

        try:
            cmd = target_module.build_command(step, PROJECT_ROOT)
        except Exception as e:
            self._log("step_failed", tube_id=tube_id,
                      step_index=step_index,
                      error=f"build_command error: {e}")
            return False

        self._log("step_started", tube_id=tube_id,
                  step_index=step_index, step_type=stype,
                  target=sid, payload=payload)

        max_retries = step.get("retries", 0)
        on_fail = step.get("on_fail", "stop")

        for attempt in range(max_retries + 1):
            start = time.time()
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    cwd=PROJECT_ROOT, timeout=STEP_TIMEOUT)

                duration = round(time.time() - start, 2)
                code = result.returncode
                stdout_tail = (result.stdout or "")[-500:]
                stderr_tail = (result.stderr or "")[-500:]

                if code == 0:
                    # Write stdout to staging for inter-step data passing
                    if (result.stdout or "").strip():
                        staging_dir = os.path.join(
                            TUBE_DIR, "staging", tube_id)
                        os.makedirs(staging_dir, exist_ok=True)
                        staging_file = os.path.join(
                            staging_dir, f"step_{step_index}.out")
                        with open(staging_file, "w", encoding="utf-8") as sf:
                            sf.write(result.stdout or "")

                    self._log("step_completed", tube_id=tube_id,
                              step_index=step_index, exit_code=0,
                              duration_sec=duration, attempt=attempt + 1,
                              stdout_tail=stdout_tail)
                    return True
                else:
                    if attempt < max_retries:
                        self._log("step_retrying", tube_id=tube_id,
                                  step_index=step_index, exit_code=code,
                                  attempt=attempt + 1,
                                  max_retries=max_retries,
                                  stderr_tail=stderr_tail)
                        time.sleep(min(2 ** attempt, 30))
                        continue

                    self._log("step_failed", tube_id=tube_id,
                              step_index=step_index, exit_code=code,
                              duration_sec=duration, attempt=attempt + 1,
                              stderr_tail=stderr_tail)

            except subprocess.TimeoutExpired:
                if attempt < max_retries:
                    self._log("step_retrying", tube_id=tube_id,
                              step_index=step_index,
                              error=f"Timeout ({STEP_TIMEOUT}s)",
                              attempt=attempt + 1,
                              max_retries=max_retries)
                    continue
                self._log("step_failed", tube_id=tube_id,
                          step_index=step_index,
                          error=f"Timeout ({STEP_TIMEOUT}s)",
                          attempt=attempt + 1)

            except Exception as e:
                if attempt < max_retries:
                    self._log("step_retrying", tube_id=tube_id,
                              step_index=step_index, error=str(e),
                              attempt=attempt + 1,
                              max_retries=max_retries)
                    continue
                self._log("step_failed", tube_id=tube_id,
                          step_index=step_index, error=str(e),
                          attempt=attempt + 1)

            break  # fall through to on_fail handling

        # --- on_fail handling ---
        if on_fail == "skip":
            self._log("step_skipped", tube_id=tube_id,
                      step_index=step_index, reason="on_fail=skip")
            return True  # continue to next step
        elif on_fail.startswith("tube:"):
            fallback_id = on_fail[5:]
            fallback = self._find_tube(fallback_id)
            if fallback:
                self._log("on_fail_triggered", tube_id=tube_id,
                          step_index=step_index,
                          fallback_tube=fallback_id)
                self._execute_tube(fallback, depth=depth + 1)
            else:
                self._log("on_fail_error", tube_id=tube_id,
                          step_index=step_index,
                          error=f"Fallback tube '{fallback_id}' not found")
            return False
        else:
            # Default: on_fail="stop"
            return False

    # -------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------

    def _log(self, event, **fields):
        """Append one JSON line to tube_log.jsonl."""
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(),
                 "event": event}
        entry.update(fields)

        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------------
    # Main loop
    # -------------------------------------------------------------------

    def run(self):
        """Poll tubes.json every interval, check triggers, fire steps."""
        os.makedirs(FLAG_DIR, exist_ok=True)
        os.makedirs(os.path.join(TUBE_DIR, "staging"), exist_ok=True)
        self._log("runner_started", interval=self.interval)
        print(f"[tube_runner] Started — polling every {self.interval}s. "
              f"Ctrl+C to stop.")

        try:
            while True:
                for tube in self._load_tubes():
                    if not tube.get("enabled", True):
                        continue

                    tid = tube["id"]

                    with self.lock:
                        if tid in self.running_tubes:
                            continue

                    if self._check_triggers(tube):
                        self.last_triggered[tid] = datetime.now(timezone.utc)
                        t = threading.Thread(
                            target=self._execute_tube,
                            args=(tube,),
                            daemon=True,
                            name=f"tube-{tid}")
                        with self.lock:
                            self.running_tubes[tid] = t
                        t.start()

                time.sleep(self.interval)

        except KeyboardInterrupt:
            self._log("runner_stopped")
            print("\n[tube_runner] Stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Tube Runner — IAF signal topology engine")
    parser.add_argument(
        "--interval", type=int, default=15,
        help="Polling interval in seconds (default: 15)")
    args = parser.parse_args()

    TubeRunner(interval=args.interval).run()


if __name__ == "__main__":
    main()
