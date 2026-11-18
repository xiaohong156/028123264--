# -*- coding: utf-8 -*-
"""评估脚本：基线与 Agent 策略对比、容量扫描、数据审计消融。

输出
----
outputs/eval/metrics.json     全部指标（报告表格的数据源）
outputs/eval/capacity_sweep.csv
outputs/eval/policy_compare.csv

运行：
    python scripts/evaluate.py --n 4500
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "src")))

from creditguard import schema  # noqa: E402
from creditguard.ml import data as D  # noqa: E402
from creditguard.ml import metrics as M  # noqa: E402
from creditguard.ml.model import LinearScorecard  # noqa: E402

OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "outputs", "eval"))
MODEL_PATH = os.path.normpath(os.path.join(HERE, "..", "models", "logreg_v1.json"))


def load_test_raw(n: int, seed: int = 42):
    """按训练时完全相同的划分取测试集原始记录（含标签，仅用于评估）。"""
    raw = D.load_raw()  # 列名已归一，标签列名为 default
    _train, _val, test_df = D.split(raw, seed=seed)
    if n and n < len(test_df):
        test_df = test_df.sample(n=n, random_state=seed)
    return test_df.reset_index(drop=True)


def policy_metrics(p: np.ndarray, y: np.ndarray, review_thr: float, decline_thr: float) -> dict:
    """把概率映射成动作：自动通过 / 人工复核 / 建议拒绝，并统计业务指标。"""
    auto = p < review_thr
    review = (p >= review_thr) & (p < decline_thr)
    decline = p >= decline_thr
    return _policy_from_masks(y, auto, review, decline)


def _policy_from_masks(y: np.ndarray, auto: np.ndarray, review: np.ndarray,
                       decline: np.ndarray) -> dict:
    n = len(y)
    caught = review | decline
    return {
        "n": int(n),
        "auto_approve_share": float(auto.mean()),
        "review_share": float(review.mean()),
        "decline_share": float(decline.mean()),
        "auto_approve_default_rate": float(y[auto].mean()) if auto.any() else 0.0,
        "defaulters_auto_approved_share": float(y[auto].sum() / max(y.sum(), 1)),
        "defaulters_in_review_or_decline_share": float(y[caught].sum() / max(y.sum(), 1)),
        "good_customers_declined_share": float((decline & (y == 0)).sum() / max((y == 0).sum(), 1)),
        "review_default_rate": float(y[review | decline].mean()) if (review | decline).any() else 0.0,
    }


def evaluate(n: int = 4500):
    card = LinearScorecard.load(MODEL_PATH)
    test = load_test_raw(n)
    X = D.build_features(D.clean(test))
    Xv = X[card.features].values.astype(float)
    y = test[schema.TARGET].astype(int).values
    p = card.predict_proba(Xv)

    review_thr = card.thresholds["review_threshold"]
    decline_thr = card.thresholds["decline_threshold"]

    ranking = M.ranking_metrics(y, p)
    at_capacity = M.binary_metrics(y, p, threshold=review_thr)
    at_half = M.binary_metrics(y, p, threshold=0.5)

    # 1) 容量扫描
    sweep = M.capacity_sweep(y, p)

    # 2) 策略对比
    policies = {}
    policies["P0_全部通过"] = {
        "n": int(len(y)), "auto_approve_share": 1.0, "review_share": 0.0,
        "decline_share": 0.0, "auto_approve_default_rate": float(y.mean()),
        "defaulters_auto_approved_share": 1.0, "defaulters_in_review_or_decline_share": 0.0,
        "good_customers_declined_share": 0.0, "review_default_rate": 0.0,
    }
    policies["P1_模型0.5阈值自动决策"] = policy_metrics(p, y, 0.5, 0.5)
    # P2：模型 0.5 阈值 + 0.45~0.55 边界区间转人工，0.55 以上仍自动拒绝
    p2_auto = p < 0.45
    p2_review = (p >= 0.45) & (p < 0.55)
    p2_decline = p >= 0.55
    policies["P2_模型0.5+边界复核"] = _policy_from_masks(y, p2_auto, p2_review, p2_decline)
    policies["P3_Agent容量15%分级"] = policy_metrics(p, y, review_thr, decline_thr)

    # 3) 数据审计消融：注入 5% 脏数据，比较"拦截"与"静默打分"
    rng = np.random.RandomState(0)
    bad_idx = rng.choice(len(test), size=max(20, int(0.05 * len(test))), replace=False)
    records = test.to_dict(orient="records")
    corrupt_types = ["missing_age", "bad_limit", "unknown_edu", "bad_pay"]
    corrupted = []
    for i, idx in enumerate(bad_idx):
        rec = dict(records[idx])
        kind = corrupt_types[i % len(corrupt_types)]
        if kind == "missing_age":
            rec.pop("AGE", None)
        elif kind == "bad_limit":
            rec["LIMIT_BAL"] = 3000          # 低于下限
        elif kind == "unknown_edu":
            rec["EDUCATION"] = 9             # 未定义编码
        else:
            rec["PAY_0"] = 99                # 越界
        rec["_corrupt"] = kind
        corrupted.append(rec)

    from creditguard.skills.registry import SkillRegistry
    registry = SkillRegistry().discover()
    audit_skill = registry.get("credit-data-audit")
    audit = audit_skill.apply({"records": corrupted})
    blocked = sum(1 for r in audit["records"] if r["status"] == "error")
    warned = sum(1 for r in audit["records"] if r["status"] == "warn")

    # 不启用审计时：直接构造特征并打分，统计"被静默接受"的比例
    silent = 0
    for rec in corrupted:
        try:
            feats = D.record_to_features(rec)
            x = np.array([[feats[f] for f in card.features]], dtype=float)
            x = np.where(np.isnan(x), card.mean, x)
            card.predict_proba(x)
            silent += 1
        except Exception:
            pass

    # 4) 真实 Agent 端到端耗时（取 300 条）
    from creditguard.agent import CreditAgent
    agent = CreditAgent(model_path=MODEL_PATH)
    sample_n = min(300, len(test))
    t0 = time.time()
    ok = 0
    for rec in records[:sample_n]:
        res = agent.process(rec)
        if res["status"] == "done":
            ok += 1
    elapsed = time.time() - t0

    result = {
        "dataset": {"n_test": int(len(y)), "positive_rate": float(y.mean()),
                    "data_sha256": D.sha256_of(D.RAW_CSV)},
        "model": {"version": card.version, "auc": ranking["auc"],
                  "pr_auc": ranking["pr_auc"], "brier": ranking["brier"]},
        "thresholds": {"review": review_thr, "decline": decline_thr, "capacity": 0.15},
        "at_capacity": at_capacity,
        "at_0.5": at_half,
        "policies": policies,
        "capacity_sweep": sweep,
        "audit_ablation": {
            "n_corrupted": len(corrupted),
            "blocked": blocked,
            "warned": warned,
            "silently_scored": silent,
            "block_rate": blocked / len(corrupted),
            "silent_accept_rate_without_audit": silent / len(corrupted),
        },
        "agent_runtime": {
            "n": sample_n, "completed": ok,
            "mean_ms": round(elapsed / sample_n * 1000, 2),
            "records_per_second": round(sample_n / elapsed, 1),
        },
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    pd.DataFrame(sweep).to_csv(os.path.join(OUT_DIR, "capacity_sweep.csv"), index=False)
    pd.DataFrame([{"policy": k, **v} for k, v in policies.items()]).to_csv(
        os.path.join(OUT_DIR, "policy_compare.csv"), index=False)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=4500)
    args = ap.parse_args()
    r = evaluate(args.n)
    print(json.dumps({
        "auc": r["model"]["auc"], "pr_auc": r["model"]["pr_auc"],
        "thresholds": r["thresholds"],
        "policies": {k: {"auto": round(v["auto_approve_share"], 3),
                         "auto_def": round(v["auto_approve_default_rate"], 4),
                         "caught": round(v["defaulters_in_review_or_decline_share"], 3)}
                     for k, v in r["policies"].items()},
        "audit": r["audit_ablation"],
        "runtime": r["agent_runtime"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
