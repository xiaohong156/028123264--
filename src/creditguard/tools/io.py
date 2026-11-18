# -*- coding: utf-8 -*-
"""输入输出工具：读取申请批次、把结果导出为 JSONL / Markdown / CSV。

Agent 只依赖这里定义的函数读写文件，方便替换成数据库或接口。
"""
from __future__ import annotations

import csv
import json
import os
from typing import Dict, Iterable, List

import pandas as pd

from .. import schema


def load_records(path: str) -> List[Dict]:
    """读取 CSV 或 JSON 申请批次，统一成记录字典列表。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".json", ".jsonl"):
        if ext == ".jsonl":
            with open(path, "r", encoding="utf-8") as f:
                return [json.loads(line) for line in f if line.strip()]
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["records"] if isinstance(data, dict) else data

    df = pd.read_csv(path)
    df.columns = schema.normalize_columns(list(df.columns))
    if schema.TARGET in df.columns:
        df = df.drop(columns=[schema.TARGET])  # 推理时不接受标签，避免标签泄漏
    if schema.TARGET_RAW in df.columns:
        df = df.drop(columns=[schema.TARGET_RAW])
    return df.to_dict(orient="records")


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def write_jsonl(path: str, rows: Iterable[Dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_csv(path: str, rows: List[Dict], columns: List[str]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def write_workbook(path: str, rows: List[Dict]) -> None:
    """把复核清单写成 Excel：冻结表头、风险等级着色、长文本自动换行。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "复核清单"
    headers = ["申请号", "违约概率", "风险等级", "建议动作", "复核优先级",
               "主要风险因素", "数据标记", "人工结论"]
    ws.append(headers)
    fills = {"A": PatternFill("solid", fgColor="E2EFDA"),
             "B": PatternFill("solid", fgColor="FFF2CC"),
             "C": PatternFill("solid", fgColor="FCE4D6")}
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for row in rows:
        p = row.get("p")
        ws.append([
            row.get("app_id"),
            None if p is None else round(float(p), 4),
            row.get("band"), row.get("action"), row.get("priority"),
            "；".join(row.get("risk_texts", [])), "；".join(row.get("flags", [])),
            row.get("human_decision", ""),
        ])
        cell = ws.cell(row=ws.max_row, column=3)
        if row.get("band") in fills:
            cell.fill = fills[row["band"]]
        prob_cell = ws.cell(row=ws.max_row, column=2)
        if p is not None:
            prob_cell.number_format = "0.0%"

    widths = [10, 10, 10, 22, 11, 62, 38, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DCE6F1")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(headers)):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column >= 6)
            cell.border = border
    ws.freeze_panes = "A2"

    # 汇总页用公式，便于复核员改数据后自动重算
    summary = wb.create_sheet("汇总")
    summary["A1"] = "指标"
    summary["B1"] = "数值"
    summary["A2"] = "申请总数"
    summary["B2"] = "=COUNTA(复核清单!A2:A%d)" % (len(rows) + 1)
    summary["A3"] = "自动通过数"
    summary["B3"] = '=COUNTIF(复核清单!D2:D%d,"自动通过")' % (len(rows) + 1)
    summary["A4"] = "人工复核数"
    summary["B4"] = '=COUNTIF(复核清单!D2:D%d,"人工复核")' % (len(rows) + 1)
    summary["A5"] = "建议拒绝数"
    summary["B5"] = '=COUNTIF(复核清单!D2:D%d,"建议拒绝并人工确认")' % (len(rows) + 1)
    summary["A6"] = "高风险占比"
    summary["B6"] = "=IF(B2=0,0,B5/B2)"
    summary["B6"].number_format = "0.0%"
    for row in summary.iter_rows(min_row=1, max_row=6, min_col=1, max_col=2):
        for cell in row:
            cell.alignment = Alignment(horizontal="left", vertical="center")
    summary["B2"].font = Font(bold=True)
    summary.column_dimensions["A"].width = 16
    summary.column_dimensions["B"].width = 12
    wb.save(path)
