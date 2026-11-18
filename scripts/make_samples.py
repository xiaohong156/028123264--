# -*- coding: utf-8 -*-
"""生成测试样例：正常申请 30 条 + 含脏数据的申请 10 条。

正常样例来自 UCI 测试划分之外的真实记录，只保留推理所需字段（不含标签），
可直接用 CLI 的 batch 子命令运行。
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard import schema  # noqa: E402
from creditguard.ml import data as D  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "samples")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = D.load_raw().drop(columns=[schema.TARGET])
    rng = np.random.RandomState(2026)
    idx = rng.choice(len(df), size=30, replace=False)
    sample = df.iloc[idx].reset_index(drop=True)
    sample.to_csv(os.path.join(OUT_DIR, "sample_applications.csv"), index=False, encoding="utf-8-sig")

    bad = sample.head(10).copy()
    bad.loc[0, "AGE"] = 15
    bad.loc[1, "LIMIT_BAL"] = 3000
    bad.loc[2, "EDUCATION"] = 9
    bad.loc[3, "PAY_0"] = 99
    bad.loc[4, ["PAY_AMT1", "PAY_AMT2"]] = -100
    bad.loc[5, "BILL_AMT3"] = 9_999_999
    bad.loc[6, "MARRIAGE"] = 7
    bad.loc[7, "SEX"] = 3
    bad = bad.drop(columns=["PAY_3"], errors="ignore")  # 整列缺失，整批都会被标记
    bad.to_csv(os.path.join(OUT_DIR, "sample_with_errors.csv"), index=False, encoding="utf-8-sig")
    print("[ok]", os.path.join(OUT_DIR, "sample_applications.csv"))
    print("[ok]", os.path.join(OUT_DIR, "sample_with_errors.csv"))


if __name__ == "__main__":
    main()
