# 贡献指南

感谢你愿意帮 `大肥鱼的考核` 变得更好。这个项目很小，规则也很简单。

## 提交之前

1. 先开 Issue 或在已有 Issue 下说一声，避免重复劳动。
2. Fork 本仓库，从 `main` 切一个分支：`feat/xxx`、`fix/xxx`、`docs/xxx`。
3. 本地跑一遍检查：

```bash
ruff check --select E9,F .
pytest -q
```

4. 提交信息用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：
   - `feat: 支持多实例独立账本`
   - `fix: 批条在重启后丢失`
   - `docs: 补充 L3 配置说明`

## 代码约定

- 只依赖 Python 标准库 + AstrBot API，不引入额外运行时依赖。
- 所有面向用户的文案用中文，日志用 `[moon_gate]` 前缀。
- 新增状态字段时，在 `_load()` 里给默认值，避免老 `gate.json` 崩。
- 涉及权限的改动，必须在 `tests/` 里补一条反向用例（越权要被拒绝）。

## Pull Request

- 一个 PR 只做一件事。
- 描述里写清楚：改了什么、为什么、怎么验证。
- CI 必须全绿；涉及安全模型的改动请在描述里单独说明。

## 行为准则

参与本项目即表示同意遵守 [行为准则](CODE_OF_CONDUCT.md)。
