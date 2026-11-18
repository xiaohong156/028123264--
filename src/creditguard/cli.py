# -*- coding: utf-8 -*-
"""CreditGuard 命令行入口。

用法
----
    python -m creditguard.cli demo --n 8 --out outputs/runs/demo
    python -m creditguard.cli demo --n 8 --out outputs/runs/demo --interactive
    python -m creditguard.cli batch --input data/samples/sample_applications.csv --out outputs/runs/batch
"""
from __future__ import annotations

import argparse
import os
import sys

from .agent import CreditAgent, EventLogger
from .tools import io as T


def _demo_records(n: int, seed: int = 7, corrupt: bool = False):
    """从原始数据中抽取若干条真实申请，构造演示输入。"""
    import numpy as np
    import pandas as pd

    from . import schema
    from .ml import data as D

    df = D.load_raw()
    rng = np.random.RandomState(seed)
    idx = rng.choice(len(df), size=n, replace=False)
    rows = df.iloc[idx].drop(columns=[schema.TARGET]).to_dict(orient="records")
    if corrupt and rows:
        # 故意制造一条脏数据，用于演示数据审计与退回补件
        rows[0] = dict(rows[0])
        rows[0]["LIMIT_BAL"] = 5000
        rows[0]["AGE"] = 15
        rows[0].pop("PAY_3", None)
    return rows


def cmd_demo(args):
    out_dir = os.path.abspath(args.out)
    records = _demo_records(args.n, corrupt=args.with_bad_case)
    agent = CreditAgent(logger=EventLogger(os.path.join(out_dir, "events.jsonl")))
    print("CreditGuard v1.0 | 模型: %s | 技能: %s" % (
        agent.model_path, ", ".join(agent.registry.names())))
    payload = agent.run_batch(records, out_dir, interactive=args.interactive)
    s = payload["summary"]
    print("\n完成 %d 条：评分 %d，退回补件 %d，平均耗时 %.1f ms" % (
        s["n"], s["scored"], s["rejected_by_audit"], s["mean_latency_ms"]))
    print("动作分布:", s["by_action"])
    print("结果目录:", out_dir)


def cmd_batch(args):
    records = T.load_records(os.path.abspath(args.input))
    agent = CreditAgent(logger=EventLogger())
    payload = agent.run_batch(records, os.path.abspath(args.out), interactive=args.interactive)
    print("处理完成:", payload["summary"]["n"], "条 →", payload["out_dir"])


def cmd_skills(args):
    agent = CreditAgent()
    for item in agent.registry.manifest():
        print("- %(name)s v%(version)s [%(license)s]\n  %(description)s" % item)


def build_parser():
    ap = argparse.ArgumentParser(prog="creditguard", description="信贷初审风险复核 Agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="用真实样本跑一次演示")
    p_demo.add_argument("--n", type=int, default=8)
    p_demo.add_argument("--out", default="outputs/runs/demo")
    p_demo.add_argument("--interactive", action="store_true", help="开启人工复核交互")
    p_demo.add_argument("--with-bad-case", action="store_true", help="注入一条脏数据演示退回补件")
    p_demo.set_defaults(func=cmd_demo)

    p_batch = sub.add_parser("batch", help="批量处理 CSV/JSON 申请")
    p_batch.add_argument("--input", required=True)
    p_batch.add_argument("--out", required=True)
    p_batch.add_argument("--interactive", action="store_true")
    p_batch.set_defaults(func=cmd_batch)

    p_skills = sub.add_parser("skills", help="列出已注册技能")
    p_skills.set_defaults(func=cmd_skills)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
