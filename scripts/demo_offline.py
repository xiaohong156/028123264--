# -*- coding: utf-8 -*-
"""一键演示：克隆仓库后无需训练、无需下载数据即可跑通完整 Agent 链路。

用法：
    python scripts/demo_offline.py

它用 data/samples/sample_applications.csv 中的真实申请，另注入两条脏数据，
演示 数据审计 → 评分 → 原因码 → 复核策略 → 人工复核 → 导出 的全流程。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard import schema  # noqa: E402
from creditguard.agent import CreditAgent  # noqa: E402
from creditguard.tools import io as T  # noqa: E402

SAMPLE = os.path.join(ROOT, "data", "samples", "sample_applications.csv")
OUT = os.path.join(ROOT, "outputs", "runs", "offline_demo")


def reviewer(result):
    """演示用的脚本化复核员：概率高就拒绝，否则通过。真实系统里由人输入。"""
    p = result.get("p") or 0.0
    return "人工拒绝" if p >= 0.55 else "人工通过"


def main():
    records = T.load_records(SAMPLE)[:6]
    # 注入两条脏数据：一条缺字段，一条额度越界
    bad_missing = dict(records[0])
    bad_missing["ID"] = "D-001"
    bad_missing.pop("PAY_3", None)
    bad_range = dict(records[1])
    bad_range["ID"] = "D-002"
    bad_range["LIMIT_BAL"] = 3000
    # 一条明显高风险的申请：连续逾期 + 额度几乎用满 + 几乎不还款
    high = dict(records[2])
    high.update({"ID": "H-001", "LIMIT_BAL": 30000, "PAY_0": 3, "PAY_2": 3, "PAY_3": 2,
                 "PAY_4": 2, "PAY_5": 2, "PAY_6": 1,
                 "BILL_AMT1": 29500, "BILL_AMT2": 29000, "BILL_AMT3": 28500,
                 "BILL_AMT4": 28000, "BILL_AMT5": 27500, "BILL_AMT6": 27000,
                 "PAY_AMT1": 0, "PAY_AMT2": 200, "PAY_AMT3": 0,
                 "PAY_AMT4": 0, "PAY_AMT5": 0, "PAY_AMT6": 0})
    records = [bad_missing, bad_range, high] + records[2:]

    agent = CreditAgent()
    print("CreditGuard 离线演示 | 模型 %s | 技能 %s" % (
        os.path.basename(agent.model_path), ", ".join(agent.registry.names())))
    print("输入 %d 条申请（其中 2 条故意构造为脏数据）\n" % len(records))

    payload = agent.run_batch(records, OUT, interactive=True, reviewer=reviewer)
    summary = payload["summary"]
    print("\n完成 %d 条：评分 %d，退回补件 %d，平均耗时 %.1f ms" % (
        summary["n"], summary["scored"], summary["rejected_by_audit"], summary["mean_latency_ms"]))
    print("动作分布:", summary["by_action"])
    print("\n结果已写入:", OUT)
    print(" - run_summary.md / review_queue.csv / review_queue.xlsx")
    print(" - results.jsonl / events.jsonl")


if __name__ == "__main__":
    main()
