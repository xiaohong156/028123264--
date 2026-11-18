# -*- coding: utf-8 -*-
"""训练评分卡并保存模型与实验记录。

用法：
    python scripts/train.py
    python scripts/train.py --capacity 0.15 --out ../models/logreg_v1.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "src")))

from creditguard.ml import model as M  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity", type=float, default=0.15, help="人工复核容量占比")
    ap.add_argument("--decline-share", type=float, default=1.0 / 3.0,
                    help="复核队列中'建议拒绝'的比例")
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "models", "logreg_v1.json")))
    args = ap.parse_args()

    card, params = M.train(capacity=args.capacity, decline_share=args.decline_share)
    M.save_model(params, args.out)
    print("[ok] 模型已保存:", args.out)

    summary = {
        "version": params["version"],
        "thresholds": params["thresholds"],
        "val": params["metrics"]["val"],
        "test": params["metrics"]["test"],
        "coef": params["coef"],
    }
    with open(os.path.join(os.path.dirname(args.out), "model_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
