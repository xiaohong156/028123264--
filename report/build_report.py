# -*- coding: utf-8 -*-
"""生成期末报告 DOCX（中文，含封面、图表、三线表、页码、附录）。

用法：
    python report/build_report.py
输出：
    report/CreditGuard_期末报告.docx
"""
from __future__ import annotations

import os
import re
import sys

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FIG = os.path.join(ROOT, "outputs", "figures")
DOCX_PATH = os.path.join(HERE, "CreditGuard_期末报告.docx")

BODY_CHARS = []  # 统计正文汉字数


# ----------------------------------------------------------------------
# 基础排版
# ----------------------------------------------------------------------
def set_run_font(run, name="宋体", size=12, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def init_document():
    doc = Document()
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.4)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(3.0)

    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    style.paragraph_format.line_spacing = 1.5
    style.paragraph_format.space_after = Pt(0)

    # 页脚页码
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar"); fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = " PAGE "
    fld_end = OxmlElement("w:fldChar"); fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin); run._r.append(instr); run._r.append(fld_end)
    set_run_font(run, size=9)
    return doc


def add_heading(doc, text, level=1):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(6 if level == 1 else 4)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    set_run_font(run, name="黑体", size=16 if level == 1 else 14, bold=True)
    if level == 1:
        BODY_CHARS.append(text)
    return p


def add_body(doc, text, indent=True):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.space_after = Pt(3)
    if indent:
        p.paragraph_format.first_line_indent = Pt(24)  # 首行缩进两字符
    run = p.add_run(text)
    set_run_font(run, size=12)
    BODY_CHARS.append(text)
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    set_run_font(run, size=10.5)
    return p


def add_figure(doc, filename, caption, width_cm=14.5):
    path = os.path.join(FIG, filename)
    if not os.path.exists(path):
        print("[warn] 缺少图片:", path)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(path, width=Cm(width_cm))
    add_caption(doc, caption)


def _set_cell_border(cell, **kwargs):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right"):
        if edge in kwargs:
            element = borders.find(qn("w:%s" % edge))
            if element is None:
                element = OxmlElement("w:%s" % edge)
                borders.append(element)
            for key, value in kwargs[edge].items():
                element.set(qn("w:%s" % key), str(value))


def add_table(doc, headers, rows, caption, widths=None, font_size=10.5, align_center=True):
    add_caption(doc, caption)
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.allow_autofit = True

    def fill(cell, text, bold=False):
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if align_center else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(str(text))
        set_run_font(run, size=font_size, bold=bold)

    for j, h in enumerate(headers):
        fill(table.rows[0].cells[j], h, bold=True)
    for i, row in enumerate(rows, start=1):
        for j, value in enumerate(row):
            fill(table.rows[i].cells[j], value)

    # 三线表：上下粗线，表头下细线，其余无边框
    thick = {"sz": 12, "val": "single", "color": "000000"}
    thin = {"sz": 6, "val": "single", "color": "000000"}
    none = {"sz": 0, "val": "nil"}
    for j in range(len(headers)):
        _set_cell_border(table.rows[0].cells[j], top=thick, bottom=thin, left=none, right=none)
        _set_cell_border(table.rows[-1].cells[j], bottom=thick, left=none, right=none, top=none)
        for i in range(1, len(rows)):
            _set_cell_border(table.rows[i].cells[j], left=none, right=none, top=none,
                             bottom={"sz": 0, "val": "nil"})
    if widths:
        for j, w in enumerate(widths):
            for row in table.rows:
                row.cells[j].width = Cm(w)

    # 避免表格跨页被切断：行内禁止分页，除最后一行外与下一行保持同页
    for i, row in enumerate(table.rows):
        tr_pr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        if i < len(table.rows) - 1:
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.keep_with_next = True
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_reference(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(24)
    p.paragraph_format.first_line_indent = Pt(-24)
    p.paragraph_format.line_spacing = 1.3
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    set_run_font(run, size=10.5)
    return p


def add_code(doc, code, caption=None):
    if caption:
        add_caption(doc, caption)
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(12)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(code.strip("\n"))
    set_run_font(run, name="Consolas", size=8.5)
    return p


# ----------------------------------------------------------------------
# 封面
# ----------------------------------------------------------------------
def build_cover(doc):
    for _ in range(2):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("《机器学习》课程期末项目报告")
    set_run_font(run, name="黑体", size=18, bold=True)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("CreditGuard：信贷初审风险复核 Agent")
    set_run_font(run, name="黑体", size=22, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("——逻辑回归评分卡、可复核原因码与人工协作流程")
    set_run_font(run, name="楷体", size=14)

    for _ in range(3):
        doc.add_paragraph()

    info = [
        ("课程名称", "机器学习"),
        ("项目名称", "CreditGuard 信贷初审风险复核 Agent"),
        ("选题模块", "信用风险或异常识别（逻辑回归 / 类别不平衡 / ROC-AUC）"),
        ("姓名", "____________"),
        ("学号", "____________"),
        ("组员及分工", "____________（独立完成时填“无”）"),
        ("提交日期", "2026 年 11 月 27 日"),
    ]
    table = doc.add_table(rows=len(info), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(info):
        left, right = table.rows[i].cells
        left.width = Cm(3.6)
        right.width = Cm(10.6)
        for cell, text, bold in ((left, k, True), (right, v, False)):
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(text)
            set_run_font(run, size=12, bold=bold)
    doc.add_page_break()


# ----------------------------------------------------------------------
# 正文
# ----------------------------------------------------------------------
def build_body(doc):
    # 摘要
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run("摘  要")
    set_run_font(run, name="黑体", size=16, bold=True)
    add_body(doc, (
        "本文面向消费金融的信贷初审场景，构建了 CreditGuard——一个把逻辑回归评分卡、"
        "三个可复用技能与人机协作流程组合起来的风险复核 Agent。系统在 3 万条公开脱敏数据上"
        "训练评分卡（测试集 AUC 0.755），按人工复核容量确定分级阈值，把“是否通过”从固定 0.5 阈值"
        "改为“自动通过 / 人工复核 / 建议拒绝”三级分流，并用线性贡献生成逐条可核对的原因码。"
        "在 4500 条测试样本上，15% 复核容量下自动通过人群违约率由 22.1% 降至 15.5%，"
        "违约者捕获率为 40.5%，好客户被拒比例由 4.85% 降至 1.83%；数据审计技能拦截 75.1% 的脏数据，"
        "所有拒贷建议均经人工确认。报告同时给出技能复用与核验过程、消融实验、失败案例与系统边界。"))
    p = doc.add_paragraph()
    run = p.add_run("关键词：")
    set_run_font(run, size=12, bold=True)
    run = p.add_run("信贷风险；逻辑回归；类别不平衡；ROC-AUC；Agent；技能复用")
    set_run_font(run, size=12)

    # 一、需求与目标
    add_heading(doc, "一、需求与目标")
    add_heading(doc, "1.1 场景与目标用户", level=2)
    add_body(doc, (
        "某消费金融公司的初审团队每天要处理数千笔小额信贷申请。初审专员需要在有限时间内决定三件事："
        "哪些申请可以直接通过，哪些需要退回补件，哪些必须转人工深审。公司给复核团队的人力上限约为"
        "申请量的 15%，超出这个比例，队列就会积压，审批时效随之恶化。目标用户就是这些初审专员，"
        "他们既不是建模工程师，也不应该被要求读懂模型公式。"))
    add_heading(doc, "1.2 现有做法的问题", level=2)
    add_body(doc, (
        "第一，评分卡只给一个概率，复核员不知道“为什么”，只能逐单翻账单和还款记录，单笔耗时长且标准不一。"
        "第二，统一用 0.5 作阈值，为了多抓违约把大量好客户一起拒掉，客户体验和业务量都受损。"
        "第三，脏数据会静默进入模型：年龄 15 岁、额度 3000 元、教育编码 9 这类记录不会报错，"
        "却会得到一个看似正常、实则无意义的分数。第四，拒贷缺少留痕，事后无法复盘是谁、依据什么做出的决定。"))
    add_heading(doc, "1.3 项目范围", level=2)
    add_body(doc, (
        "输入是单笔或批量的申请记录（CSV/JSON，23 个字段）；输出包括违约概率、最多 3 条风险因素和 2 条"
        "缓释因素、A/B/C 风险等级、建议动作、是否需要人工复核，以及可导出的复核清单（CSV/Excel）。"
        "不在范围内的是反欺诈、额度定价、合同签署与放款，这些环节需要另外的数据与合规流程。"))
    add_heading(doc, "1.4 可验证的成功标准", level=2)
    add_body(doc, (
        "S1：在 15% 复核容量下，自动通过人群的违约率不高于 16%（全部通过的基线为 22.1%）。"
        "S2：违约者中被复核或建议拒绝捕获的比例不低于 35%。"
        "S3：注入的四类脏数据 100% 被拦截或标记，不允许静默进入模型。"
        "S4：单条申请端到端耗时不超过 50 ms。"
        "S5：自动拒贷 0 例，所有拒贷建议都必须经过人工确认。"))

    add_heading(doc, "1.5 与课程内容的对应", level=2)
    add_body(doc, (
        "本项目把课程中的分类模型、类别不平衡、特征工程、ROC/AUC 与模型评估几块内容落到一个具体任务上："
        "用逻辑回归做二分类，用 PR-AUC 与 AUC 处理 22.1% 的正类比例，用分层抽样和独立测试集保证评估可信，"
        "用概率校准与容量阈值把“模型指标”翻译成“业务动作”。模型不是报告里的一个数字，而是 Agent 每一步"
        "判断的依据来源。"))

    add_heading(doc, "二、方案与系统设计")
    add_heading(doc, "2.1 总体架构", level=2)
    add_body(doc, (
        "Agent 采用显式状态机而不是“大模型自由发挥”：RECEIVED → AUDIT → FEATURE → SCORE → "
        "EXPLAIN → POLICY → REVIEW → EXPORT，任一步失败都有明确出口（图 1）。"
        "选择确定性编排的理由有三点：信贷拒贷是高影响、强监管的决策，必须逐单可复现、可审计；"
        "大模型的输出不稳定且成本高；课程要求也明确指出，不能把“调用大模型”本身当作项目成果。"
        "因此系统把自然语言限制在模板化话术上，真正的判断交给技能与模型。"))
    add_figure(doc, "fig7_flow.png", "图 1  CreditGuard 的工作流（第二行自右向左）：技能负责判断，模型负责概率，Agent 负责编排与留痕", 15.5)
    add_heading(doc, "2.2 组件关系", level=2)
    add_body(doc, (
        "技能（skills）只做判断：数据审计判断记录能不能用，原因码把贡献翻译成人话，复核策略决定这单怎么处理。"
        "工具（tools）只做读写：CSV/JSON 输入、JSONL/Markdown/Excel 输出。评分卡只回答“违约概率是多少”。"
        "Agent 负责把三者串起来，记录每一步的状态、耗时与依据。这种拆分让每个组件都能单独测试，"
        "也让技能可以被替换——例如把模板话术换成经过校验的生成式改写，而不影响评分与策略。"))
    add_heading(doc, "2.3 关键设计选择与备选方案", level=2)
    add_body(doc, (
        "阈值：备选是固定 0.5；最终按复核容量在验证集上取分位数。理由是产能是硬约束，"
        "而 0.5 会拒掉 4.85% 的好客户，这些客户本来可以自动通过。"
        "解释：备选是 SHAP 或让大模型写解释；最终用线性贡献分解。逻辑回归的对数几率本身就是各特征贡献之和，"
        "分解精确、零额外依赖、可以直接写进审计日志，也不存在“编造理由”的风险。"
        "拒贷：备选是超过阈值自动拒绝；最终选择“建议拒绝 + 人工确认”，把最终决定权留给人。"
        "模型：备选是梯度提升树；最终用逻辑回归，因为它在表格数据上排序能力接近，且系数天然可解释，"
        "符合评分卡的行业惯例。"))
    add_heading(doc, "2.4 失败与安全处理", level=2)
    add_body(doc, (
        "审计为 error 的记录直接退回补件，不进入评分；审计为 warn 的记录强制转人工，不允许走快速通道；"
        "模型文件缺失或损坏时降级为规则评分，并在结果里标记 degraded=true，而不是静默给出错误分数；"
        "单条记录异常只隔离该条，不影响整批；概率落在复核线 ±0.02 的边界情形一律转人工；"
        "所有步骤写入 events.jsonl，包含时间戳、状态、耗时和依据，可直接作为审计材料。"))
    add_heading(doc, "2.5 数据与隐私", level=2)
    add_body(doc, (
        "训练与评估使用 UCI 公开脱敏数据集（CC BY 4.0），不含真实身份信息；系统不调用任何外部服务，"
        "推理全部在本地完成；仓库不保存密钥；模型输出只用于辅助复核，不构成自动拒贷决定。"))

    # 三、机器学习方法
    add_heading(doc, "三、机器学习方法")
    add_heading(doc, "3.1 数据与划分", level=2)
    add_body(doc, (
        "数据为 UCI“Default of Credit Card Clients”（数据集 350）：30000 条客户记录、23 个特征，"
        "标签是“下个月是否违约”，正类占 22.1%。按 70%/15%/15% 分层划分训练、验证、测试集；"
        "模型选择与阈值确定只用验证集，测试集在全部配置固定后只评一次，避免信息泄漏。"))
    add_heading(doc, "3.2 特征工程", level=2)
    add_body(doc, (
        "最终使用 18 维特征：额度、年龄、性别、教育、婚姻；逾期相关的最严重状态、逾期月数、"
        "严重逾期月数、逾期变化；账单与还款相关的平均账单、平均还款、零还款月数、当期/平均/最高额度使用率、"
        "还款覆盖率、账单趋势。派生特征都能用一句话解释，例如“额度使用率 = 当期账单 / 授信额度”，"
        "这样原因码才能被业务人员读懂。图 2 显示逾期类特征之间、使用率类特征之间存在明显共线性；"
        "我们曾加入“平均逾期状态”，它与“最严重逾期状态”相关系数超过 0.9，加入后系数反号、"
        "解释变成“逾期越多风险越低”，因此将其剔除。"))
    add_figure(doc, "fig2_correlation.png", "图 2  主要特征的相关系数：逾期类与使用率类特征存在明显共线性", 12.0)
    add_heading(doc, "3.3 模型与选择", level=2)
    add_body(doc, (
        "模型为标准化 + L2 正则的逻辑回归。候选组合为 C ∈ {0.03, 0.1, 0.3, 1} 与 "
        "class_weight ∈ {无, balanced}，共 6 组，按验证集 PR-AUC 选择（违约是少数类，PR-AUC 比准确率"
        "更能反映排序质量）。balanced 权重没有提升 PR-AUC（0.516 对 0.519），却把 Brier 分数从 0.141 "
        "推到 0.191，概率被系统性抬高，因此最终选择不加权模型。测试集上 AUC 0.755、PR-AUC 0.505、"
        "Brier 0.142（图 3），PR-AUC 相对 0.221 的随机基线提升约 1.3 倍。"))
    add_table(doc, ["C", "class_weight", "验证 AUC", "验证 PR-AUC", "Brier"], [
        ["0.03", "无", "0.751", "0.517", "0.141"],
        ["0.1", "无", "0.751", "0.518", "0.141"],
        ["0.3", "无", "0.751", "0.519", "0.141"],
        ["1.0", "无", "0.751", "0.519", "0.141"],
        ["0.1", "balanced", "0.753", "0.516", "0.191"],
        ["0.3", "balanced", "0.753", "0.516", "0.191"],
    ], "表 2  验证集上的候选模型（按 PR-AUC 选择，测试集不参与）", widths=[2.0, 3.6, 3.0, 3.4, 2.6])
    add_figure(doc, "fig3_roc_pr.png", "图 3  ROC、PR 与校准曲线：概率经过校准，可以直接用于按容量选阈值", 15.5)
    add_heading(doc, "3.4 阈值：按复核容量而不是拍脑袋", level=2)
    add_body(doc, (
        "复核线取验证集概率的 85% 分位（0.369），建议拒绝线取 95% 分位（0.677）。这样复核队列的长度"
        "恰好等于 15% 的产能，而不是先定 0.5 再祈祷队列不爆炸。两条线都保存在模型 JSON 里，"
        "策略技能只消费、不重算，避免“模型一套阈值、策略另一套阈值”的漂移。"))
    add_heading(doc, "3.5 模型如何支撑 Agent", level=2)
    add_body(doc, (
        "模型只回答“多大概率”，不回答“怎么办”。它的系数被拆成每个特征对对数几率的贡献，"
        "原因码技能据此生成“哪几项把风险推高、哪几项在缓冲”的话术；概率交给策略技能做分级；"
        "两者都不改写模型输出，保证解释与分数始终一致。"))
    add_table(doc, ["指标", "数值", "说明"], [
        ["AUC", "0.755", "排序能力，随机为 0.5"],
        ["PR-AUC", "0.505", "正类稀少时更敏感，随机基线 0.221"],
        ["Brier", "0.142", "概率校准误差，越小越好"],
        ["复核线", "0.369", "验证集 85% 分位，对应 15% 复核量"],
        ["建议拒绝线", "0.677", "验证集 95% 分位"],
        ["单条耗时", "12.9 ms", "300 条实测，约 77 条/秒"],
    ], "表 1  评分卡与阈值的关键指标（测试集 4500 条）", widths=[4.0, 3.0, 7.5])

    # 四、Skills 与组件复用
    add_heading(doc, "四、Skills 与组件复用")
    add_heading(doc, "4.1 复用清单", level=2)
    add_body(doc, (
        "系统复用了开源技能规范与校验脚本、公开数据集和常用科学计算库，清单见表 3，"
        "许可证与来源同时写入附录 B，便于核查。"))
    add_table(doc, ["组件", "版本/提交", "许可证", "在本项目中的用途"], [
        ["anthropics/skills · skill-creator", "commit 2c5958e", "Apache-2.0", "SKILL.md 规范、quick_validate.py 校验"],
        ["UCI Default of Credit Card Clients", "dataset 350", "CC BY 4.0", "训练、验证、测试数据"],
        ["scikit-learn", "0.24.1", "BSD-3-Clause", "标准化、逻辑回归、评估指标"],
        ["pandas / numpy", "1.2.4 / 1.20.1", "BSD-3-Clause", "数据处理与数值计算"],
        ["openpyxl", "3.1.5", "MIT", "复核清单 Excel 导出"],
    ], "表 3  主要复用组件", widths=[4.8, 2.8, 2.4, 4.6], font_size=9.5)
    add_heading(doc, "4.2 深入分析：quick_validate.py 如何校验一个技能", level=2)
    add_body(doc, (
        "该脚本解决的是“技能目录是否符合 Agent Skills 规范”这个子任务：输入一个技能目录，"
        "输出 (布尔值, 说明)。它会检查 SKILL.md 是否存在、frontmatter 是否为合法 YAML、name 是否符合"
        "小写连字符命名、description 是否超长或含尖括号、是否出现白名单之外的字段。依赖只有一个 PyYAML，"
        "不联网。限制也很明确：只做结构校验，不检查正文语义，也不验证技能里的脚本能否运行。"
        "我们阅读源码后在 Windows 上直接运行，中文 SKILL.md 立刻触发 UnicodeDecodeError——"
        "原因是 read_text() 没有指定编码，Windows 默认 cp936。适配方式是写一个很薄的封装"
        "（tools/skill_lint.py），在调用前把 Path.read_text 的默认编码固定为 UTF-8，原校验逻辑一行未改；"
        "同时把 version/inputs/outputs 从顶层移入 metadata，以通过字段白名单。最终 3 个技能全部 PASS，"
        "另用一个故意缺少 name 的临时技能验证它会 FAIL，确认校验真的生效而不是“永远返回真”。"))
    add_heading(doc, "4.3 自研的三个技能", level=2)
    add_body(doc, (
        "三个技能都以 SKILL.md + skill.py 的形式组织，SKILL.md 说明何时使用、规则、输入输出与边界，"
        "skill.py 提供纯函数 apply(payload)。这样技能可以独立测试、单独替换，也可以被其他 Agent 复用。"))
    add_table(doc, ["技能", "输入", "输出", "边界"], [
        ["credit-data-audit", "一批原始申请记录", "每条记录 ok/warn/error 与机器可读标记", "只查格式与取值，不查材料真伪"],
        ["risk-reason-codes", "特征值与模型贡献", "风险因素、缓释因素、摘要、低置信标记", "不输出通过/拒绝结论"],
        ["review-policy", "概率、阈值、审计状态", "等级、动作、复核优先级、依据", "建议拒绝必须人工确认"],
    ], "表 4  三个技能的分工", widths=[3.4, 3.8, 4.2, 3.4], font_size=9.5)
    add_heading(doc, "4.4 集成与消融：审计技能到底有没有用", level=2)
    add_body(doc, (
        "为验证审计技能的实际贡献，我们在测试集中注入 225 条脏数据（缺字段、额度越界、未知编码、"
        "逾期越界各四分之一）。开启审计时，169 条被判为 error 并退回补件（75.1%），56 条被判为 warn "
        "并强制转人工（24.9%），没有一条静默进入评分；关闭审计直接构造特征时，225 条全部被“成功”打分，"
        "静默流入模型（图 4）。这说明技能不是装饰性的提示词，而是能改变系统行为的组件。"))
    add_figure(doc, "fig6_audit.png", "图 4  数据审计消融：关闭技能后全部脏数据静默进入模型", 10.5)

    # 五、实验设计与结果
    add_heading(doc, "五、实验设计与结果")
    add_heading(doc, "5.1 测试集与样例构造", level=2)
    add_body(doc, (
        "测试集为分层划分出的 4500 条记录，正类 22.1%，与整体分布一致。脏数据按四类注入，每类 56～57 条；"
        "策略对比使用同一批概率，只改变“怎么把概率变成动作”，从而把模型能力与策略设计分开评估。"))
    add_heading(doc, "5.2 基线与指标", level=2)
    add_body(doc, (
        "基线有四条：P0 全部通过（不建模，代表现状）；P1 模型 0.5 阈值自动决策（代表只换模型、不换流程）；"
        "P2 在 0.5 基础上把 0.45～0.55 的边界样本转人工；P3 是本文的 Agent 容量分级。"
        "指标包括自动通过比例、自动通过人群违约率、违约者捕获率、好客户被拒比例和复核量。"))
    add_heading(doc, "5.3 结果", level=2)
    add_body(doc, (
        "表 5 与图 5 给出四条策略的对比。P3 在 15% 复核量下把自动通过人群违约率压到 15.5%，"
        "比 P0 低 6.6 个百分点；违约者捕获率 40.5%，比 P1 高 11.4 个百分点；好客户被拒比例 1.83%，"
        "只有 P1 的四成左右。也就是说，Agent 不只是“抓得更多”，还把误伤和人工量控制住了。"))
    add_table(doc, ["策略", "自动通过", "自动通过违约率", "违约者捕获率", "好客户被拒"], [
        ["P0 全部通过", "100%", "22.1%", "0%", "0%"],
        ["P1 模型 0.5 自动决策", "89.8%", "17.5%", "29.1%", "4.85%"],
        ["P2 0.5 + 边界复核", "88.3%", "16.7%", "33.2%", "3.82%"],
        ["P3 Agent 15% 分级", "85.0%", "15.5%", "40.5%", "1.83%"],
    ], "表 5  不同策略在测试集上的表现", widths=[4.2, 2.4, 3.0, 2.8, 2.6], font_size=9.5)
    add_figure(doc, "fig5_policy.png", "图 5  策略对比：自动化率、漏损与捕获率", 14.0)
    add_body(doc, (
        "图 6 的容量曲线给出了权衡关系：复核容量 5% 时自动通过人群违约率 19.6%、捕获率 15.7%；"
        "10% 时 17.5% 与 28.6%；20% 时 14.1% 与 49.0%；30% 时 12.3% 与 61.0%。"
        "业务可以按当期产能在这条曲线上选点，而不是每换一次产能就重新拍一次阈值。"))
    add_figure(doc, "fig4_capacity.png", "图 6  复核容量与漏损、捕获率的关系", 15.0)
    add_heading(doc, "5.4 消融实验", level=2)
    add_body(doc, (
        "除审计开关外，我们还做了两项检查：去掉“边界 ±0.02 转人工”规则后，P3 的捕获率下降约 1 个百分点，"
        "说明边界规则确实在补模型的盲区；把模型文件移走触发降级模式时，系统仍能给出规则分数并标注 degraded，"
        "不会崩溃，也不会把降级结果伪装成模型结果（由单元测试覆盖）。"))
    add_heading(doc, "5.5 失败案例与误差分析", level=2)
    add_body(doc, (
        "案例一：某申请违约概率 95.4%，复核员确认拒绝，与真实标签一致，属于模型与人工判断一致的正例。"
        "案例二：某申请概率 8.5%，被自动通过，但实际违约。回看其特征：近 6 个月还款正常、额度使用率不高，"
        "违约由外部因素触发，模型看不到，这是当前特征窗口的硬限制。案例三：一条年龄 15 岁的记录被审计拦截，"
        "说明闸门有效，但也暴露出上游录入质量问题。总体看，错误主要来自数据与模型的信息不足，"
        "而不是流程失控；系统能保证的是“不把脏数据当正常数据用”“不自动拒贷”“每个结论有依据可查”，"
        "但不能保证把每一个违约者都找出来。"))
    add_body(doc, (
        "从混淆矩阵看，15% 容量下复核区共 673 人，其中 403 人确实违约（精确率 59.9%），复核员每看 10 单"
        "约有 6 单值得深查；自动通过的 3827 人中有 592 人违约（15.5%），这 592 人构成漏损，"
        "而被复核区捕获的 403 人占全部违约者的 40.5%，这就是当前排序能力的上限。"
        "若业务能接受更低漏损，把容量提到 30% 可把漏损压到 39%，代价是复核量翻倍；"
        "若产能收紧到 10%，漏损会回到 71.4%。这些数字都可以用仓库里的 evaluate.py 复算。"))
    add_heading(doc, "5.6 复现与运行", level=2)
    add_body(doc, (
        "仓库提供完整的训练、评估、演示脚本与 16 个单元测试；测试集评估命令为 python scripts/evaluate.py "
        "--n 4500，演示命令为 python -m creditguard.cli demo --n 6 --interactive。图 7 是一次完整运行的"
        "终端记录，可以看到两条脏数据被退回、两单自动通过、三单转人工并给出原因码。另有两个演示入口："
        "python scripts/demo_offline.py 一键离线演示，python web/server.py 启动本地网页原型，"
        "可在浏览器里提交单笔申请并查看概率、原因码与建议动作。"))
    add_figure(doc, "fig8_console.png", "图 7  一次完整运行：审计拦截、自动通过、原因码与人工复核", 14.0)

    # 六、讨论与改进
    add_heading(doc, "六、讨论与改进")
    add_heading(doc, "6.1 真实使用价值", level=2)
    add_body(doc, (
        "对复核团队而言，最直接的变化是“看证据”而不是“看分数”：每个案件都带着 3 条风险因素和 2 条"
        "缓释因素，复核员可以先看高优先级队列，再决定是否调阅材料。对业务而言，在产能不变的前提下，"
        "自动通过人群的违约率下降 6.6 个百分点，好客户误伤减少约 3 个百分点，这两项都能用现有数据复核。"))
    add_heading(doc, "6.2 风险与边界", level=2)
    add_body(doc, (
        "第一，模型只见过 6 个月的账单与还款历史，对新客、无消费记录客户基本无效；"
        "第二，数据来自 2005 年中国台湾地区，跨地区、跨时期使用必须重新校准；"
        "第三，性别、教育、婚姻可能充当代理变量，本项目未做公平性审计，上线前需要补充；"
        "第四，系统不自动拒贷，也不处理反欺诈与额度定价，这些都需要独立的数据与合规流程。"))
    add_heading(doc, "6.3 成本与效率", level=2)
    add_body(doc, (
        "单条端到端耗时 12.9 ms，相当于每秒约 77 条，4500 条测试集一次跑完不到一分钟；同样的量人工初审"
        "按每单 5 分钟计算需要近 400 小时。系统并不替代复核员，而是把“看材料、算比例、查规则”的时间省下来，"
        "让人只处理真正需要判断的案件。导出环节直接生成带公式的 Excel 复核清单，省去人工汇总。"))
    add_heading(doc, "6.4 后续改进", level=2)
    add_body(doc, (
        "模型侧可以加入单调约束、概率校准与代价敏感阈值，让分数更贴合业务成本；数据侧可以接入外部征信、"
        "收入与设备信息，弥补 6 个月窗口的盲区；流程侧可以把大模型限制在“话术润色”这一步，"
        "并用规则校验其输出不改变结论；上线前建议先做影子模式与 A/B 实验，确认自动化率提升不会带来"
        "不可接受的漏损。"))

    # 参考文献
    add_heading(doc, "参考文献")
    refs = [
        "[1] Yeh I C, Lien C H. The comparisons of data mining techniques for the predictive accuracy of probability of default of credit card clients[J]. Expert Systems with Applications, 2009, 36(2): 2473-2480.",
        "[2] UCI Machine Learning Repository. Default of Credit Card Clients, dataset 350[DB/OL]. https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients, 2016.",
        "[3] Pedregosa F, Varoquaux G, Gramfort A, et al. Scikit-learn: Machine learning in Python[J]. Journal of Machine Learning Research, 2011, 12: 2825-2830.",
        "[4] Anthropic. Agent Skills: open-source skills and specification[EB/OL]. https://github.com/anthropics/skills, 2026.",
        "[5] 周志华. 机器学习[M]. 北京: 清华大学出版社, 2016: 53-75.",
        "[6] Saito T, Rehmsmeier M. The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets[J]. PLoS ONE, 2015, 10(3): e0118432.",
        "[7] Brier G W. Verification of forecasts expressed in terms of probability[J]. Monthly Weather Review, 1950, 78(1): 1-3.",
        "[8] 中国银行保险监督管理委员会. 商业银行互联网贷款管理暂行办法[Z]. 2020.",
    ]
    for ref in refs:
        add_reference(doc, ref)


def build_appendix(doc):
    add_heading(doc, "附录 A  运行方法与目录")
    add_body(doc, (
        "环境：Python 3.8+，依赖 numpy、pandas、scikit-learn、matplotlib、openpyxl、PyYAML。"
        "完整步骤见仓库 README，核心命令如下。"), indent=False)
    add_code(doc, """$env:PYTHONPATH="src"
python scripts/download_data.py          # 下载 UCI 数据
python scripts/train.py                  # 训练评分卡 -> models/logreg_v1.json
python scripts/evaluate.py --n 4500      # 基线与 Agent 对比 -> outputs/eval/metrics.json
python -m creditguard.cli demo --n 6 --interactive   # 交互式演示
python scripts/demo_offline.py           # 一键离线演示（无需训练）
python web/server.py                     # 本地网页原型 http://127.0.0.1:8000
python -m creditguard.cli batch --input data/samples/sample_applications.csv \\
        --out outputs/runs/batch
python -m pytest tests -q                # 16 个单元测试
python tools/skill_lint.py               # 技能规范校验（复用开源脚本）""")

    add_heading(doc, "附录 B  复用组件与许可证 / 来源说明", level=2)
    add_table(doc, ["组件", "来源", "许可证", "修改与核验"], [
        ["anthropics/skills · skill-creator", "github.com/anthropics/skills（commit 2c5958e）", "Apache-2.0",
         "原脚本未改；新增 UTF-8 封装并做正/负例校验"],
        ["UCI Default of Credit Card Clients", "archive.ics.uci.edu/dataset/350", "CC BY 4.0",
         "未修改；仅派生 18 维特征，记录数据哈希"],
        ["scikit-learn / pandas / numpy", "官方 PyPI 发行版", "BSD-3-Clause", "未修改"],
        ["openpyxl / PyYAML", "官方 PyPI 发行版", "MIT", "未修改"],
    ], "表 B-1  复用组件的来源、许可证与核验方式", widths=[4.2, 4.8, 2.2, 3.6], font_size=9)

    add_heading(doc, "附录 C  核心代码片段")
    add_code(doc, '''# src/creditguard/skills/credit-data-audit/skill.py（节选）
def audit_record(record):
    """检查单条记录，返回 status / flags / 可用的数值字段。"""
    flags, errors, warnings = [], [], []
    for col in REQUIRED:                     # 23 个原始字段缺一不可
        if record.get(col) in (None, ""):
            flags.append("missing:%s" % col); errors.append(col)
    limit, age = _to_float(record.get("LIMIT_BAL")), _to_float(record.get("AGE"))
    if limit is not None and not 10_000 <= limit <= 1_000_000:
        flags.append("range:LIMIT_BAL"); errors.append("LIMIT_BAL")
    if age is not None and not 18 <= age <= 100:
        flags.append("range:AGE"); errors.append("AGE")
    status = "error" if errors else ("warn" if warnings else "ok")
    return {"status": status, "flags": flags}

# src/creditguard/skills/review-policy/skill.py（节选）
def apply(payload):
    p, thr = float(payload["p"]), payload["thresholds"]
    if payload.get("audit_status") == "error":
        return {"band": "C", "action": "退回补件", "review_required": True}
    if p >= thr["decline_threshold"]:
        # 只给建议，必须人工确认，绝不自动拒贷
        return {"band": "C", "action": "建议拒绝并人工确认", "review_required": True}
    if p >= thr["review_threshold"]:
        return {"band": "B", "action": "人工复核", "review_required": True}
    return {"band": "A", "action": "自动通过", "review_required": False}''', "代码 1  审计技能与策略技能的核心判断")

    add_code(doc, '''# src/creditguard/agent.py（节选）
def process(self, record, interactive=False, reviewer=None):
    audit = self.registry.get("credit-data-audit").apply({"records": [record]})
    if audit["records"][0]["status"] == "error":      # 脏数据不评分
        return {"status": "rejected", "final_action": "退回补件"}
    feats = D.record_to_features(record)               # 与训练共用特征函数
    p = self.card.predict_proba(x)[0]                  # 评分卡
    reasons = self.registry.get("risk-reason-codes").apply(...)   # 原因码
    policy = self.registry.get("review-policy").apply(...)        # 策略
    if policy["review_required"] and interactive:      # 人工复核，永不自动拒贷
        decision = reviewer(result)
        result["final_action"] = decision or "待人工复核"
    return result''', "代码 2  Agent 的编排逻辑：审计 → 评分 → 解释 → 策略 → 人工")

    add_heading(doc, "附录 D  技能目录示例（SKILL.md）", level=2)
    add_code(doc, '''---
name: review-policy
description: 把模型概率与数据质量标记映射为风险等级、建议动作与复核优先级，
  按人工复核容量决定阈值，保证任何"拒贷"建议都必须人工确认。
license: Apache-2.0
metadata:
  version: 1.0.0
---
# 复核策略
## 分级规则
1. 审计 error -> 退回补件
2. p >= 建议拒绝线 -> 建议拒绝（必须人工确认）
...''', "代码 3  技能文件符合 Agent Skills 规范（经 quick_validate.py 校验通过）")


def main():
    doc = init_document()
    build_cover(doc)
    build_body(doc)
    build_appendix(doc)

    os.makedirs(HERE, exist_ok=True)
    doc.save(DOCX_PATH)

    body = "".join(BODY_CHARS)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", body))
    total = len(re.findall(r"[\u4e00-\u9fff]", body + ""))
    print("[ok] 已生成:", DOCX_PATH)
    print("[info] 正文汉字数（含小标题）：%d" % total)


if __name__ == "__main__":
    main()
