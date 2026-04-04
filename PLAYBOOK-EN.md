# IAF AI-Piloted Edition — LLM Operations Playbook

> This document is for external LLMs (Claude Code, GPT Agent, etc.) to read.
> After reading this file, you will know how to fully manage IAF through file read/write and shell commands.

## Quick Start

1. `Read MANIFEST.json` — Understand what agents, dispatches, and tubes currently exist
2. `Read PLAYBOOK.md` — This file you are reading now
3. Before any modification, run `bash auto_commit.sh "description"` to create a safety snapshot
4. After modification, run `python3 validate.py all` to validate
5. Run `python3 generate_manifest.py` to update MANIFEST.json

---

## 1. Agent Management

### Create a New Agent

```bash
cp -r template/ agents/{agent_id}/
```

Then:
- Edit `agents/{agent_id}/agent_config.json` — set display_name, model
- Edit `agents/{agent_id}/SOUL.md` — define personality and instructions
- Run `python3 validate.py agent {agent_id}` to validate
- Run `python3 generate_manifest.py` to update the map

### Modify Agent Behaviour

| Modification Target | File to Edit |
|---------------------|-------------|
| Personality / Instructions | `agents/{id}/SOUL.md` |
| Model / Provider | `agents/{id}/agent_config.json` |
| Add context files | `agent_config.json` → `context_files` array |
| Add skill triggers | `agent_config.json` → `skills` array |

### Delete an Agent

1. Delete the entire `agents/{agent_id}/` directory
2. Check and remove references in `dispatch/*/dispatch_config.json` and `tube/tubes.json`
3. Run `python3 generate_manifest.py`

---

## 2. Tool Management

### Add a Tool

1. Read `TOOL_CONTRACT.md` to understand format conventions
2. Create `{name}_tools.py` in `agents/{id}/tools/`
3. No code changes needed — auto-discovery mechanism loads it on next call
4. Run `python3 validate.py tool agents/{id}/tools/{name}_tools.py` to validate

### Remove a Tool

- Simply delete the `agents/{id}/tools/{name}_tools.py` file.

---

## 3. Agent Engine Modification (Important)

Each agent has its own independent copy of `core/direct_llm.py` and `core/tool_executor.py`.

### Modification Procedure

1. Modify one agent's copy first and test
2. After confirmation, use `diff` to compare against other agents' same-named files
3. Sync individually to agents that need the same modification (not all agents need syncing)
4. Run `python3 validate.py all` for global validation

### Important Notes

- **Always** run `bash auto_commit.sh` to create a snapshot before modifying engine files
- If the change should apply to all future new agents, also sync the modification to `template/core/` template files

---

## 4. Tube Management

### Create a Tube

Edit `tube/tubes.json`, append a new entry:

```json
{
  "id": "my_tube",
  "enabled": true,
  "triggers": [
    {"type": "cron", "config": {"expr": "*/10 * * * *"}},
    {"type": "manual"}
  ],
  "steps": [
    {
      "type": "agent",
      "id": "charlie",
      "mode": "batch",
      "payload": {"prompt": "Execute task..."},
      "retry": {"max": 2, "delay_sec": 30},
      "on_fail": "continue"
    }
  ]
}
```

- Changes auto-effective every 15 seconds (TubeRunner hot-loads)
- Run `python3 validate.py tube` to validate

### Manually Trigger a Tube

```bash
# Method A: Create flag file
touch tube/manual_triggers/{tube_id}.flag

# Method B: API call
curl -X POST http://127.0.0.1:5000/api/tube/trigger \
  -H "Content-Type: application/json" \
  -d '{"tube_id": "my_tube"}'
```

### Step Configuration

| Field | Description | Default |
|-------|-------------|---------|
| `retry` | Retry config: `{"max": N, "delay_sec": N}` | No retry |
| `on_fail` | Failure handling: `"stop"` / `"continue"` | `"stop"` |

---

## 5. Dispatch Management

### Add an Agent to an Existing Strategy

Edit `dispatch/{strategy}/dispatch_config.json`:
- Add agent entry in the `agents` object
- Add agent_id to the `turn_order` array

### Create a New Dispatch Strategy

```bash
cp -r dispatch/roundtable/ dispatch/{name}/
```

Then modify:
- `dispatch.py` — Orchestration logic (only modify the ORCHESTRATION LOGIC section)
- `dispatch_config.json` — Participating agents and settings
- `rules/*.md` — Role definitions

---

## 6. Status Viewing

| What to View | Operation |
|-------------|-----------|
| System overview | `Read MANIFEST.json` |
| Agent chat history | `Read agents/{id}/history.jsonl` |
| Agent run log | `Read agents/{id}/call_log.jsonl` |
| Tube execution log | `Read tube/tube_log.jsonl` |
| Inter-step data | `Read tube/staging/{tube_id}/step_{n}.out` |
| Troubleshoot errors | `grep "error\|failed" tube/tube_log.jsonl` |
| Real-time Tube status | `GET http://127.0.0.1:5000/api/tube/status` |

---

## 7. Global Configuration

Edit `config.json`:
- Add new provider to the `providers` object
- Modify `default_provider` or `default_model`

---

## 8. Safety Operations

### Create Safety Snapshot

```bash
bash auto_commit.sh "modification description"
```

### Dangerous Operations Checklist (Always Snapshot Before)

- Deleting any directory under `agents/`
- Modifying any agent's `core/direct_llm.py` or `core/tool_executor.py`
- Modifying `config.json` provider keys
- Modifying `dispatch/*/dispatch.py` or `dispatch_base.py`
- Deleting or heavily modifying existing tube definitions in `tube/tubes.json`
- Modifying shared infrastructure code under `lib/`

### Rollback

```bash
git diff          # See what changed
git revert HEAD   # Rollback most recent commit
```

---

## 9. File Structure Quick Reference

```
IAF_AI_Piloted/
├── MANIFEST.json              # Auto-generated system map
├── PLAYBOOK.md                # This operations manual
├── TOOL_CONTRACT.md           # Tool file format contract
├── config.json                # Global provider/model configuration
├── validate.py                # Validation script
├── generate_manifest.py       # MANIFEST generator
├── auto_commit.sh             # Git safety snapshot
├── chat_server.py             # Flask service entry point
├── template/                  # Agent template (copy to create new agent)
│   ├── agent_config.json
│   ├── SOUL.md
│   ├── core/direct_llm.py
│   ├── core/tool_executor.py
│   └── tools/*_tools.py
├── agents/{id}/               # Individual Agent instances
├── dispatch/{strategy}/       # Multi-Agent collaboration strategies
├── tube/
│   ├── tubes.json             # Tube definitions
│   ├── tube_runner.py         # Tube engine
│   ├── tube_log.jsonl         # Execution log
│   ├── triggers/              # Trigger modules
│   ├── targets/               # Target modules
│   └── staging/               # Inter-step data passing
└── lib/                       # Shared infrastructure
```
