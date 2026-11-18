# -*- coding: utf-8 -*-
"""模型评估与阈值工具：分类指标、ROC/PR 数据、容量约束下的阈值选择。"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def binary_metrics(y_true: Sequence[int], y_prob: Sequence[float],
                   threshold: float = 0.5) -> Dict[str, float]:
    """给定阈值输出一组业务可读的指标。"""
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def ranking_metrics(y_true: Sequence[int], y_prob: Sequence[float]) -> Dict[str, float]:
    """与阈值无关的排序质量：AUC、PR-AUC、Brier。"""
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)
    return {
        "auc": float(roc_auc_score(y_true, y_prob)),
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "positive_rate": float(y_true.mean()),
    }


def roc_points(y_true: Sequence[int], y_prob: Sequence[float]):
    fpr, tpr, thr = roc_curve(np.asarray(y_true), np.asarray(y_prob))
    return {"fpr": fpr.tolist(), "tpr": tpr.tolist(), "thresholds": thr.tolist()}


def pr_points(y_true: Sequence[int], y_prob: Sequence[float]):
    from sklearn.metrics import precision_recall_curve
    precision, recall, thr = precision_recall_curve(np.asarray(y_true), np.asarray(y_prob))
    return {"precision": precision.tolist(), "recall": recall.tolist(), "thresholds": thr.tolist()}


def threshold_at_capacity(y_prob: Sequence[float], capacity: float) -> float:
    """按人工复核容量确定阈值：风险分最高的 capacity 比例进入复核。

    例如 capacity=0.15 时，取分数的 85% 分位数作为"自动通过/复核"的分界，
    保证复核队列长度不超过产能，而不是拍脑袋用 0.5。
    """
    if not 0 < capacity < 1:
        raise ValueError("capacity 必须在 (0,1) 内，当前 %.3f" % capacity)
    return float(np.quantile(np.asarray(y_prob, dtype=float), 1.0 - capacity))


def threshold_at_capacity_two_tier(y_prob: Sequence[float], review_capacity: float,
                                   decline_share: float = 1.0 / 3.0) -> Dict[str, float]:
    """两级阈值：复核线 + 建议拒绝线（建议拒绝仅占复核队列的一部分）。

    示例：review_capacity=0.15, decline_share=1/3
      → 复核线 = 85% 分位，建议拒绝线 = 95% 分位。
    """
    review_thr = threshold_at_capacity(y_prob, review_capacity)
    decline_thr = threshold_at_capacity(y_prob, review_capacity * decline_share)
    return {"review_threshold": review_thr, "decline_threshold": decline_thr}


def capacity_sweep(y_true: Sequence[int], y_prob: Sequence[float],
                   capacities: Optional[List[float]] = None) -> List[Dict[str, float]]:
    """扫描复核容量，计算"自动通过人群中的违约率"和"被复核到的违约人数占比"。"""
    capacities = capacities or [0.05, 0.10, 0.15, 0.20, 0.30, 0.50]
    y_true = np.asarray(y_true, dtype=int)
    y_prob = np.asarray(y_prob, dtype=float)
    out = []
    for cap in capacities:
        thr = threshold_at_capacity(y_prob, cap)
        review = y_prob >= thr
        auto = ~review
        out.append({
            "capacity": cap,
            "threshold": thr,
            "auto_approve_share": float(auto.mean()),
            "auto_approve_default_rate": float(y_true[auto].mean()) if auto.any() else 0.0,
            "caught_default_share": float(y_true[review].sum() / max(y_true.sum(), 1)),
            "review_default_rate": float(y_true[review].mean()) if review.any() else 0.0,
        })
    return out
