# 演示脚本：5 分钟看懂 CreditGuard

> 目标：在一台干净的机器（或 GitHub Codespaces）上，用两条命令复现"审计 → 评分 → 原因码 → 分级 → 人工复核 → 导出"的完整链路。

## 0. 准备（30 秒）

```bash
git clone https://github.com/<你的用户名>/<仓库名>.git
cd <仓库名>
python -m pip install -r requirements.txt
```

模型、技能和样例数据都已随仓库提供，**不需要重新训练**。

## 1. 跑一次带人工复核的演示（1 分钟）

```bash
python scripts/demo_offline.py
```

它会用 `data/samples/sample_applications.csv` 里的真实申请跑一遍 Agent，并在终端打印每一步：

- 两条脏数据（缺字段、额度越界）被 **数据审计** 拦下，退回补件，不进入评分；
- 两条低风险申请 **自动通过**；
- 三条高风险申请进入 **人工复核**，并列出 3 条风险因素、2 条缓释因素与建议动作；
- 人工结论（通过 / 拒绝）写回结果，所有"建议拒绝"都必须人工签署。

产物在 `outputs/runs/offline_demo/`：

| 文件 | 用途 |
| --- | --- |
| `run_summary.md` | 人类可读的复核摘要 |
| `review_queue.csv` / `.xlsx` | 可直接发给复核员的清单（Excel 含汇总公式） |
| `results.jsonl` | 每条申请的完整结构化结果 |
| `events.jsonl` | 每一步的时间戳、状态、依据（审计日志） |

## 2. 打开可视化原型（1 分钟）

```bash
python web/server.py
# 浏览器打开 http://127.0.0.1:8000
```

页面提供三种预设：低风险、高风险、脏数据。点"提交评估"即可看到概率、等级、原因码与建议动作。
也可以手动改字段，观察 0.5 阈值与"按容量分级"的差别。

> 在 GitHub Codespaces 里运行 `python web/server.py` 后，VS Code 会把 8000 端口转发成浏览器链接，等于一个在线原型。

## 3. 看实验怎么来的（2 分钟）

```bash
python scripts/evaluate.py --n 4500     # 基线与 Agent 对比、容量扫描、审计消融
python -m pytest tests -q               # 16 个单元测试
python tools/skill_lint.py              # 3 个技能的规范校验（复用开源脚本）
```

结果写在 `outputs/eval/metrics.json`，报告里的表格和曲线都由它生成。

## 4. 对照报告（30 秒）

- 工作流图：`docs/assets/flow.png`（报告图 1）
- 策略对比：`docs/assets/policy.png`（报告图 5）
- 终端运行记录：`docs/assets/console.png`（报告图 7）
- Excel 复核清单：`docs/assets/excel.png`

## 常见问题

**Q：为什么不是大模型对话？**
信贷拒贷是高影响决策，需要逐单可复现、可审计；项目把"语言"限制在模板化原因码，判断交给模型与技能，符合课程"不能把调用大模型当成果"的要求。

**Q：为什么阈值是 0.369 / 0.677 而不是 0.5？**
在验证集上按 15% 复核容量取 85% / 95% 分位，保证复核队列长度等于产能；0.5 会拒掉约 4.85% 的好客户。

**Q：为什么"建议拒绝"还要人工确认？**
误伤成本与合规要求。系统只给建议，最终决定由复核员签署，且全程留痕。
