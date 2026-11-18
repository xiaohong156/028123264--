# -*- coding: utf-8 -*-
"""数据加载、清洗与特征工程。

设计要点
--------
* 训练与推理共用 :func:`build_features` / :func:`record_to_features`，
  避免"训练时一套、上线时另一套"的特征漂移。
* 所有派生特征都能用一句话解释（如额度使用率 = 账单/额度），
  保证后续原因码对业务人员可读。
* 清洗只做有依据的映射：EDUCATION/MARRIAGE 的未文档化编码并入"其他"，
  逾期状态保留原始 -2~8 的序数含义。
"""
from __future__ import annotations

import hashlib
import os
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from .. import schema

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
RAW_CSV = os.path.join(PROJECT_ROOT, "data", "raw", "uci_credit_default.csv")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "data", "processed")


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_raw(path: str = RAW_CSV) -> pd.DataFrame:
    """读取原始 CSV，统一列名并把标签改成 default。"""
    df = pd.read_csv(path)
    df.columns = schema.normalize_columns(list(df.columns))
    if schema.TARGET_RAW in df.columns:
        df = df.rename(columns={schema.TARGET_RAW: schema.TARGET})
    missing = [c for c in schema.RAW_COLUMNS
               if c not in df.columns and c != schema.TARGET_RAW]
    if missing:
        raise ValueError("缺少字段: %s" % missing)
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """类型规范化与类别映射；不删除任何样本（便于和原始分布对照）。"""
    out = df.copy()
    # 单条推理时输入可能缺字段或类型错误，这里统一转数值，非法值变成 NaN，
    # 由数据审计技能负责拦截/标记，而不是在清洗阶段直接抛异常。
    out["SEX"] = pd.to_numeric(out["SEX"], errors="coerce").map(schema.SEX_MAP)
    out["EDUCATION"] = pd.to_numeric(out["EDUCATION"], errors="coerce").map(schema.EDU_MAP).fillna("其他")
    out["MARRIAGE"] = pd.to_numeric(out["MARRIAGE"], errors="coerce").map(schema.MARRIAGE_MAP).fillna("其他")
    for col in schema.PAY_COLS + schema.BILL_COLS + schema.PAY_AMT_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["AGE"] = pd.to_numeric(out["AGE"], errors="coerce")
    out["LIMIT_BAL"] = pd.to_numeric(out["LIMIT_BAL"], errors="coerce")
    if schema.TARGET in out.columns:
        out[schema.TARGET] = out[schema.TARGET].astype(int)
    return out


def _safe_div(num: pd.Series, den: pd.Series, eps: float = 1e-6) -> pd.Series:
    return num / (den.abs() + eps)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """由原始字段派生 16 个模型特征（与 schema.FEATURES 顺序一致）。"""
    pay = df[schema.PAY_COLS]
    bill = df[schema.BILL_COLS]
    pay_amt = df[schema.PAY_AMT_COLS]

    limit = df["LIMIT_BAL"].clip(lower=1)
    bill_mean = bill.mean(axis=1)
    pay_amt_mean = pay_amt.mean(axis=1)

    # 额度使用率：当期账单 / 授信额度；负数账单（溢缴款）按 0 处理
    util = _safe_div(bill["BILL_AMT1"].clip(lower=0), limit).clip(0, 2)
    util_mean = _safe_div(bill_mean.clip(lower=0), limit).clip(0, 2)

    # 还款覆盖率：当期还款 / 上期账单；>1 表示还清并可能有溢缴
    pay_ratio = _safe_div(pay_amt["PAY_AMT1"], bill["BILL_AMT2"].clip(lower=0)).clip(0, 2)
    pay_ratio_mean = _safe_div(pay_amt.sum(axis=1), bill.sum(axis=1).clip(lower=0)).clip(0, 2)

    # 账单趋势：近 6 个月账单从最早到最近的变化幅度（按额度归一）
    bill_trend = _safe_div(bill["BILL_AMT1"] - bill["BILL_AMT6"], limit).clip(-2, 2)

    feats = pd.DataFrame({
        "limit_bal": limit,
        "age": df["AGE"],
        "sex": df["SEX"].map({"男": 1, "女": 2}).fillna(0),
        "edu": df["EDUCATION"].map({"研究生": 1, "大学": 2, "高中": 3, "其他": 4}).fillna(4),
        "marriage": df["MARRIAGE"].map({"已婚": 1, "未婚": 2, "其他": 3}).fillna(3),
        "pay_max": pay.max(axis=1),
        "delay_cnt": (pay >= 1).sum(axis=1),
        "delay_cnt": (pay >= 1).sum(axis=1),
        "delay2_cnt": (pay >= 2).sum(axis=1),
        "pay_trend": (pay["PAY_0"] - pay["PAY_6"]).astype(float),
        "bill_mean": bill_mean,
        "pay_amt_mean": pay_amt_mean,
        "zero_pay_cnt": (pay_amt == 0).sum(axis=1).astype(float),
        "util": util,
        "util_mean": util_mean,
        "util_max": _safe_div(bill.clip(lower=0).max(axis=1), limit).clip(0, 2),
        "pay_ratio": pay_ratio,
        "pay_ratio_mean": pay_ratio_mean,
        "bill_trend": bill_trend,
    })
    return feats[schema.FEATURES].astype(float)


def record_to_features(record: Dict[str, object]) -> Dict[str, float]:
    """单条申请记录 → 特征字典（推理入口，与训练特征保持一致）。"""
    row = {k: record.get(k, np.nan) for k in schema.RAW_COLUMNS if k != schema.TARGET_RAW}
    df = pd.DataFrame([row])
    df.columns = schema.normalize_columns(list(df.columns))
    df = clean(df)
    feats = build_features(df)
    return {k: float(feats.iloc[0][k]) for k in schema.FEATURES}


def split(df: pd.DataFrame, seed: int = 42,
          ratios: Tuple[float, float, float] = (0.70, 0.15, 0.15)
          ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """分层抽样划分训练/验证/测试集；验证集用于选模型与定阈值，测试集只评一次。"""
    from sklearn.model_selection import train_test_split

    train_ratio, val_ratio, test_ratio = ratios
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-9

    train_df, rest = train_test_split(
        df, test_size=(val_ratio + test_ratio), stratify=df[schema.TARGET], random_state=seed)
    rel_test = test_ratio / (val_ratio + test_ratio)
    val_df, test_df = train_test_split(
        rest, test_size=rel_test, stratify=rest[schema.TARGET], random_state=seed)
    return train_df.reset_index(drop=True), val_df.reset_index(drop=True), test_df.reset_index(drop=True)


def prepare(seed: int = 42, save: bool = True):
    """完整流程：读取 → 清洗 → 特征 → 划分，可选落盘。"""
    raw = load_raw()
    data_hash = sha256_of(RAW_CSV)
    df = clean(raw)
    X = build_features(df)
    y = df[schema.TARGET].astype(int)
    idx_train, idx_val, idx_test = None, None, None

    train_df, val_df, test_df = split(df.assign(**{schema.TARGET: y}), seed=seed)
    X_train = build_features(train_df)
    X_val = build_features(val_df)
    X_test = build_features(test_df)
    y_train = train_df[schema.TARGET].astype(int)
    y_val = val_df[schema.TARGET].astype(int)
    y_test = test_df[schema.TARGET].astype(int)

    if save:
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        for name, X_part, y_part in [
            ("train", X_train, y_train), ("val", X_val, y_val), ("test", X_test, y_test)]:
            out = X_part.copy()
            out[schema.TARGET] = y_part.values
            out.to_csv(os.path.join(PROCESSED_DIR, "%s.csv" % name), index=False)

    meta = {
        "n_total": int(len(df)),
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_test": int(len(X_test)),
        "positive_rate": float(y.mean()),
        "data_sha256": data_hash,
        "split_seed": seed,
    }
    return (X_train, y_train), (X_val, y_val), (X_test, y_test), meta


if __name__ == "__main__":
    (Xtr, ytr), (Xva, yva), (Xte, yte), meta = prepare()
    print(meta)
    print(Xtr.head(3).to_string())
