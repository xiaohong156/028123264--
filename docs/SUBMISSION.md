# 提交材料清单（对应课程要求 ①②③④）

> 按“学号_姓名_项目名称”命名提交的 PDF，其余材料用仓库链接。

| 要求 | 本项目的材料 | 位置 / 链接 |
| --- | --- | --- |
| ① 报告 PDF | 课程报告（16 页，正文约 3900 字） | [`report/CreditGuard_期末报告.pdf`](../report/CreditGuard_期末报告.pdf) ｜ 网页版副本 [`docs/assets/report.pdf`](assets/report.pdf) |
| ② 可访问的代码仓库 | 本仓库（README 含依赖、运行步骤、结果） | `https://github.com/xiaohong156/028123264--` |
| ③ 演示材料 / 可运行原型 | 命令行一键演示、Web 原型、运行截图、演示脚本 | 见下方“三种演示入口” |
| ④ 复用组件与许可证说明 | 报告附录 B + 独立清单 + 仓库内 commit 记录 | [`THIRD_PARTY.md`](../THIRD_PARTY.md)、[`vendor/anthropic-skills/VENDOR.md`](../vendor/anthropic-skills/VENDOR.md) |

## 三种演示入口

1. **30 秒命令行**（无需训练、无需下载数据）：
   ```bash
   python scripts/demo_offline.py
   ```
   终端会依次展示：脏数据退回 → 自动通过 → 高风险转人工 → 原因码 → 导出清单。

2. **Web 原型**（可交互单笔试算）：
   ```bash
   python web/server.py    # http://127.0.0.1:8000
   ```
   三个预设：低风险 / 高风险 / 脏数据；也可手动改字段。

3. **GitHub 页面**：
   - 展示页（GitHub Pages）：`https://xiaohong156.github.io/028123264--/`
   - Codespaces 一键运行：仓库页 → Code → Codespaces → Create codespace → 运行上面的命令
   - CI 徽章：每次 push 自动跑 16 个单元测试、技能校验与一键演示

## 截图素材

| 文件 | 内容 |
| --- | --- |
| `docs/assets/console.png` | 终端完整运行记录（报告图 7） |
| `docs/assets/excel.png` | 导出的 Excel 复核清单 |
| `docs/assets/flow.png` | Agent 工作流（报告图 1） |
| `docs/assets/policy.png` | 不同策略对比（报告图 5） |

## 提交前检查

- [ ] 仓库为 **Public**（否则老师打不开 Pages 与 Codespaces）
- [ ] 已运行 `python scripts/set_repo.py <owner>/<repo>`，README 徽章与链接不再是 `OWNER/REPO`
- [ ] GitHub Actions 最近一次运行是绿色
- [ ] Settings → Pages 已选择 `main` 分支的 `/docs` 目录，页面可访问
- [ ] 报告封面已填写姓名、学号、组员分工
- [ ] 报告 PDF 文件名符合“学号_姓名_项目名称”
