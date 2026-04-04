# IAF AI v1.0 — LLM Operations Playbook

> 本文档供外部 LLM（Claude Code、GPT Agent 等）阅读。
> 阅读本文件后，你将知道如何通过文件读写和 Shell 命令完整管理 IAF。

## 快速开始

1. `Read MANIFEST.json` — 了解当前系统有哪些 agent、dispatch、tube
2. `Read PLAYBOOK.md` — 你正在读的这个文件
3. 修改前运行 `bash auto_commit.sh "描述"` 创建安全快照
4. 修改后运行 `python3 validate.py all` 验证
5. 运行 `python3 generate_manifest.py` 更新 MANIFEST.json

---

## 1. Agent 管理

### 创建新 Agent

```bash
cp -r template/ agents/{agent_id}/
```

然后：
- 编辑 `agents/{agent_id}/agent_config.json` — 设置 display_name、model
- 编辑 `agents/{agent_id}/SOUL.md` — 定义人格和指令
- 运行 `python3 validate.py agent` 验证
- 运行 `python3 generate_manifest.py` 更新地图

### 修改 Agent 行为

| 修改目标 | 操作文件 |
|----------|----------|
| 人格/指令 | `agents/{id}/SOUL.md` |
| 模型/Provider | `agents/{id}/agent_config.json` |
| 添加上下文文件 | `agent_config.json` 的 `context_files` 数组 |
| 添加技能触发 | `agent_config.json` 的 `skills` 数组 |

### 删除 Agent

1. 删除 `agents/{agent_id}/` 整个目录
2. 检查并移除 `dispatch/*/dispatch_config.json` 和 `tube/tubes.json` 中的引用
3. 运行 `python3 generate_manifest.py`

---

## 2. 工具管理

### 添加工具

1. 阅读 `TOOL_CONTRACT.md` 了解格式约定
2. 在 `agents/{id}/tools/` 下创建 `{name}_tools.py`
3. 无需修改任何代码 — 自动发现机制会在下次调用时加载
4. 运行 `python3 validate.py tool` 验证

### 删除工具

- 删除 `agents/{id}/tools/{name}_tools.py` 文件即可

---

## 3. Agent 引擎修改（重要）

每个 agent 有独立的 `core/direct_llm.py` 和 `core/tool_executor.py` 副本。

### 修改流程

1. 先改一个 agent 的副本并测试
2. 确认无误后，用 `diff` 比对其他 agent 的同名文件
3. 逐个同步需要同样修改的 agent（不是所有 agent 都需要同步）
4. 运行 `python3 validate.py all` 全局验证

### 注意

- 修改前**务必** `bash auto_commit.sh` 创建快照
- 如需给所有新 agent 生效，也要同步修改 `template/core/` 下的模板文件

---

## 4. Tube 管理

### 创建 Tube

编辑 `tube/tubes.json`，追加新条目：

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
      "payload": {"prompt": "执行任务..."},
      "retries": 2,
      "on_fail": "skip"
    }
  ]
}
```

- 修改后每 15 秒自动生效（TubeRunner 热加载）
- 运行 `python3 validate.py tube` 验证

### 手动触发 Tube

```bash
# 方式 A：创建标志文件
touch tube/manual_triggers/{tube_id}.flag

# 方式 B：API 调用
curl -X POST http://127.0.0.1:5000/api/tube/trigger \
  -H "Content-Type: application/json" \
  -d '{"tube_id": "my_tube"}'
```

### 步骤配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `retries` | 失败后重试次数 | 0 |
| `on_fail` | 失败处理：`"stop"` / `"skip"` / `"tube:{id}"` | `"stop"` |

---

## 5. Dispatch 管理

### 添加 Agent 到现有策略

编辑 `dispatch/{strategy}/dispatch_config.json`：
- 在 `agents` 对象中添加 agent 条目
- 在 `turn_order` 数组中添加 agent_id

### 创建新 Dispatch 策略

```bash
cp -r dispatch/roundtable/ dispatch/{name}/
```

然后修改：
- `dispatch.py` — 编排逻辑（只改 ORCHESTRATION LOGIC 部分）
- `dispatch_config.json` — 参与 agent 和设置
- `rules/*.md` — 角色定义

---

## 6. 状态查看

| 查看内容 | 操作 |
|----------|------|
| 系统总览 | `Read MANIFEST.json` |
| Agent 聊天记录 | `Read agents/{id}/history.jsonl` |
| Agent 运行日志 | `Read agents/{id}/call_log.jsonl` |
| Tube 执行日志 | `Read tube/tube_log.jsonl` |
| 步骤间数据 | `Read tube/staging/{tube_id}/step_{n}.out` |
| 排查错误 | `grep "error\|failed" tube/tube_log.jsonl` |
| 实时 Tube 状态 | `GET http://127.0.0.1:5000/api/tube/status` |

---

## 7. 全局配置

编辑 `config.json`：
- 添加新 provider 到 `providers` 对象
- 修改 `default_provider` 或 `default_model`

---

## 8. 安全操作

### 创建安全快照

```bash
bash auto_commit.sh "修改描述"
```

### 危险操作清单（修改前务必快照）

- 删除 `agents/` 下的任何目录
- 修改任何 agent 的 `core/direct_llm.py` 或 `core/tool_executor.py`
- 修改 `config.json` 的 provider key
- 修改 `dispatch/roundtable/dispatch.py` 或 `dispatch_base.py`
- 删除或大幅修改 `tube/tubes.json` 中已有的 tube 定义
- 修改 `lib/` 下的共享基础设施代码

### 回滚

```bash
git diff          # 查看改了什么
git revert HEAD   # 回滚最近一次提交
```

---

## 9. 文件结构速查

```
IAF_AI_v1.0/
├── MANIFEST.json              # 自动生成的系统地图
├── PLAYBOOK.md                # 本操作手册
├── TOOL_CONTRACT.md           # 工具文件格式约定
├── config.json                # 全局 provider/model 配置
├── validate.py                # 验证脚本
├── generate_manifest.py       # MANIFEST 生成器
├── auto_commit.sh             # Git 安全快照
├── chat_server.py             # Flask 服务入口
├── template/                  # Agent 模板（复制创建新 agent）
│   ├── agent_config.json
│   ├── SOUL.md
│   ├── core/direct_llm.py
│   ├── core/tool_executor.py
│   └── tools/*_tools.py
├── agents/{id}/               # 各 Agent 实例
├── dispatch/{strategy}/       # 多 Agent 协作策略
├── tube/
│   ├── tubes.json             # Tube 定义
│   ├── tube_runner.py         # Tube 引擎
│   ├── tube_log.jsonl         # 执行日志
│   ├── triggers/              # 触发器模块
│   ├── targets/               # 目标模块
│   └── staging/               # 步骤间数据传递
└── lib/                       # 共享基础设施
```
