#!/usr/bin/env python3
"""
Generate MANIFEST.json — machine-readable system map.
Scans agents/, dispatch/, tube/tubes.json and writes MANIFEST.json.

Run manually:  python3 generate_manifest.py
Auto-called:   chat_server.py calls generate() on startup.
"""

import os
import json
import glob
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "template")
DISPATCH_DIR = os.path.join(PROJECT_ROOT, "dispatch")
TUBE_DIR = os.path.join(PROJECT_ROOT, "tube")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "MANIFEST.json")


def _scan_agents():
    """Scan agents/ directory. Returns dict of agent_id → info."""
    agents = {}
    if not os.path.isdir(AGENTS_DIR):
        return agents

    for name in sorted(os.listdir(AGENTS_DIR)):
        agent_dir = os.path.join(AGENTS_DIR, name)
        config_path = os.path.join(agent_dir, "agent_config.json")
        if not os.path.isdir(agent_dir) or not os.path.isfile(config_path):
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        tools = [os.path.basename(p) for p in
                 sorted(glob.glob(os.path.join(agent_dir, "tools", "*_tools.py")))]

        agents[name] = {
            "config": f"agents/{name}/agent_config.json",
            "soul": f"agents/{name}/SOUL.md",
            "tools": tools,
            "history": f"agents/{name}/history.jsonl",
            "model": cfg.get("model", "unknown"),
        }
    return agents


def _scan_dispatches():
    """Scan dispatch/ directory. Returns dict of strategy_name → info."""
    dispatches = {}
    if not os.path.isdir(DISPATCH_DIR):
        return dispatches

    for name in sorted(os.listdir(DISPATCH_DIR)):
        strategy_dir = os.path.join(DISPATCH_DIR, name)
        dispatch_py = os.path.join(strategy_dir, "dispatch.py")
        if not os.path.isdir(strategy_dir) or not os.path.isfile(dispatch_py):
            continue

        config_path = os.path.join(strategy_dir, "dispatch_config.json")
        cfg = {}
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        agents = list(cfg.get("agents", {}).keys())
        ui_html = os.path.join(strategy_dir, f"{name}.html")

        dispatches[name] = {
            "config": f"dispatch/{name}/dispatch_config.json",
            "agents": agents,
            "ui": f"dispatch/{name}/{name}.html" if os.path.isfile(ui_html) else None,
        }
    return dispatches


def _scan_tubes():
    """Load tube/tubes.json. Returns dict of tube_id → summary."""
    tubes = {}
    tubes_path = os.path.join(TUBE_DIR, "tubes.json")
    if not os.path.isfile(tubes_path):
        return tubes

    try:
        with open(tubes_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return tubes

    for tube in data:
        tid = tube.get("id", "")
        if not tid:
            continue
        triggers = [t.get("type", "") for t in tube.get("triggers", [])]
        steps = [{"type": s.get("type", ""), "id": s.get("id", "")}
                 for s in tube.get("steps", [])]
        tubes[tid] = {
            "enabled": tube.get("enabled", True),
            "triggers": triggers,
            "steps": steps,
        }
    return tubes


def generate():
    """Build and write MANIFEST.json."""
    template_tools = [os.path.basename(p) for p in
                      sorted(glob.glob(os.path.join(TEMPLATE_DIR, "tools", "*_tools.py")))]

    manifest = {
        "framework": "IAF",
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),

        "structure": {
            "agents_dir": "agents/",
            "template_dir": "template/",
            "dispatch_dir": "dispatch/",
            "tube_dir": "tube/",
            "global_config": "config.json",
            "tube_config": "tube/tubes.json",
            "tube_log": "tube/tube_log.jsonl",
            "pages_dir": "pages/",
        },

        "agents": _scan_agents(),
        "dispatches": _scan_dispatches(),
        "tubes": _scan_tubes(),

        "conventions": {
            "tool_file_pattern": "*_tools.py",
            "tool_export_variable": "TOOLS",
            "context_strategy_dir": "context/",
            "skill_dir": "skills/",
            "template_tools": template_tools,
        },
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


if __name__ == "__main__":
    generate()
    print(f"MANIFEST.json generated at {MANIFEST_PATH}")
