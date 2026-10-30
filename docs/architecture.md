# 架构与实现

## 参与方

```
┌──────────────┐   写/改/回滚    ┌────────────────────┐
│  溟月的工坊   │ ─────────────▶ │ events.jsonl        │
│  (workshop)  │   +2 / −3 / −5  │ (append-only JSONL) │
└──────────────┘                 └─────────┬──────────┘
                                           │ 增量消费
                                           ▼
                                  ┌─────────────────┐
                                  │ 大肥鱼的考核     │
                                  │ (moon_gate)     │
                                  └───┬─────┬───────┘
                                      │     │
                              积分/等级 │     │ 改配置 / 改人格
                                      ▼     ▼
                              gate.json   AstrBot config / data_v4.db
```

## 运行时序

1. 插件加载：`StarTools.get_data_dir()` → `gate.json` 读取（缺省 `score=0, level=0`）。
2. 任意状态查询或写操作前调用 `_level()`：
   - `_consume_workshop()` 从上次 `consumed_ledger` 偏移继续读 `events.jsonl`，逐条累加分数；
   - `_evaluate()` 检查门槛：L1 达标直接升级；L2/L3 达标只设置 `pending_level`，等主人 `/提权 批准`。
3. `_write_config(plugin, key, value)`：
   - 红线检查 → 受保护插件检查 → 等级检查 → L1 前缀检查 → `cmd_config` 白名单与批条检查；
   - 写前备份原文件到 `backups/<ts>_<name>`；
   - 合并点号路径后写回（`utf-8-sig`），失败自动还原。
4. `gate_config_set` 成功后调用 `context._star_manager.reload(plugin)`，让插件读取新配置。
5. `gate_persona_set`（L2+）：
   - 先备份旧人格文本到 `backups/persona_<ts>.txt`；
   - `await context.persona_manager.update_persona("default", system_prompt=...)`；
   - 失败则用备份回滚。

## 状态文件

```json
{
  "score": 0,
  "level": 0,
  "pending_level": 0,
  "last_star_ts": 0.0,
  "events": [{"ts": "...", "epoch": 0.0, "kind": "write_ok", "delta": 2, "detail": "..."}],
  "consumed_ledger": 0,
  "cmd_ticket": 0
}
```

- `events` 最多保留 500 条，超出裁剪；
- `consumed_ledger` 是 `events.jsonl` 的字节偏移，保证只消费一次；
- `cmd_ticket` 是 L3 一次性批条计数。

## 为什么不直接读 AstrBot 事件总线

工坊的写操作发生在 AI 发起工具调用时，天然有结构化结果（成功/失败/回滚），比从聊天记录里猜更可靠。账本是唯一事实源，考核只做「记账 + 门槛判定」，职责清晰，也方便单测。

## 已知限制

- 事件账本是普通 JSONL，主人或拥有写权限的进程可以手改；
- 插件重载与配置写入不是原子操作，极端情况下可能短暂出现半新半旧配置；
- L3 的 `cmd_config` 改动写入后，AstrBot 全局配置若在内存中有旧副本，可能需要重启才会完全生效，因此默认只放行展示类键。
