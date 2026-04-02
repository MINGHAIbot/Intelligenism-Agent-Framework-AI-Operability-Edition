# IAF Architecture Map — AI 操作导航图

**版本 0.4 | 2026-04-02**

> 本文件为外部 LLM（Claude Code、GPT Agent、OpenClaw 等）接管 IAF 时的操作导航图。
> 它回答的不是"每个文件里有什么函数"，而是"哪些文件可以碰、哪些不要碰、碰的时候改哪个区域"。
>
> **核心原则：不到万不得已不动基础设施。99% 的需求通过调整可调整件实现。**
>
> **v0.4 变更：** 整合外部 LLM 全面接管改造方案。新增 MANIFEST.json、validate.py、
> call_log.jsonl、工具热重载、Tube 重试/数据传递、auto_commit.sh 等组件说明。
> 保持 agent 引擎独立副本设计（可能性管理），不引入引擎继承机制。

---

## 零、外部 LLM 接管入口

外部 LLM 首次接手 IAF 实例时，按以下顺序读取三份文件即可开始工作：

| 顺序 | 文件 | 回答的问题 |
|------|------|-----------|
| 1 | `MANIFEST.json` | 系统现在长什么样？有哪些 agent、tube、dispatch？ |
| 2 | `PLAYBOOK.md` | 每个意图对应什么文件操作？操作步骤是什么？ |
| 3 | 本文档 | 系统怎么运转？每个文件什么职责？哪些能碰哪些不能碰？ |

### 0.1 MANIFEST.json（系统地图）

由 `generate_manifest.py` 扫描目录自动生成，也在 `chat_server.py` 启动时自动刷新。

```json
{
  "framework": "IAF",
  "version": "0.1.0",
  "generated_at": "2026-04-01T14:30:00Z",

  "structure": {
    "agents_dir": "agents/",
    "template_dir": "template/",
    "dispatch_dir": "dispatch/",
    "tube_dir": "tube/",
    "global_config": "config.json",
    "tube_config": "tube/tubes.json",
    "tube_log": "tube/tube_log.jsonl",
    "pages_dir": "pages/"
  },

  "agents": {
    "charlie": {
      "config": "agents/charlie/agent_config.json",
      "soul": "agents/charlie/SOUL.md",
      "tools": ["file_tools.py", "shell_tools.py", "dispatch_tools.py", "tube_tools.py"],
      "history": "agents/charlie/history.jsonl",
      "call_log": "agents/charlie/call_log.jsonl",
      "model": "google/gemini-3-flash-preview"
    }
  },

  "dispatches": {
    "roundtable": {
      "config": "dispatch/roundtable/dispatch_config.json",
      "agents": ["charlie", "mcmillan"],
      "ui": "dispatch/roundtable/roundtable.html"
    }
  },

  "tubes": {
    "morning_news": {
      "enabled": true,
      "triggers": ["cron:0 3 * * *", "manual"],
      "steps": ["agent:charlie"]
    }
  },

  "conventions": {
    "tool_file_pattern": "*_tools.py",
    "tool_export_variable": "TOOLS",
    "context_strategy_dir": "context/",
    "skill_dir": "skills/"
  }
}
```

外部 LLM 手动刷新：`python3 generate_manifest.py`

### 0.2 PLAYBOOK.md（操作手册）

纯文本操作手册，覆盖所有常见操作的完整步骤。详见独立文件。

### 0.3 validate.py（验证脚本）

外部 LLM 改完文件后通过 Bash 调用，确认修改是否合法。

```bash
python3 validate.py agent charlie          # 验证单个 agent
python3 validate.py tool agents/charlie/tools/http_tools.py  # 验证工具文件
python3 validate.py tube                   # 验证 tubes.json
python3 validate.py all                    # 全局验证
```

输出格式：成功 → `OK`，失败 → `FAIL: N error(s)` + 逐行错误描述。纯文本，无彩色。

### 0.4 auto_commit.sh（安全快照）

外部 LLM 在执行批量修改前调用：

```bash
bash auto_commit.sh "修改前快照: 准备给 charlie 添加 http 工具"
```

回滚：`git revert HEAD` 或 `git checkout -- {file}`

---

## 一、全局分类

框架中的所有文件分为两类：

| 类别 | 含义 | AI 操作方式 |
|------|------|-----------|
| **基础设施 (Infrastructure)** | 框架怎么运转。管道系统。 | 读一次建立认知，之后不碰 |
| **可调整件 (Adjustable)** | 系统做什么。积木和接线。 | 每次任务都可能操作 |

**判断规则：拿到需求后，先确认能否通过调整可调整件实现。只有当需求涉及框架能力边界本身（新的 LLM 响应格式、新的存储机制、新的通信协议）时，才考虑动基础设施。**

---

## 二、基础设施清单（不要碰）

### 2.1 共享层 lib/

| 文件 | 行数 | 职责 | AI 需要知道的接口 |
|------|------|------|-----------------|
| `lib/llm_client.py` | ~76 | HTTP 调用 LLM + 重试 + 错误分类 | `call_llm(url, key, model, messages, tools=None) → response` |
| `lib/token_utils.py` | ~13 | Token 数量估算 | `estimate_tokens(text) → int` |

### 2.2 Web 服务层

| 文件 | 行数 | 职责 | AI 需要知道的 |
|------|------|------|-------------|
| `chat_server.py` | ~220 | Flask 路由器 + Tube Runner 启动 + MANIFEST 生成 | 不包含业务逻辑，只做路由分发。启动时自动拉起 TubeRunner 后台线程并生成 MANIFEST.json |
| `dispatch_routes.py` | ~330 | Dispatch 层的 Flask Blueprint | 调用 dispatch.py 的公开函数，不包含编排逻辑 |
| `tube_routes.py` | ~280 | Tube 层的 Flask Blueprint | 管 tube 列表、状态查询、手动触发、日志读取/清除 |

### 2.3 Agent 引擎 template/

| 文件 | 行数 | 职责 | AI 需要知道的 |
|------|------|------|-------------|
| `template/core/direct_llm.py` | ~290 | 基础循环引擎核心 | `call_agent(message, mode, max_loops) → response`。通过 `context_files` 配置加载 system prompt。包含 call_log.jsonl 结构化日志写入 |
| `template/core/tool_executor.py` | ~60 | 工具自动发现注册表 + 热重载 | 扫描 tools/*_tools.py，导入 TOOLS 字典。每次 execute() 调用前检查 tools/ 目录 mtime，有变化自动重扫 |
| `template/context/sliding_window.py` | ~47 | 默认上下文裁切策略 | `trim(messages, max_tokens) → trimmed_messages` |
| `template/tools/file_tools.py` | ~78 | 默认工具集（读写文件、列目录） | 复制到新 Agent 后可替换或扩展 |
| `template/tools/TOOL_CONTRACT.md` | — | 工具文件格式合约 | 外部 LLM 写新工具时参考此文件 |

> **注意：** `template/` 是复制源。创建新 Agent 时 `cp -r template/ agents/xxx/`，
> 之后 agents/xxx/ 里的文件就是可调整件了。template/ 本身不要动。

**direct_llm.py 的 build_messages 五层拼装模型：**

```
Layer 1: context_files 内容 → 拼接为 system prompt
Layer 2: skills 触发匹配 → 命中时注入为 user+assistant 对话对
Layer 3: history.jsonl → 仅 chat 模式加载，batch 模式跳过
Layer 4: 当前用户消息
Layer 5: trim 裁切 → 确保不超过 max_context - 8000
```

**direct_llm.py 路径解析规则（context_files 和 skill_file 共用）：**

| 优先级 | 解析方式 | 示例 |
|--------|---------|------|
| 1 | Agent 目录相对路径 | `"SOUL.md"` → `agents/xxx/SOUL.md` |
| 2 | 框架根目录相对路径 | `"dispatch/roundtable/rules/default.md"` |
| 3 | 绝对路径 | `"/data/external/reference.md"` |

**direct_llm.py 结构化日志（call_log.jsonl）：**

每次 `call_agent()` 调用在 `agents/xxx/call_log.jsonl` 记录以下事件：

| 事件 | 关键字段 | 含义 |
|------|---------|------|
| `call_started` | model, mode, message_preview | Agent 被调用 |
| `llm_call` | loop, tokens_est, duration_ms | 一次 LLM API 调用 |
| `tool_call` | loop, tool_name, args_summary, result_length, is_error | 一次工具调用 |
| `call_completed` | loops_used, reply_length, total_duration_ms | Agent 返回结果 |
| `call_failed` | error | Agent 调用失败 |

外部 LLM 查看：`tail -20 agents/xxx/call_log.jsonl` 或 `grep "tool_error" agents/xxx/call_log.jsonl`

### 2.4 Dispatch 策略基础设施

每个 dispatch 策略文件夹内，以下文件是基础设施：

| 文件 | 行数 | 职责 | AI 需要知道的 |
|------|------|------|-------------|
| `dispatch_base.py` | ~478 | 工具循环、LLM 响应解析、staging 管理、状态追踪 | 见下方接口表 |
| `session_manager.py` | ~200 | JSONL session 的增删查改 + staging 格式化 | `create_session()`, `append_to_session()`, `load_session()`, `list_sessions()`, `delete_session()`, `format_session_history()` |
| `context_injector.py` | ~80 | 按 context_files 路径列表读取文件，构建 messages 数组 | `build_context(agent_id, config, project_root, user_message) → (messages, provider, model)` |
| `context/sliding_window.py` | ~150 | 配置驱动的上下文裁切 | `trim_records(records, max_tokens, trim_strategy) → trimmed_records` |

**dispatch_base.py 关键接口：**

```
get_llm_caller(project_root) → call_llm_fn or None
load_global_config(project_root) → dict
resolve_llm_endpoint(provider, global_config) → (url, key)
load_agent_tools(agent_id, project_root) → (tool_definitions, tool_functions)
call_with_tool_loop(messages, url, key, model, call_llm_fn, tool_definitions, tool_functions, max_tool_loops) → (content, tool_history)
write_agent_memory(agent_id, tool_history) → None
write_staging_history(project_root, session_id) → None
clear_staging() → None
set_status(session_id, round_num, agent_id, agent_name, status) → None
clear_status() → None
get_status() → dict
```

### 2.5 Tube 层基础设施

#### 2.5.1 核心引擎

| 文件 | 行数 | 职责 | AI 需要知道的 |
|------|------|------|-------------|
| `tube/tube_runner.py` | ~370 | 主循环引擎：轮询 tubes.json、检查触发条件、串行执行 steps（支持重试和失败策略）、写日志、管理 staging 数据传递 | `TubeRunner(interval=15).run()` — 作为 daemon 线程在 chat_server 中运行 |

**运行机制要点：**

- 每 15 秒轮询一次 tubes.json（热加载，改配置不重启）
- 每条 tube 触发后在独立线程中执行，多条 tube 可并行
- running_tubes 字典防止同一条 tube 重复触发
- Steps 默认串行：上一步退出码 0 才跑下一步，非 0 按 on_fail 配置决定（stop 或 continue）
- 支持步骤级重试（retry.max + retry.delay_sec）
- 步骤间数据通过 staging 文件传递（$PREV_OUTPUT 占位符）
- type=tube 的 step 内联递归执行（深度限制 5 层）
- 其他 type 的 step 通过 targets/ 模块构建命令，subprocess 执行

#### 2.5.2 可插拔触发源 triggers/

每个 .py 文件是一种触发源类型，统一接口：

```python
def check(config: dict, state: dict) -> bool
```

| 文件 | 行数 | 职责 | config 示例 |
|------|------|------|------------|
| `triggers/cron.py` | ~44 | 定时触发（依赖 croniter） | `{"expr": "0 3 * * *"}` |
| `triggers/manual.py` | ~32 | flag 文件触发（API 或文件创建） | `{}`（不需要 config） |

**state 字段（由 tube_runner 提供）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `now` | datetime (UTC) | 当前时间 |
| `last_triggered` | datetime or None | 该 tube 上次触发时间 |
| `tube_id` | str | 当前 tube 的 ID |
| `flag_dir` | str | 手动触发 flag 文件目录路径 |

> **用户扩展：** 在 triggers/ 放一个 .py 文件，实现 `check()` 接口。零代码改动。

#### 2.5.3 可插拔驱动目标 targets/

每个 .py 文件是一种驱动目标类型，统一接口：

```python
def build_command(step: dict, project_root: str) -> list[str]
```

| 文件 | 行数 | 职责 | step.type |
|------|------|------|-----------|
| `targets/agent.py` | ~34 | 构建 Agent 子进程命令 | `"agent"` |
| `targets/dispatch.py` | ~40 | 构建 Dispatch 子进程命令 | `"dispatch"` |

> **用户扩展：** 在 targets/ 放一个 .py 文件，实现 `build_command()` 接口。零代码改动。
>
> **例外：** type=tube 的 step 不走 targets/ 模块，由 tube_runner 内联递归处理。

#### 2.5.4 CLI 入口

| 文件 | 行数 | 职责 | 命令行用法 |
|------|------|------|-----------|
| `tube/run_agent.py` | ~65 | Agent subprocess 桥接 | `python3 tube/run_agent.py --agent-id default --mode batch --prompt "..."` |
| `tube/run_dispatch.py` | ~92 | Dispatch subprocess 桥接 | `python3 tube/run_dispatch.py --strategy roundtable --message "..."` |

#### 2.5.5 运行时文件

| 文件/目录 | 说明 |
|----------|------|
| `tube/tube_log.jsonl` | 执行日志，所有 tube 共用，追加式写入 |
| `tube/manual_triggers/` | flag 文件目录，API 写入 `{tube_id}.flag`，tube_runner 扫描到后删除 |
| `tube/staging/{tube_id}_{timestamp}/` | 步骤间数据传递目录，每步输出写入 step_N_output.txt |

#### 2.5.6 Tube API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/tubes` | 列出所有 tube 定义 + 实时 running/idle 状态 |
| GET | `/api/tube/status` | 轻量状态查询（仅 id, enabled, status） |
| POST | `/api/tube/trigger` | 手动触发（request body: `{"tube_id": "xxx"}`） |
| GET | `/api/tube/log?tail=50&tube_id=xxx` | 查询日志（支持过滤） |
| GET | `/api/tube/log/grouped?per_tube=10` | 按 tube 分组返回日志 |
| DELETE | `/api/tube/log?tube_id=xxx` | 清除日志（可按 tube 单独清除） |

#### 2.5.7 tube_log.jsonl 事件类型

| 事件 | 关键字段 | 含义 |
|------|---------|------|
| `runner_started` | interval | tube_runner 启动 |
| `runner_stopped` | — | tube_runner 停止 |
| `tube_triggered` | tube_id, step_count | tube 被触发 |
| `step_started` | tube_id, step_index, step_type, step_target, payload | 某一步开始 |
| `step_completed` | tube_id, step_index, step_type, step_target, exit_code, duration_sec | 某一步成功 |
| `step_failed` | tube_id, step_index, step_type, step_target, exit_code, duration_sec, stderr_tail | 某一步失败 |
| `step_retry` | tube_id, step_index, attempt, max_attempts, delay_sec | 某一步重试 |
| `tube_completed` | tube_id, duration_sec | 全部步骤完成 |
| `tube_stopped` | tube_id, stopped_at_step, duration_sec | 因某步失败中止 |
| `trigger_error` | tube_id, trigger_type, error | trigger 检查异常 |

### 2.6 框架级辅助工具

| 文件 | 职责 | 使用者 |
|------|------|--------|
| `generate_manifest.py` | 扫描目录生成 MANIFEST.json | 外部 LLM 通过 Bash 调用 |
| `validate.py` | 验证 agent/tool/tube 配置合法性 | 外部 LLM 通过 Bash 调用 |
| `auto_commit.sh` | Git 快照（批量修改前的安全网） | 外部 LLM 通过 Bash 调用 |

这三个文件是基础设施，但外部 LLM **只调用不修改**。

---

## 三、可调整件清单（AI 操作的目标）

### 3.1 Agent 可调整件

每个 `agents/xxx/` 文件夹内：

| 文件 | 作用 | 修改场景 |
|------|------|---------|
| **agent_config.json** | 模型、provider、context 来源、skill 触发规则 | 换模型、改 context 文件列表、加减 skill 触发 |
| **SOUL.md** | Agent 身份定义（通过 context_files 引用） | 改人格、角色、行为准则 |
| **skills/*.md** | 任务指令文件 | 增减指令内容 |
| **tools/*_tools.py** | Agent 可用的工具 | 增减工具（放文件即生效，热重载自动发现） |
| **context/sliding_window.py** | 该 Agent 的裁切策略 | 如需与默认不同的裁切行为 |

> **引擎代码**（core/direct_llm.py, core/tool_executor.py）属于半基础设施：
> 从 template 复制后默认不改。只有当用户需要该 Agent 在引擎层面与其他 Agent
> 彻底不同时才修改——这是"可能性管理"的核心承诺。
>
> **引擎修改操作规范：** 每个 agent 有独立的引擎副本。修改引擎逻辑时：
> 1. 先改一个 agent 的副本并测试
> 2. 确认无误后，用 `diff` 比对其他 agent 的同名文件
> 3. 逐个同步需要同样修改的 agent（不是所有 agent 都需要同步——有些可能有特殊逻辑）
> 4. 同步完成后运行 `python3 validate.py all`

#### agent_config.json 完整字段定义

```json
{
  "display_name": "Research Agent",
  "provider": "openrouter",
  "model": "google/gemini-3-flash-preview",
  "max_context": 200000,
  "trim_strategy": "sliding_window",
  "context_files": [
    "SOUL.md",
    "knowledge/domain_guide.md",
    "skills/skill_router.md"
  ],
  "skills": [
    {
      "trigger": "深度审查",
      "match_type": "exact",
      "skill_file": "skills/deep_review_checklist.md"
    }
  ]
}
```

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `display_name` | string | 否 | UI 和日志中显示的名称，默认 "Agent" |
| `provider` | string | 否 | 引用 config.json 中的 provider 名称，默认用 config.json 的 default_provider |
| `model` | string | 否 | LLM 模型标识符，默认用 config.json 的 default_model |
| `max_context` | int | 否 | 最大 context 窗口 token 数，默认 120000 |
| `trim_strategy` | string | 否 | 裁切策略名称，对应 context/ 下的 .py 文件名，默认 "sliding_window" |
| `context_files` | array | 否 | 每次调用都加载的文件路径列表。未指定时自动回退到 `["SOUL.md"]` |
| `skills` | array | 否 | 条件触发的技能规则列表，默认空数组 |

**context_files 说明：**

列出的所有文件在每次 LLM 调用时都加载，拼接为 system prompt。路径解析走三级优先级（agent 目录 → 框架根目录 → 绝对路径）。文件不存在时静默跳过。

典型配置：

| 文件类型 | 示例路径 | 用途 |
|---------|---------|------|
| 身份定义 | `"SOUL.md"` | Agent 的人格和行为准则 |
| 领域知识 | `"knowledge/product_spec.md"` | 永久参考信息 |
| Skill 路由表 | `"skills/skill_router.md"` | 告诉 LLM 什么场景该读哪个 skill 文件 |
| 跨模块引用 | `"dispatch/roundtable/rules/default.md"` | 引用其他模块的文件 |

**skills 数组说明：**

每条 skill 是一个触发规则对象：

| 字段 | 类型 | 说明 |
|------|------|------|
| `trigger` | string | 匹配关键词 |
| `match_type` | string | `"contains"`（消息包含）、`"startswith"`（消息前缀）、`"exact"`（完全匹配） |
| `skill_file` | string | 命中时加载的 .md 文件路径（走同样的三级路径解析） |

注意：trigger 是纯字符串匹配，不是语义理解。"代码审查"不会命中"代码检查"。可配多条规则指向同一文件覆盖不同说法，也可配合 context_files 中的 skill_router.md 让 LLM 通过 read_file 工具语义触发。

#### 可用工具文件清单

| 文件 | 工具 | 能力 | 默认自带 |
|------|------|------|---------|
| `file_tools.py` | read_file, write_file, list_dir | 读写文件、列目录 | 是（template 自带） |
| `shell_tools.py` | run_shell | 执行终端命令（30s 超时，输出截断保护） | 否，按需放入 |
| `tube_tools.py` | trigger_tube, list_tubes, tube_log | 触发 tube、查 tube 状态、读 tube 日志 | 否，按需放入 |
| `dispatch_tools.py` | run_dispatch, list_dispatch_strategies | 发起多 Agent 协作、列出可用策略 | 否，按需放入 |

工具文件放到 `agents/xxx/tools/` 目录，热重载自动发现，不改任何代码。不需要的工具不放，不占 context。

**TOOLS 字典格式（创建新工具时遵循，详见 template/tools/TOOL_CONTRACT.md）：**

```python
TOOLS = {
    "tool_name": {
        "description": "工具功能描述（LLM 根据这段话判断何时使用）",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数说明"}
            },
            "required": ["param1"]
        },
        "handler": _handler_function  # 接收 dict 参数，返回字符串
    }
}
```

**Handler 约定要点（完整合约见 TOOL_CONTRACT.md）：**
- 入参 dict，返回 str
- 失败返回 "Error: ..." 开头的字符串
- 内部捕获所有异常，不让异常冒泡
- 长操作设 timeout，输出超 5000 字符截断

#### Agent 运行时文件

| 文件 | 说明 | 外部 LLM 用法 |
|------|------|-------------|
| `history.jsonl` | 聊天记录（chat 模式追加） | `tail -20 agents/xxx/history.jsonl` |
| `call_log.jsonl` | 结构化运行日志（每次调用追加） | `tail -20 agents/xxx/call_log.jsonl` |

### 3.2 Dispatch 可调整件

每个 `dispatch/xxx/` 文件夹内：

| 文件 | 作用 | 修改场景 |
|------|------|---------|
| **dispatch.py** | 编排逻辑 | 改协作模式（轮流发言→辩论→星形拓扑→串行流水线） |
| **dispatch_config.json** | 参与 Agent、轮数、裁切策略、context_files | 增减 Agent、改轮数、改 context 来源 |
| **rules/*.md** | Agent 在本次协作中的角色定义 | 改 Agent 在协作中扮演的角色 |

**dispatch.py 修改指南：**

```
dispatch.py（~288 行）的结构：

第 1-70 行:     imports + 公开 API 声明        → 一般不改
第 74-78 行:    new_session()                  → 一般不改
第 81-120 行:   run_streaming() 前置准备        → 一般不改
                (LLM caller、global config、
                 session、工具预加载)

┌─────────────────────────────────────────────┐
│ 第 126-210 行: ORCHESTRATION LOGIC          │ ← 改这里
│   双层 for 循环: rounds × turn_order        │
│   每个 agent turn 的调用序列               │
│   轮次标记和终止条件                        │
└─────────────────────────────────────────────┘

第 214-220 行:  清理和 done 事件               → 一般不改
第 228-270 行:  run() 包装器                   → 不改
第 276-288 行:  session 便捷函数               → 不改
```

#### dispatch_config.json 完整字段定义

```json
{
  "display_name": "Roundtable Discussion",
  "description": "Multi-agent roundtable discussion",
  "max_rounds": 3,
  "max_history_tokens": 3000,
  "trim_strategy": {
    "keep_first_user_input": true,
    "keep_last_user_input": true,
    "drop_order": "oldest_first"
  },
  "agents": {
    "charlie": {
      "display_name": "Strategist",
      "provider": "from_agent",
      "model": "from_agent",
      "context_files": [
        "agents/charlie/SOUL.md",
        "dispatch/roundtable/rules/charlie.md",
        "dispatch/roundtable/staging/session_history.md"
      ]
    }
  },
  "turn_order": ["charlie", "mcmillan"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `display_name` | string | 策略显示名称 |
| `description` | string | 策略描述（AI 调 list_dispatch_strategies 时看到） |
| `max_rounds` | int | 最大讨论轮数 |
| `max_history_tokens` | int | session 历史的 token 预算 |
| `trim_strategy` | object | 裁切策略配置 |
| `agents` | object | 参与 Agent 配置。key 是 agent ID |
| `agents.{id}.display_name` | string | 该 Agent 在此协作中的显示名 |
| `agents.{id}.provider` | string | `"from_agent"` 则从 agent_config.json 读取，也可直接写死 |
| `agents.{id}.model` | string | 同上，可覆盖 Agent 自身配置 |
| `agents.{id}.context_files` | array | 该 Agent 在此协作中读取的文件列表（框架根目录相对路径） |
| `turn_order` | array | Agent 每轮的发言顺序 |

**关键设计：** Dispatch 不调用 Agent 的 call_agent。它直接调 lib/llm_client.call_llm()，自己通过 context_injector 组装 context。Agent 文件夹对 Dispatch 而言只是数据源（SOUL.md、rules、config），不是执行器。

### 3.3 Tube 可调整件

| 文件 | 作用 | 修改场景 |
|------|------|---------|
| **tube/tubes.json** | 全部 tube 的声明式定义——唯一拓扑真相源 | 增删 tube、改触发条件、改步骤、改信号拓扑 |
| **pages/tube-dashboard.html** | Tube 可视化监控页面 | 自定义 UI 展示 |

**tubes.json 字段定义：**

tubes.json 是一个 JSON 数组，每个元素是一条 tube：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识符。用于日志、API 调用、tube 间引用 |
| `enabled` | boolean | 否 | 默认 true。设为 false 时 tube_runner 跳过 |
| `triggers` | array | 是 | 触发源数组，**OR 关系**——任意一个命中就 fire |
| `triggers[].type` | string | 是 | 触发源类型名，对应 `triggers/{type}.py` |
| `triggers[].config` | object | 否 | 传给 `check()` 的配置。cron 需要 `{"expr": "..."}` |
| `steps` | array | 是 | 执行步骤数组，**默认串行**——上一步成功才跑下一步 |
| `steps[].type` | string | 是 | 目标类型名，对应 `targets/{type}.py`，或 `"tube"` |
| `steps[].id` | string | 是 | 目标 ID（agent 名 / dispatch 策略名 / tube ID） |
| `steps[].mode` | string | 否 | Agent 专用：`"batch"` 或 `"chat"`（默认 batch） |
| `steps[].payload` | object | 否 | 传递给目标的数据。支持 `$PREV_OUTPUT` 占位符引用上一步输出文件路径 |
| `steps[].retry` | object | 否 | 重试配置：`{"max": 3, "delay_sec": 30}` |
| `steps[].on_fail` | string | 否 | 失败策略：`"stop"`（默认，停止后续步骤）或 `"continue"`（跳过继续） |

**tubes.json 完整示例：**

```json
[
  {
    "id": "morning_news",
    "enabled": true,
    "triggers": [
      { "type": "cron", "config": { "expr": "0 3 * * *" } },
      { "type": "manual" }
    ],
    "steps": [
      {
        "type": "agent",
        "id": "charlie",
        "mode": "batch",
        "payload": { "prompt": "搜集过去24小时的AI领域重要新闻" }
      }
    ]
  },
  {
    "id": "site_monitor",
    "enabled": true,
    "triggers": [
      { "type": "cron", "config": { "expr": "*/10 * * * *" } }
    ],
    "steps": [
      {
        "type": "agent",
        "id": "monitor",
        "mode": "batch",
        "payload": { "prompt": "检查网站状态" },
        "retry": { "max": 3, "delay_sec": 30 },
        "on_fail": "continue"
      },
      {
        "type": "agent",
        "id": "reporter",
        "mode": "batch",
        "payload": { "prompt": "根据 $PREV_OUTPUT 生成状态报告" },
        "on_fail": "stop"
      }
    ]
  },
  {
    "id": "doc_analysis_pipeline",
    "enabled": false,
    "triggers": [
      { "type": "manual" }
    ],
    "steps": [
      {
        "type": "agent",
        "id": "doc_processor",
        "mode": "batch",
        "payload": { "prompt": "处理并分析上传的文档" }
      },
      {
        "type": "dispatch",
        "id": "roundtable",
        "payload": { "message": "基于文档分析结果进行头脑风暴讨论" }
      },
      {
        "type": "tube",
        "id": "send_report"
      }
    ]
  }
]
```

**触发机制全景：**

| 触发来源 | 触发者 | 机制 |
|---------|--------|------|
| Cron 定时 | tube_runner 自动 | croniter 比对时间表达式，每 15 秒轮询 |
| API 调用 | 人类 / AI agent / 外部系统 | `POST /api/tube/trigger` → flag 文件 → 下个周期扫描 |
| Tube 链式 | 上游 tube 的 step | steps 中 `type=tube` → 内联执行目标 tube 的 steps |

**驱动目标全景：**

| 目标类型 | steps 配置 | 执行方式 |
|---------|-----------|---------|
| Agent | `{"type":"agent","id":"xxx","mode":"batch","payload":{...}}` | subprocess → run_agent.py |
| Dispatch | `{"type":"dispatch","id":"xxx","payload":{...}}` | subprocess → run_dispatch.py |
| Tube | `{"type":"tube","id":"xxx"}` | 内联递归执行目标 tube 的 steps |
| 用户自定义 | `{"type":"自定义","payload":{...}}` | 用户在 targets/ 放对应 .py |

**步骤间数据传递：**

每个 tube 执行时创建 `tube/staging/{tube_id}_{timestamp}/` 目录。
每步的 stdout 写入 `step_N_output.txt`。下一步的 payload 中 `$PREV_OUTPUT` 被替换为上一步输出文件的绝对路径。
外部 LLM 可通过 `Read tube/staging/...` 查看每步的输入输出，方便调试。

### 3.4 UI 可调整件

| 文件 | 作用 | 修改场景 |
|------|------|---------|
| **index.html** | 黄页，功能入口索引 | 一般不改（自动发现） |
| **chat.html** | 基础聊天界面 | 自定义聊天 UI |
| **pages/*.html** | 用户自建功能页面 | 加页面 = 放文件 |
| **dispatch/xxx/*.html** | Dispatch 专属 UI | 自定义协作界面 |

---

## 四、AI 操作决策树

```
收到需求
  │
  ├─ 需要新 Agent？
  │   → bash auto_commit.sh "新增 agent 前快照"
  │   → cp -r template/ agents/xxx/
  │   → 编辑 SOUL.md
  │   → 编辑 agent_config.json（设置 context_files、skills、model）
  │   → 不碰引擎代码
  │   → python3 validate.py agent xxx
  │   → python3 generate_manifest.py
  │
  ├─ 需要改 Agent 读取的文件？
  │   → 编辑 agent_config.json 的 context_files 数组
  │   → 加路径 = 加文件，删路径 = 减文件
  │   → 不碰 direct_llm.py
  │
  ├─ 需要给 Agent 加工具？
  │   → 参考 template/tools/TOOL_CONTRACT.md 了解格式
  │   → 在 agents/xxx/tools/ 放 *_tools.py 文件
  │   → 热重载自动发现，不改任何代码
  │   → python3 validate.py tool agents/xxx/tools/新工具_tools.py
  │
  ├─ 需要让 Agent 能执行终端命令？
  │   → cp template/tools/shell_tools.py agents/xxx/tools/
  │
  ├─ 需要让 Agent 能触发 Tube？
  │   → cp template/tools/tube_tools.py agents/xxx/tools/
  │
  ├─ 需要让 Agent 能发起多 Agent 协作？
  │   → cp template/tools/dispatch_tools.py agents/xxx/tools/
  │
  ├─ 需要给 Agent 加技能？
  │   → 在 agents/xxx/skills/ 放 .md 文件
  │   → 方式 A：在 agent_config.json 的 skills 数组加触发规则（精确匹配）
  │   → 方式 B：在 skill_router.md 的路由表加一行（语义触发，需 file_tools）
  │   → 方式 C：直接加到 context_files（全量注入，每次都在）
  │
  ├─ 需要新 Dispatch 策略？
  │   → cp -r dispatch/roundtable/ dispatch/xxx/
  │   → 编辑 dispatch.py 的 ORCHESTRATION LOGIC 区域
  │   → 编辑 dispatch_config.json, rules/
  │   → 不碰 dispatch_base.py, session_manager.py, context_injector.py
  │
  ├─ 需要调整信号拓扑？
  │   → 编辑 tube/tubes.json
  │   → 不碰 tube_runner.py, triggers/, targets/
  │   → python3 validate.py tube
  │
  ├─ 需要新的 Tube 触发源类型？
  │   → 在 tube/triggers/ 放 .py 文件，实现 check(config, state) → bool
  │   → tubes.json 中用文件名作为 type
  │   → 不碰 tube_runner.py
  │
  ├─ 需要新的 Tube 驱动目标类型？
  │   → 在 tube/targets/ 放 .py 文件，实现 build_command(step, project_root) → list
  │   → tubes.json 的 steps 中用文件名作为 type
  │   → 不碰 tube_runner.py
  │
  ├─ 需要手动触发 Tube？
  │   → curl -X POST http://127.0.0.1:5000/api/tube/trigger \
  │       -H "Content-Type: application/json" \
  │       -d '{"tube_id": "xxx"}'
  │   → 或 touch tube/manual_triggers/xxx
  │   → 或让 Agent 通过 tube_tools.py 触发
  │
  ├─ 需要查看系统运行状态？
  │   → Agent 聊天记录：tail agents/xxx/history.jsonl
  │   → Agent 运行日志：tail agents/xxx/call_log.jsonl
  │   → Tube 执行日志：tail tube/tube_log.jsonl
  │   → Tube 步骤输出：Read tube/staging/{tube_id}_{timestamp}/
  │   → 错误排查：grep "error\|failed" tube/tube_log.jsonl
  │   → 全局验证：python3 validate.py all
  │
  ├─ 需要修改 Agent 引擎逻辑？
  │   → bash auto_commit.sh "引擎修改前快照"
  │   → 先改一个 agent 的 core/ 副本并测试
  │   → diff 比对其他 agent 的同名文件
  │   → 逐个同步（注意：不是所有 agent 都需要同步）
  │   → python3 validate.py all
  │
  ├─ 需要新 UI 页面？
  │   → 在 pages/ 放 .html 文件
  │   → 黄页自动发现
  │
  ├─ 需要回滚修改？
  │   → git diff → 看改了什么
  │   → git log --oneline -10 → 看历史快照
  │   → git checkout -- {file} → 恢复单个文件
  │   → git revert HEAD → 回滚最近一次提交
  │
  └─ 以上都不满足？
      → 可能需要动基础设施
      → 先确认：真的不能通过可调整件实现吗？
      → 如果确认，读对应的基础设施源码，理解后修改
      → 修改后 python3 validate.py all 验证不影响其他模块
```

---

## 五、创建新 Dispatch 策略的完整步骤

```bash
# 0. 安全快照
bash auto_commit.sh "新增 dispatch 策略前快照"

# 1. 复制现有策略作为起点
cp -r dispatch/roundtable/ dispatch/debate/

# 2. 编辑 dispatch_config.json
#    - 修改 display_name, description
#    - 修改 agents（参与者列表、context_files、model）
#    - 修改 turn_order
#    - 调整 max_rounds, max_history_tokens

# 3. 编辑 rules/*.md
#    - 为每个 Agent 定义在本次协作中的角色
#    - 比如 rules/prosecutor.md, rules/defender.md, rules/judge.md

# 4. 编辑 dispatch.py 的 ORCHESTRATION LOGIC 区域
#    - 原版: 双层 for 循环（rounds × turn_order），轮流发言
#    - 辩论版: 正方发言 → 反方发言 → 评委打分 → 判断是否继续
#    - 只改这个区域，上下的准备代码和清理代码不动

# 5. （可选）修改或新建 HTML 页面

# 6. 验证：刷新首页，新策略自动出现
python3 generate_manifest.py
bash auto_commit.sh "新增 debate dispatch 策略"
```

**dispatch_base.py、session_manager.py、context_injector.py、sliding_window.py 原样复制过去，不需要看，不需要改。**

---

## 六、创建新 Agent 的完整步骤

```bash
# 0. 安全快照
bash auto_commit.sh "新增 agent 前快照"

# 1. 复制模板
cp -r template/ agents/researcher/

# 2. 编辑 SOUL.md
#    定义 Agent 的身份、角色、行为准则

# 3. 编辑 agent_config.json
#    - 设置 display_name, provider, model, max_context
#    - 配置 context_files 列表（至少包含 "SOUL.md"）
#    - 配置 skills 触发规则（可选）

# 4. （可选）在 skills/ 放 .md 文件
#    定义特定场景下的任务指令

# 5. （可选）在 tools/ 放 *_tools.py 文件
#    增加 Agent 可用的工具
#    常用工具：shell_tools.py, tube_tools.py, dispatch_tools.py
#    新写工具参考 template/tools/TOOL_CONTRACT.md

# 6. 验证
python3 validate.py agent researcher

# 7. 更新系统地图
python3 generate_manifest.py

# 8. 保存
bash auto_commit.sh "新增 researcher agent"

# 9. 测试：通过 API 或 chat.html 发消息给新 Agent
```

**core/direct_llm.py、core/tool_executor.py 原样复制过去，默认不改。**

---

## 七、创建新 Tube 的完整步骤

```bash
# 1. 编辑 tube/tubes.json，在数组中添加一条记录
#    不需要创建文件夹，不需要写代码

# 2. 验证
python3 validate.py tube

# 3. 保存文件。下个轮询周期（15 秒内）自动生效

# 4. 触发方式（三选一）：
#    - curl -X POST http://127.0.0.1:5000/api/tube/trigger \
#        -H "Content-Type: application/json" \
#        -d '{"tube_id": "my_pipeline"}'
#    - touch tube/manual_triggers/my_pipeline
#    - Agent 通过 tube_tools.py 触发

# 5. 查看结果：
#    - tail tube/tube_log.jsonl
#    - Read tube/staging/{tube_id}_{timestamp}/（查看步骤间数据）
#    - curl http://127.0.0.1:5000/api/tube/log?tube_id=my_pipeline

# 6. 更新系统地图
python3 generate_manifest.py
```

---

## 八、扩展 Tube 触发源或驱动目标

```bash
# 扩展触发源：
# 1. 在 tube/triggers/ 放一个 .py 文件
# 2. 实现 check(config, state) → bool
# 3. tubes.json 中 trigger.type 使用文件名（不含 .py）

# 扩展驱动目标：
# 1. 在 tube/targets/ 放一个 .py 文件
# 2. 实现 build_command(step, project_root) → list[str]
# 3. tubes.json 的 steps 中用文件名作为 type
```

**不碰 tube_runner.py。放文件即生效。**

---

## 九、Agent 能力三层模型速查

| 层 | 载体 | 配置位置 | 加载时机 | 用途 |
|---|------|---------|---------|------|
| 身份与知识 | .md / .txt 文件 | agent_config.json 的 `context_files` | 每次调用 | Agent 永远知道的信息 |
| 条件指令 | .md 文件 + 触发规则 | agent_config.json 的 `skills` | 关键词命中时 | 特定场景注入的指令 |
| 执行能力 | *_tools.py 文件 | 自动发现（放文件即生效，热重载） | 每次调用 | Agent 能做的操作 |

**Skill 触发的三种方式：**

| 方式 | 机制 | 可靠性 | token 成本 | 配置位置 |
|------|------|--------|-----------|---------|
| skills 精确匹配 | 框架关键词匹配 | 精确但可能漏 | 低（命中才加载） | agent_config.json skills 数组 |
| skill_router + read_file | LLM 语义判断 + 工具调用 | 高（语义理解） | 中（路由表常驻） | context_files 引用路由表 .md |
| context_files 全量注入 | 每次都加载 | 100% 不漏 | 高（每次都占） | context_files 直接引用 .md |

三种方式可叠加使用。推荐组合：context_files 放路由表做兜底，skills 放精确触发做加速。

---

## 十、文件变动影响范围速查

| 我改了这个文件 | 影响范围 |
|--------------|---------|
| agents/xxx/SOUL.md | 仅该 Agent |
| agents/xxx/agent_config.json | 仅该 Agent |
| agents/xxx/skills/*.md | 仅该 Agent |
| agents/xxx/tools/*.py | 仅该 Agent（热重载，下次调用生效） |
| agents/xxx/core/direct_llm.py | 仅该 Agent（其他 agent 有独立副本，不受影响） |
| agents/xxx/core/tool_executor.py | 仅该 Agent（同上） |
| dispatch/xxx/dispatch.py | 仅该 Dispatch 策略 |
| dispatch/xxx/dispatch_config.json | 仅该 Dispatch 策略 |
| dispatch/xxx/rules/*.md | 仅该 Dispatch 策略 |
| tube/tubes.json | 信号拓扑（不影响 Agent 和 Dispatch 内部） |
| tube/triggers/新增.py | 仅使用该 trigger type 的 tube |
| tube/targets/新增.py | 仅使用该 target type 的 tube |
| pages/*.html | 仅该页面 |
| MANIFEST.json | 无运行时影响（仅供外部 LLM 读取） |
| lib/llm_client.py | **全局** — 所有 Agent 和 Dispatch 的 LLM 调用 |
| chat_server.py | **全局** — 所有 API 路由 + Tube Runner 启动 |
| dispatch_routes.py | **全局** — 所有 Dispatch API 路由 |
| tube_routes.py | **全局** — 所有 Tube API 路由 |
| tube/tube_runner.py | **全局** — 所有 Tube 的轮询和执行 |
| template/ | **无直接影响** — 只影响未来新建的 Agent |

> **关键特征：** 前 14 行的影响范围都是"仅该模块"或"仅使用它的 tube"。
> 这就是模块隔离的价值——AI 可以安全做局部修改，无全局副作用。

---

## 十一、热重载机制速查

| 文件类型 | 热重载方式 | 生效时机 |
|---------|-----------|---------|
| agent_config.json | `_load_config()` 每次 call_agent() 重读 | 下次 agent 被调用 |
| SOUL.md / context_files | `_load_context_files()` 每次重读 | 下次 agent 被调用 |
| tools/*_tools.py | tool_executor 检查 tools/ 目录 mtime | 下次 agent 被调用 |
| tubes.json | tube_runner 每轮询周期重新 `_load_tubes()` | 下个轮询周期（≤15 秒） |
| dispatch_config.json | 每次 dispatch 调用重读 | 下次 dispatch 被调用 |
| rules/*.md | 通过 context_injector 每次重读 | 下次 dispatch 被调用 |
| pages/*.html | Flask 路由每次请求重读 | 下次页面被访问 |

**结论：外部 LLM 改完文件后，不需要重启服务器。所有可调整件都是热加载的。**

---

## 十二、危险操作清单（修改前务必 git commit）

| 操作 | 风险等级 | 说明 |
|------|---------|------|
| 删除 agents/ 下的目录 | 高 | Agent 数据和历史永久丢失 |
| 修改 config.json 的 provider key | 高 | 所有 agent 的 LLM 调用可能失败 |
| 修改任何 agent 的 core/direct_llm.py | 中 | 仅影响该 agent，但可能破坏基础循环 |
| 修改任何 agent 的 core/tool_executor.py | 中 | 仅影响该 agent，但可能导致工具加载失败 |
| 修改 dispatch/xxx/dispatch_base.py | 高 | 影响该策略所有协作会话 |
| 修改 lib/llm_client.py | 高 | 影响全局所有 LLM 调用 |
| 修改 tube/tube_runner.py | 高 | 影响全局所有 Tube 执行 |
| 删除或大幅修改 tubes.json 中已有 tube | 中 | 可能中断正在运行的自动化流程 |

**操作前必做：** `bash auto_commit.sh "修改描述"`
**操作后必做：** `python3 validate.py all`

---

## 十三、外部 LLM 完整接管验收场景

```
1. Read MANIFEST.json
   → 了解系统有哪些 agent、tube、dispatch

2. Read PLAYBOOK.md
   → 知道怎么操作

3. Bash: bash auto_commit.sh "修改前快照"
   → 安全备份

4. Bash: cp -r template/ agents/monitor/
   → 创建新 agent

5. Write agents/monitor/SOUL.md
   → 写入 "你是一个网站监控 agent，每次被调用时检查网站状态..."

6. Edit agents/monitor/agent_config.json
   → 设置 display_name, model

7. Read template/tools/TOOL_CONTRACT.md
   → 了解工具文件格式

8. Write agents/monitor/tools/http_tools.py
   → 写入符合合约的 HTTP 检查工具

9. Bash: python3 validate.py agent monitor
   → 输出 "OK"

10. Edit tube/tubes.json
    → 添加一条每 10 分钟触发 monitor agent 的 tube

11. Bash: python3 validate.py tube
    → 输出 "OK"

12. Bash: python3 generate_manifest.py
    → 更新 MANIFEST.json

13. Bash: bash auto_commit.sh "新增 monitor agent 和定时检查 tube"
    → 保存修改

14. 等 10 分钟后:
    Read tube/tube_log.jsonl → 确认 tube 触发了
    Read agents/monitor/call_log.jsonl → 确认 agent 运行了

15. 如果有问题:
    Bash: git diff → 看改了什么
    Bash: git revert HEAD → 回滚
```

---

## 十四、当前缺失项（待改造实施）

| 项目 | 状态 | 对应改造 Phase | 说明 |
|------|------|--------------|------|
| ~~Tube 模块~~ | 已完成 | — | tube_runner + triggers + targets + CLI + API + Dashboard |
| ~~CLI 入口标准化~~ | 已完成 | — | run_agent.py + run_dispatch.py |
| ~~tubes.json 完整文档~~ | 已完成 | — | 本文档 3.3 节 |
| ~~agent_config.json 字段定义~~ | 已完成 | — | 本文档 3.1 节 |
| ~~dispatch_config.json 字段定义~~ | 已完成 | — | 本文档 3.2 节 |
| ~~context_files 机制~~ | 已完成 | — | direct_llm.py 重构 |
| ~~Agent 工具清单~~ | 已完成 | — | file/shell/tube/dispatch tools |
| MANIFEST.json + generate_manifest.py | 待实施 | Phase 1 | 系统地图，外部 LLM 一次 Read 掌握全局 |
| PLAYBOOK.md | 待实施 | Phase 2 | 操作手册，意图→文件操作的映射 |
| validate.py | 待实施 | Phase 3 | 验证脚本，改完配置立即确认 |
| TOOL_CONTRACT.md | 待实施 | Phase 4 | 工具文件格式合约 |
| call_log.jsonl 结构化日志 | 待实施 | Phase 5 | Agent 运行日志，需同步到所有 agent 的 direct_llm.py |
| tool_executor.py 热重载 | 待实施 | Phase 6 | mtime 检测自动重扫，需同步到所有 agent 的 tool_executor.py |
| auto_commit.sh | 待实施 | Phase 7 | Git 快照脚本 |
| Tube 重试 + on_fail | 待实施 | Phase 8 | tube_runner.py 步骤级重试和失败策略 |
| Tube 步骤间数据传递 | 待实施 | Phase 8 | staging 目录 + $PREV_OUTPUT 占位符 |
| tube_log.jsonl 字段增强 | 待实施 | Phase 8 | 补充 step_type, step_target, retry 事件 |
