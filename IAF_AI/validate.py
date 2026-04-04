#!/usr/bin/env python3
"""
Validation CLI for IAF AI v1.0.

Usage:
    python3 validate.py agent          # validate all agents
    python3 validate.py tool           # validate all tool files
    python3 validate.py tube           # validate tubes.json
    python3 validate.py all            # validate everything

Output (LLM-friendly):
    OK
    FAIL: N error(s)
      - [agent:charlie] missing agent_config.json
      - [tool:template/fake_tools.py] TOOLS dict not found
"""

import os
import sys
import json
import glob
import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "template")
TUBE_DIR = os.path.join(PROJECT_ROOT, "tube")


def validate_agents():
    """Validate all agent directories under agents/."""
    errors = []
    if not os.path.isdir(AGENTS_DIR):
        return errors

    for name in sorted(os.listdir(AGENTS_DIR)):
        agent_dir = os.path.join(AGENTS_DIR, name)
        if not os.path.isdir(agent_dir):
            continue

        config_path = os.path.join(agent_dir, "agent_config.json")
        if not os.path.isfile(config_path):
            errors.append(f"[agent:{name}] missing agent_config.json")
            continue

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"[agent:{name}] invalid JSON in agent_config.json: {e}")
            continue

        for field in ("display_name", "provider", "model"):
            if not cfg.get(field):
                errors.append(f"[agent:{name}] agent_config.json missing '{field}'")

        if not os.path.isfile(os.path.join(agent_dir, "core", "direct_llm.py")):
            errors.append(f"[agent:{name}] missing core/direct_llm.py")

        if not os.path.isfile(os.path.join(agent_dir, "core", "tool_executor.py")):
            errors.append(f"[agent:{name}] missing core/tool_executor.py")

        soul_path = os.path.join(agent_dir, "SOUL.md")
        if not os.path.isfile(soul_path):
            errors.append(f"[agent:{name}] missing SOUL.md")
        elif os.path.getsize(soul_path) == 0:
            errors.append(f"[agent:{name}] SOUL.md is empty")

        # Validate provider exists in global config
        provider_name = cfg.get("provider")
        if provider_name:
            global_cfg_path = os.path.join(PROJECT_ROOT, "config.json")
            if os.path.isfile(global_cfg_path):
                try:
                    with open(global_cfg_path, "r", encoding="utf-8") as f:
                        gcfg = json.load(f)
                    if provider_name not in gcfg.get("providers", {}):
                        errors.append(f"[agent:{name}] provider '{provider_name}' not in config.json")
                except (json.JSONDecodeError, IOError):
                    pass

    return errors


def validate_tools():
    """Validate all *_tools.py files in template and agent tools/ directories."""
    errors = []
    dirs_to_check = []

    if os.path.isdir(os.path.join(TEMPLATE_DIR, "tools")):
        dirs_to_check.append(("template", TEMPLATE_DIR))

    if os.path.isdir(AGENTS_DIR):
        for name in sorted(os.listdir(AGENTS_DIR)):
            agent_dir = os.path.join(AGENTS_DIR, name)
            if os.path.isdir(agent_dir):
                dirs_to_check.append((name, agent_dir))

    for label, base_dir in dirs_to_check:
        tools_dir = os.path.join(base_dir, "tools")
        if not os.path.isdir(tools_dir):
            continue

        for filepath in sorted(glob.glob(os.path.join(tools_dir, "*_tools.py"))):
            fname = os.path.basename(filepath)
            try:
                spec = importlib.util.spec_from_file_location(
                    f"validate_{label}_{fname[:-3]}", filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as e:
                errors.append(f"[tool:{label}/{fname}] import error: {e}")
                continue

            if not hasattr(module, "TOOLS"):
                errors.append(f"[tool:{label}/{fname}] missing TOOLS dict")
                continue

            if not isinstance(module.TOOLS, dict):
                errors.append(f"[tool:{label}/{fname}] TOOLS is not a dict")
                continue

            for tname, tdef in module.TOOLS.items():
                if "description" not in tdef:
                    errors.append(f"[tool:{label}/{fname}:{tname}] missing description")
                if "parameters" not in tdef:
                    errors.append(f"[tool:{label}/{fname}:{tname}] missing parameters")
                if "handler" not in tdef:
                    errors.append(f"[tool:{label}/{fname}:{tname}] missing handler")
                elif not callable(tdef["handler"]):
                    errors.append(f"[tool:{label}/{fname}:{tname}] handler not callable")

    return errors


def validate_tubes():
    """Validate tube/tubes.json definitions."""
    errors = []
    tubes_path = os.path.join(TUBE_DIR, "tubes.json")

    if not os.path.isfile(tubes_path):
        return errors

    try:
        with open(tubes_path, "r", encoding="utf-8") as f:
            tubes = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"[tubes.json] invalid JSON: {e}")
        return errors

    if not isinstance(tubes, list):
        errors.append("[tubes.json] root must be a JSON array")
        return errors

    seen_ids = set()
    for i, tube in enumerate(tubes):
        tid = tube.get("id", "")
        if not tid:
            errors.append(f"[tubes.json] tube at index {i} missing 'id'")
            continue
        if tid in seen_ids:
            errors.append(f"[tube:{tid}] duplicate tube id")
        seen_ids.add(tid)

        triggers = tube.get("triggers", [])
        if not triggers:
            errors.append(f"[tube:{tid}] no triggers defined")
        for t in triggers:
            ttype = t.get("type", "")
            if not ttype:
                errors.append(f"[tube:{tid}] trigger missing 'type'")
            else:
                trigger_path = os.path.join(TUBE_DIR, "triggers", f"{ttype}.py")
                if not os.path.isfile(trigger_path):
                    errors.append(f"[tube:{tid}] trigger type '{ttype}' has no module")

        steps = tube.get("steps", [])
        if not steps:
            errors.append(f"[tube:{tid}] no steps defined")
        for j, step in enumerate(steps):
            stype = step.get("type", "")
            if not stype:
                errors.append(f"[tube:{tid}] step {j} missing 'type'")
            elif stype != "tube":
                target_path = os.path.join(TUBE_DIR, "targets", f"{stype}.py")
                if not os.path.isfile(target_path):
                    errors.append(f"[tube:{tid}] step {j} type '{stype}' has no target module")

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 validate.py agent|tool|tube|all")
        sys.exit(1)

    target = sys.argv[1]
    if target not in ("agent", "tool", "tube", "all"):
        print(f"Unknown target: {target}")
        print("Usage: python3 validate.py agent|tool|tube|all")
        sys.exit(1)

    errors = []

    if target in ("agent", "all"):
        errors.extend(validate_agents())
    if target in ("tool", "all"):
        errors.extend(validate_tools())
    if target in ("tube", "all"):
        errors.extend(validate_tubes())

    if not errors:
        print("OK")
    else:
        print(f"FAIL: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
