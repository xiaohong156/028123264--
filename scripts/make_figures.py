# -*- coding: utf-8 -*-
"""生成报告所需的全部图表（中文标注，300 dpi）。

运行：
    python scripts/make_figures.py
输出：
    outputs/figures/*.png
"""
from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from creditguard import schema  # noqa: E402
from creditguard.ml import data as D  # noqa: E402
from creditguard.ml import metrics as M  # noqa: E402
from creditguard.ml.model import LinearScorecard  # noqa: E402

FIG_DIR = os.path.join(ROOT, "outputs", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

for font_path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
    if os.path.exists(font_path):
        font_manager.fontManager.addfont(font_path)
plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 300

COLORS = {"main": "#2E5E8C", "accent": "#C0504D", "green": "#4F8A5B", "gray": "#7F7F7F"}


def load_all():
    raw = D.load_raw()
    clean = D.clean(raw)
    feats = D.build_features(clean)
    card = LinearScorecard.load(os.path.join(ROOT, "models", "logreg_v1.json"))
    with open(os.path.join(ROOT, "outputs", "eval", "metrics.json"), encoding="utf-8") as f:
        metrics = json.load(f)
    return raw, clean, feats, card, metrics


def fig_class_overview(clean, fig_dir):
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    y = clean[schema.TARGET]
    counts = y.value_counts().sort_index()
    axes[0].bar(["未违约", "违约"], counts.values, color=[COLORS["main"], COLORS["accent"]])
    for i, v in enumerate(counts.values):
        axes[0].text(i, v + 300, "%d\n(%.1f%%)" % (v, 100.0 * v / len(y)), ha="center", fontsize=10)
    axes[0].set_title("(a) 标签分布（正类占 %.1f%%）" % (100 * y.mean()))
    axes[0].set_ylabel("客户数")
    axes[0].set_ylim(0, counts.max() * 1.18)

    rate = clean.groupby("PAY_0")[schema.TARGET].mean()
    axes[1].plot(rate.index, rate.values * 100, marker="o", color=COLORS["accent"])
    axes[1].set_xlabel("最近一期还款状态（-2 无消费，0 正常，≥1 逾期月数）")
    axes[1].set_ylabel("违约率 (%)")
    axes[1].set_title("(b) 逾期状态与违约率")
    axes[1].grid(alpha=0.3)

    for label, color in [(0, COLORS["main"]), (1, COLORS["accent"])]:
        subset = clean[clean[schema.TARGET] == label]["BILL_AMT1"] / clean[clean[schema.TARGET] == label]["LIMIT_BAL"].clip(lower=1)
        axes[2].hist(subset.clip(0, 2), bins=40, alpha=0.55, density=True,
                     label=("违约" if label else "未违约"), color=color)
    axes[2].set_title("(c) 当期额度使用率分布")
    axes[2].set_xlabel("账单/额度")
    axes[2].set_ylabel("密度")
    axes[2].legend(frameon=False)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig1_overview.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_correlation(feats, fig_dir):
    cols = ["pay_max", "delay_cnt", "delay2_cnt", "pay_trend", "util_mean",
            "util_max", "pay_ratio_mean", "bill_trend", "limit_bal", "pay_amt_mean"]
    short = {"pay_max": "最严重逾期", "delay_cnt": "逾期月数", "delay2_cnt": "严重逾期月数",
             "pay_trend": "逾期变化", "util_mean": "平均使用率", "util_max": "最高使用率",
             "pay_ratio_mean": "平均还款覆盖", "bill_trend": "账单趋势",
             "limit_bal": "授信额度", "pay_amt_mean": "平均还款额"}
    corr = feats[cols].corr()
    fig, ax = plt.subplots(figsize=(8.4, 7))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(cols)))
    ax.set_yticks(range(len(cols)))
    ax.set_xticklabels([short[c] for c in cols], rotation=30, ha="right", fontsize=9)
    ax.set_yticklabels([short[c] for c in cols], fontsize=9)
    for i in range(len(cols)):
        for j in range(len(cols)):
            ax.text(j, i, "%.2f" % corr.values[i, j], ha="center", va="center",
                    fontsize=7, color="white" if abs(corr.values[i, j]) > 0.55 else "black")
    ax.set_title("主要特征相关系数（存在明显的共线性）", pad=12)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig2_correlation.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_roc_pr(clean, card, fig_dir):
    test = D.split(D.load_raw(), seed=42)[2]
    X = D.build_features(D.clean(test))[card.features].values.astype(float)
    y = test[schema.TARGET].values.astype(int)
    p = card.predict_proba(X)
    roc = M.roc_points(y, p)
    pr = M.pr_points(y, p)

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
    axes[0].plot(roc["fpr"], roc["tpr"], color=COLORS["main"], lw=2,
                 label="逻辑回归 AUC=%.3f" % M.ranking_metrics(y, p)["auc"])
    axes[0].plot([0, 1], [0, 1], "--", color=COLORS["gray"], label="随机猜测")
    axes[0].set_xlabel("假正率 FPR")
    axes[0].set_ylabel("真正率 TPR")
    axes[0].set_title("(a) ROC 曲线")
    axes[0].legend(loc="lower right", frameon=False)
    axes[0].grid(alpha=0.3)

    axes[1].plot(pr["recall"], pr["precision"], color=COLORS["accent"], lw=2,
                 label="PR-AUC=%.3f（基线 %.3f）" % (
                     M.ranking_metrics(y, p)["pr_auc"], y.mean()))
    axes[1].axhline(y.mean(), ls="--", color=COLORS["gray"], lw=1)
    axes[1].set_xlabel("召回率 Recall")
    axes[1].set_ylabel("精确率 Precision")
    axes[1].set_title("(b) PR 曲线（正类稀少，更敏感）")
    axes[1].legend(loc="upper right", frameon=False)
    axes[1].grid(alpha=0.3)

    from sklearn.calibration import calibration_curve
    frac_pos, mean_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    axes[2].plot(mean_pred, frac_pos, "o-", color=COLORS["green"], label="模型")
    axes[2].plot([0, 1], [0, 1], "--", color=COLORS["gray"], label="完美校准")
    axes[2].set_xlabel("预测违约概率")
    axes[2].set_ylabel("实际违约频率")
    axes[2].set_title("(c) 校准曲线（Brier=%.3f）" % M.ranking_metrics(y, p)["brier"])
    axes[2].legend(frameon=False)
    axes[2].grid(alpha=0.3)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig3_roc_pr.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_capacity(metrics, fig_dir):
    sweep = pd.DataFrame(metrics["capacity_sweep"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    axes[0].plot(sweep["capacity"] * 100, sweep["auto_approve_default_rate"] * 100,
                 "o-", color=COLORS["accent"], label="自动通过人群违约率")
    axes[0].axhline(22.11, ls="--", color=COLORS["gray"], label="全部通过基线 22.1%")
    axes[0].set_xlabel("人工复核容量 (%)")
    axes[0].set_ylabel("违约率 (%)")
    axes[0].set_title("(a) 复核容量 vs 自动通过人群违约率")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.3)

    axes[1].plot(sweep["capacity"] * 100, sweep["caught_default_share"] * 100,
                 "s-", color=COLORS["main"], label="违约者被复核/拒绝捕获比例")
    axes[1].plot(sweep["capacity"] * 100, sweep["auto_approve_share"] * 100,
                 "^-", color=COLORS["green"], label="自动通过比例")
    axes[1].set_xlabel("人工复核容量 (%)")
    axes[1].set_ylabel("比例 (%)")
    axes[1].set_title("(b) 复核容量 vs 捕获率与自动化率")
    axes[1].legend(frameon=False)
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig4_capacity.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_policy(metrics, fig_dir):
    policies = metrics["policies"]
    names = list(policies)
    short = ["P0 全部通过", "P1 模型0.5", "P2 0.5+边界复核", "P3 Agent 15%"]
    auto = [policies[n]["auto_approve_share"] * 100 for n in names]
    leak = [policies[n]["auto_approve_default_rate"] * 100 for n in names]
    caught = [policies[n]["defaulters_in_review_or_decline_share"] * 100 for n in names]

    x = np.arange(len(names))
    width = 0.26
    fig, ax = plt.subplots(figsize=(8.6, 3.9))
    ax.bar(x - width, auto, width, label="自动通过比例", color=COLORS["main"])
    ax.bar(x, leak, width, label="自动通过人群违约率", color=COLORS["accent"])
    ax.bar(x + width, caught, width, label="违约者捕获率", color=COLORS["green"])
    for i in range(len(names)):
        ax.text(x[i] - width, auto[i] + 1.2, "%.1f" % auto[i], ha="center", fontsize=8)
        ax.text(x[i], leak[i] + 1.2, "%.1f" % leak[i], ha="center", fontsize=8)
        ax.text(x[i] + width, caught[i] + 1.2, "%.1f" % caught[i], ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(short)
    ax.set_ylabel("百分比 (%)")
    ax.set_ylim(0, 112)
    ax.set_title("不同策略的自动化率、漏损与捕获率（测试集 4500 条）")
    ax.legend(ncol=3, frameon=False, loc="upper center")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig5_policy.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_audit(metrics, fig_dir):
    a = metrics["audit_ablation"]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    labels = ["审计拦截\n(error)", "审计告警\n(warn)", "无审计时\n静默打分"]
    values = [a["blocked"], a["warned"], a["silently_scored"]]
    colors = [COLORS["accent"], "#E8B04B", COLORS["gray"]]
    bars = ax.bar(labels, values, color=colors)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 4, "%d (%.0f%%)" % (v, 100.0 * v / a["n_corrupted"]),
                ha="center", fontsize=9)
    ax.set_ylabel("记录数")
    ax.set_title("注入 %d 条脏数据后的处理结果" % a["n_corrupted"])
    ax.set_ylim(0, max(values) * 1.2)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig6_audit.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_flow(fig_dir):
    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 40)
    ax.axis("off")

    def box(x, y, w, h, text, color="#EAF1F8", edge=COLORS["main"], fs=15):
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                              linewidth=1.2, edgecolor=edge, facecolor=color)
        ax.add_patch(rect)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.5)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12,
                                     lw=1.2, color=COLORS["gray"], shrinkA=2, shrinkB=2))

    box(1, 26, 15, 8, "申请记录\n(CSV/JSON)")
    box(20, 26, 16, 8, "① 数据审计\n(audit)")
    box(39, 26, 14, 8, "② 特征构造\n18 维")
    box(56, 26, 14, 8, "③ 评分卡\nP(违约)")
    box(73, 26, 14, 8, "④ 原因码\n(reason)")
    box(73, 10, 14, 8, "⑤ 复核策略\n(policy)")
    box(56, 10, 14, 8, "⑥ 人工复核\n(高风险必过)", color="#FCE4D6", edge=COLORS["accent"])
    box(39, 10, 14, 8, "⑦ 结论与\n导出", color="#E2EFDA", edge=COLORS["green"])
    box(20, 10, 16, 8, "退回补件\n(数据 error)", color="#F2F2F2", edge=COLORS["gray"])

    arrow(16, 30, 20, 30)
    arrow(36, 30, 39, 30)
    arrow(53, 30, 56, 30)
    arrow(70, 30, 73, 30)
    arrow(80, 26, 80, 18)
    arrow(73, 14, 70, 14)
    arrow(56, 14, 53, 14)
    ax.annotate("", xy=(28, 18), xytext=(28, 26),
                arrowprops=dict(arrowstyle="-|>", color=COLORS["gray"], lw=1.2))
    ax.text(28.6, 22, "审计失败", fontsize=12, color=COLORS["gray"])
    ax.text(78.5, 20.5, "需复核", fontsize=12, color=COLORS["gray"])
    ax.text(50, 6.5, "全部步骤写入 events.jsonl；模型缺失时降级为规则评分并标注 degraded=true",
            fontsize=11, color="#555555")
    ax.set_title("CreditGuard Agent 工作流：技能（①④⑤）与模型（③）各司其职", fontsize=16)
    fig.tight_layout()
    path = os.path.join(fig_dir, "fig7_flow.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_console(fig_dir):
    log_path = os.path.join(ROOT, "outputs", "runs", "demo_console.txt")
    if not os.path.exists(log_path):
        print("[skip] 缺少演示日志:", log_path)
        return None
    with open(log_path, encoding="utf-8") as f:
        text = f.read().rstrip("\n")
    lines = text.splitlines()[-34:]
    height = max(2.6, 0.136 * len(lines) + 0.28)
    fig = plt.figure(figsize=(9.6, height), facecolor="#1E1E1E")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#1E1E1E")
    ax.axis("off")
    ax.text(0.015, 0.985, "\n".join(lines), va="top", ha="left", family="SimSun",
            fontsize=7.2, color="#D4D4D4", linespacing=1.45)
    path = os.path.join(fig_dir, "fig8_console.png")
    fig.savefig(path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def main():
    raw, clean, feats, card, metrics = load_all()
    paths = [
        fig_class_overview(clean, FIG_DIR),
        fig_correlation(feats, FIG_DIR),
        fig_roc_pr(clean, card, FIG_DIR),
        fig_capacity(metrics, FIG_DIR),
        fig_policy(metrics, FIG_DIR),
        fig_audit(metrics, FIG_DIR),
        fig_flow(FIG_DIR),
        fig_console(FIG_DIR),
    ]
    for p in paths:
        if p:
            print("[ok]", p)


if __name__ == "__main__":
    main()
