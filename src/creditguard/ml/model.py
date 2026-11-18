# -*- coding: utf-8 -*-
"""逻辑回归评分卡：训练、选择、校准、持久化与推理。

为什么用逻辑回归
----------------
* 课程核心方法，系数即"对数几率贡献"，可逐条拆解成原因码，满足
  "Agent 解释风险依据"的要求；
* 在高维稀疏、样本量 2 万级别的表格数据上，正则化逻辑回归的排序能力
  与复杂模型差距不大，但可解释性和可审计性明显更好；
* 输出概率经过校准后，才能直接用于"按复核容量选阈值"。

训练流程
--------
1. 在训练集上拟合若干 (C, class_weight) 组合；
2. 用验证集 PR-AUC 选模型（违约是少数类，PR-AUC 比准确率更敏感）；
3. 若使用 balanced 权重（概率会被抬高），在验证集上做 Platt 校准；
4. 按复核容量在验证集上确定两级阈值；
5. 全部参数写入 JSON（均值/标准差/系数/截距/校准参数/阈值/指标），
   推理只依赖 JSON，不依赖 pickle，便于审计与跨环境复现。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression

from .. import schema
from . import metrics as M


class LinearScorecard:
    """从 JSON 恢复的线性评分卡（纯 numpy 推理，便于审计）。"""

    def __init__(self, params: Dict):
        self.params = params
        self.features: List[str] = params["features"]
        self.mean = np.array([params["scaler"]["mean"][f] for f in self.features])
        self.scale = np.array([params["scaler"]["scale"][f] for f in self.features])
        self.coef = np.array([params["coef"][f] for f in self.features])
        self.intercept = float(params["intercept"])
        self.calib = params.get("calibration")
        self.thresholds = params["thresholds"]
        self.version = params.get("version", "unknown")

    # ---------- 推理 ----------
    def logit(self, X: np.ndarray) -> np.ndarray:
        z = (np.asarray(X, dtype=float) - self.mean) / self.scale
        return self.intercept + z @ self.coef

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        raw = 1.0 / (1.0 + np.exp(-np.clip(self.logit(X), -30, 30)))
        if self.calib:
            a, b = float(self.calib["a"]), float(self.calib["b"])
            logits = np.log(np.clip(raw, 1e-9, 1 - 1e-9) / np.clip(1 - raw, 1e-9, 1))
            raw = 1.0 / (1.0 + np.exp(-np.clip(a * logits + b, -30, 30)))
        return raw

    def contributions(self, x: np.ndarray) -> Dict[str, float]:
        """单样本的对数几率贡献（标准化空间），满足 Σ贡献 + 截距 = logit。"""
        z = (np.asarray(x, dtype=float) - self.mean) / self.scale
        return {f: float(c) for f, c in zip(self.features, z * self.coef)}

    def contributions_frame(self, X: np.ndarray) -> np.ndarray:
        z = (np.asarray(X, dtype=float) - self.mean) / self.scale
        return z * self.coef[None, :]

    # ---------- 持久化 ----------
    @classmethod
    def load(cls, path: str) -> "LinearScorecard":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    @staticmethod
    def save(params: Dict, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False, indent=2)


def _fit_lr(X: np.ndarray, y: np.ndarray, C: float, class_weight: Optional[str]):
    """标准化 + L2 逻辑回归。标准化参数随模型一起保存，推理时复用。"""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    clf = Pipeline([
        ("standardscaler", StandardScaler()),
        ("logisticregression", LogisticRegression(
            C=C, penalty="l2", solver="lbfgs", max_iter=3000,
            class_weight=class_weight, random_state=42)),
    ])
    clf.fit(X, y)
    return clf


def _platt(X_val: np.ndarray, y_val: np.ndarray, raw_prob: np.ndarray) -> Dict[str, float]:
    """Platt 校准：在验证集上把原始分数映射成更接近真实违约率的概率。"""
    logits = np.log(np.clip(raw_prob, 1e-6, 1 - 1e-6) / np.clip(1 - raw_prob, 1e-6, 1))
    cal = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    cal.fit(logits.reshape(-1, 1), y_val)
    return {"a": float(cal.coef_[0][0]), "b": float(cal.intercept_[0])}


def train(seed: int = 42, capacity: float = 0.15, decline_share: float = 1.0 / 3.0,
          candidates: Optional[List[Tuple[float, Optional[str]]]] = None,
          verbose: bool = True) -> Tuple[LinearScorecard, Dict]:
    """训练并选择模型，返回评分卡与实验记录。"""
    from . import data as D

    (Xtr, ytr), (Xva, yva), (Xte, yte), meta = D.prepare(seed=seed)
    Xtr = Xtr.values.astype(float)
    Xva = Xva.values.astype(float)
    Xte = Xte.values.astype(float)
    ytr = ytr.values.astype(int)
    yva = yva.values.astype(int)
    yte = yte.values.astype(int)

    candidates = candidates or [
        (0.03, None), (0.1, None), (0.3, None), (1.0, None),
        (0.1, "balanced"), (0.3, "balanced"),
    ]
    records = []
    best = None
    for C, cw in candidates:
        clf = _fit_lr(Xtr, ytr, C, cw)
        pva = clf.predict_proba(Xva)[:, 1]
        m = M.ranking_metrics(yva, pva)
        records.append({"C": C, "class_weight": cw or "none", **m})
        if verbose:
            print("[cand] C=%-5.2f cw=%-8s val AUC=%.4f PR-AUC=%.4f Brier=%.4f"
                  % (C, cw, m["auc"], m["pr_auc"], m["brier"]))
        # 选择准则：PR-AUC 优先，AUC 次之
        key = (round(m["pr_auc"], 6), round(m["auc"], 6))
        if best is None or key > best[0]:
            best = (key, clf, C, cw, m)

    _, clf, C, cw, m_val = best
    calib = None
    pva = clf.predict_proba(Xva)[:, 1]
    if cw == "balanced":
        calib = _platt(Xva, yva, pva)
        cal = 1.0 / (1.0 + np.exp(-np.clip(
            calib["a"] * np.log(np.clip(pva, 1e-9, 1 - 1e-9) / np.clip(1 - pva, 1e-9, 1))
            + calib["b"], -30, 30)))
        pva = cal

    # 在验证集上按容量确定阈值
    thr = M.threshold_at_capacity_two_tier(pva, capacity, decline_share)

    # 测试集只评一次
    pte_raw = clf.predict_proba(Xte)[:, 1]
    pte = pte_raw
    if calib:
        pte = 1.0 / (1.0 + np.exp(-np.clip(
            calib["a"] * np.log(np.clip(pte_raw, 1e-9, 1 - 1e-9) / np.clip(1 - pte_raw, 1e-9, 1))
            + calib["b"], -30, 30)))
    test_metrics = {
        **M.ranking_metrics(yte, pte),
        **M.binary_metrics(yte, pte, threshold=thr["review_threshold"]),
    }
    # 参考：传统 0.5 阈值
    test_metrics["at_0.5"] = M.binary_metrics(yte, pte, threshold=0.5)

    params = {
        "version": "creditguard-logreg-%s" % datetime.now(timezone.utc).strftime("%Y%m%d"),
        "features": list(schema.FEATURES),
        "scaler": {
            "mean": dict(zip(schema.FEATURES, clf.named_steps["standardscaler"].mean_.tolist())),
            "scale": dict(zip(schema.FEATURES, clf.named_steps["standardscaler"].scale_.tolist())),
        },
        "coef": dict(zip(schema.FEATURES, clf.named_steps["logisticregression"].coef_[0].tolist())),
        "intercept": float(clf.named_steps["logisticregression"].intercept_[0]),
        "calibration": calib,
        "thresholds": {
            "review_capacity": capacity,
            "decline_share": decline_share,
            **thr,
        },
        "metrics": {
            "val": m_val,
            "test": test_metrics,
            "candidates": records,
            "dataset": meta,
        },
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "library": {"sklearn": __import__("sklearn").__version__},
    }
    card = LinearScorecard(params)

    if verbose:
        print("[best] C=%.3f cw=%s  test AUC=%.4f PR-AUC=%.4f"
              % (C, cw, test_metrics["auc"], test_metrics["pr_auc"]))
    return card, params


def save_model(params: Dict, path: str) -> None:
    LinearScorecard.save(params, path)


def load_model(path: str) -> LinearScorecard:
    return LinearScorecard.load(path)
