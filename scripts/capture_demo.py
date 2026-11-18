# -*- coding: utf-8 -*-
"""录制一次"带人工复核"的完整运行过程，输出纯文本日志（用于报告截图）。

真实运行时复核员在终端里输入 a/r/s；这里用脚本化的复核员代替，
并把 stdout 同时写到 outputs/runs/demo_console.txt。
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard import schema  # noqa: E402
from creditguard.agent import CreditAgent, EventLogger  # noqa: E402
from creditguard.ml import data as D  # noqa: E402

OUT_DIR = os.path.join(ROOT, "outputs", "runs", "demo_live")
LOG_PATH = os.path.join(ROOT, "outputs", "runs", "demo_console.txt")


def make_records(n=6, seed=11):
    """挑出低/中/高三档真实申请各若干条，便于展示完整分支。"""
    import numpy as np

    from creditguard.ml.model import LinearScorecard

    df = D.load_raw()
    card = LinearScorecard.load(os.path.join(ROOT, "models", "logreg_v1.json"))
    sample = df.sample(n=min(3000, len(df)), random_state=seed)
    X = D.build_features(D.clean(sample))[card.features].values.astype(float)
    p = card.predict_proba(X)

    order = np.argsort(p)
    picks = [
        order[int(0.10 * len(order))],   # 低风险
        order[int(0.28 * len(order))],   # 低风险
        order[int(0.88 * len(order))],   # 复核区间
        order[int(0.93 * len(order))],   # 复核区间
        order[-6],                        # 建议拒绝区间
    ]
    records = sample.iloc[picks].drop(columns=[schema.TARGET]).to_dict(orient="records")
    # 追加两条脏数据，演示审计拦截
    bad1 = dict(records[0]); bad1["ID"] = 90001; bad1.pop("PAY_3", None)
    bad2 = dict(records[1]); bad2["ID"] = 90002; bad2["LIMIT_BAL"] = 3000
    records = [bad1, bad2] + records
    return records


def scripted_reviewer(result):
    p = result.get("p") or 0.0
    if p >= 0.55:
        return "人工拒绝"
    return "人工通过"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    agent = CreditAgent(logger=EventLogger(os.path.join(OUT_DIR, "events.jsonl")))
    records = make_records()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print("PS D:\\credit_guard> python -m creditguard.cli demo --n 6 --interactive")
        print("CreditGuard v1.0 | 模型: models/logreg_v1.json")
        print("技能: credit-data-audit v1.0.0, review-policy v1.0.0, risk-reason-codes v1.0.0")
        print("")
        payload = agent.run_batch(records, OUT_DIR, interactive=True, reviewer=scripted_reviewer)
        s = payload["summary"]
        print("完成 %d 条：评分 %d，退回补件 %d，平均耗时 %.1f ms" % (
            s["n"], s["scored"], s["rejected_by_audit"], s["mean_latency_ms"]))
        print("动作分布:", s["by_action"])
        print("结果目录:", OUT_DIR)

    text = buf.getvalue()
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
