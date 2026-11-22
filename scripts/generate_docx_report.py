#!/usr/bin/env python3
"""
Generate a professionally typeset Word (.docx) evaluation report for gz_01,
combining exact parsed telemetry logs, embedded architecture/telemetry/milestone figures,
styled tables, callout boxes, running headers/footers with page numbers, and clickable links.
"""
import glob
import json
import os
from datetime import datetime

import docx
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Inches, Pt, RGBColor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_DIR = os.path.join(REPO_ROOT, "data", "gz_01")
METRICS_PATH = os.path.join(RUN_DIR, "gz01_metrics.json")
OUT_DOCX = os.path.join(REPO_ROOT, "report", "gz_01_evaluation_report.docx")

IMG_MILESTONES = os.path.join(REPO_ROOT, "assets", "gz_01_key_milestones.png")
IMG_ARCH = os.path.join(REPO_ROOT, "assets", "gz_01_architecture_diagram.png")
IMG_TELEMETRY = os.path.join(REPO_ROOT, "assets", "gz_01_telemetry_charts.png")
VIDEO_REL_URL = "../media/gz_01_full_replay.mp4"

# Palette
NAVY = RGBColor(15, 23, 42)       # #0F172A
BLUE = RGBColor(29, 78, 216)      # #1D4ED8
TEAL = RGBColor(4, 120, 87)       # #047857
SLATE = RGBColor(71, 85, 105)     # #475569
BODY_INK = RGBColor(30, 41, 59)   # #1E293B
MUTED = RGBColor(100, 116, 139)   # #64748B
RED_DARK = RGBColor(185, 28, 28)  # #B91C1C
WHITE = RGBColor(255, 255, 255)


def set_run_font(run, font_cn="微软雅黑", font_ascii="Calibri", size_pt=10.5, bold=False, italic=False, color=BODY_INK):
    run.font.name = font_ascii
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:ascii"), font_ascii)
    rFonts.set(qn("w:hAnsi"), font_ascii)
    rFonts.set(qn("w:eastAsia"), font_cn)
    rFonts.set(qn("w:cs"), font_ascii)


def set_cell_shading(cell, fill_hex):
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_margins(cell, top=90, bottom=90, left=130, right=130):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for m, val in [("top", top), ("bottom", bottom), ("left", left), ("right", right)]:
        node = OxmlElement(f"w:{m}")
        node.set(qn("w:w"), str(val))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def set_table_borders(table, border_color="CBD5E1", header_bottom_color="1E3A8A"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="single" w:sz="6" w:space="0" w:color="{header_bottom_color}"/>'
        f'  <w:bottom w:val="single" w:sz="8" w:space="0" w:color="{header_bottom_color}"/>'
        f'  <w:insideH w:val="single" w:sz="4" w:space="0" w:color="{border_color}"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def prevent_row_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:cantSplit"))


def repeat_header_row(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))


def add_hyperlink(paragraph, text, url, size_pt=10.0, color=BLUE, underline=True):
    part = paragraph.part
    r_id = part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Calibri")
    rFonts.set(qn("w:hAnsi"), "Calibri")
    rFonts.set(qn("w:eastAsia"), "微软雅黑")
    rPr.append(rFonts)

    c = OxmlElement("w:color")
    c.set(qn("w:val"), str(color))
    rPr.append(c)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size_pt * 2)))
    rPr.append(sz)

    if underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        rPr.append(u)

    new_run.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)
    return hyperlink


def add_page_number_fields(run):
    fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls("w"))
    instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> PAGE </w:instrText>' % nsdecls("w"))
    fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls("w"))
    fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls("w"))
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)


def add_numpages_fields(run):
    fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls("w"))
    instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> NUMPAGES </w:instrText>' % nsdecls("w"))
    fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls("w"))
    fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls("w"))
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)


def add_callout(doc, title, paragraphs_spec, fill_hex="EFF6FF", accent_hex="2563EB", title_color=BLUE):
    """Add a single-cell full-width shaded callout card with a bold left accent bar."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Cm(16.6)
    set_cell_shading(cell, fill_hex)
    set_cell_margins(cell, top=140, bottom=140, left=200, right=180)
    prevent_row_split(tbl.rows[0])

    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{accent_hex}"/>'
        f'  <w:top w:val="single" w:sz="4" w:space="0" w:color="{fill_hex}"/>'
        f'  <w:right w:val="single" w:sz="4" w:space="0" w:color="{fill_hex}"/>'
        f'  <w:bottom w:val="single" w:sz="4" w:space="0" w:color="{fill_hex}"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)

    p0 = cell.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = Pt(4)
    p0.paragraph_format.line_spacing = 1.25
    r0 = p0.add_run(title)
    set_run_font(r0, size_pt=10.5, bold=True, color=title_color)

    for idx, segments in enumerate(paragraphs_spec):
        p = cell.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2 if idx < len(paragraphs_spec) - 1 else 0)
        p.paragraph_format.line_spacing = 1.32
        for text, is_bold, is_code, col in segments:
            r = p.add_run(text)
            set_run_font(
                r,
                font_cn="微软雅黑",
                font_ascii="Consolas" if is_code else "Calibri",
                size_pt=9.6 if is_code else 10.0,
                bold=is_bold,
                color=col if col else BODY_INK,
            )

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(6)


def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        f'  <w:bottom w:val="single" w:sz="10" w:space="4" w:color="1D4ED8"/>'
        f'</w:pBdr>'
    )
    pPr.append(pBdr)
    r = p.add_run(text)
    set_run_font(r, size_pt=14.5, bold=True, color=NAVY)
    return p


def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_run_font(r, size_pt=12.0, bold=True, color=BLUE)
    return p


def add_rich_paragraph(doc, segments, space_after=5, left_indent_cm=0.0):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
    if left_indent_cm > 0:
        p.paragraph_format.left_indent = Cm(left_indent_cm)
    for seg in segments:
        text = seg[0]
        bold = seg[1] if len(seg) > 1 else False
        code = seg[2] if len(seg) > 2 else False
        col = seg[3] if len(seg) > 3 else BODY_INK
        italic = seg[4] if len(seg) > 4 else False
        r = p.add_run(text)
        set_run_font(
            r,
            font_cn="微软雅黑",
            font_ascii="Consolas" if code else "Calibri",
            size_pt=9.6 if code else 10.5,
            bold=bold,
            italic=italic,
            color=col,
        )
    return p


def add_bullet(doc, lead_bold, body_segments, space_after=4):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.55)
    p.paragraph_format.first_line_indent = Cm(-0.35)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35

    r_dot = p.add_run("•  ")
    set_run_font(r_dot, size_pt=10.5, bold=True, color=BLUE)

    if lead_bold:
        r_lead = p.add_run(lead_bold)
        set_run_font(r_lead, size_pt=10.5, bold=True, color=NAVY)

    for seg in body_segments:
        text = seg[0]
        bold = seg[1] if len(seg) > 1 else False
        code = seg[2] if len(seg) > 2 else False
        col = seg[3] if len(seg) > 3 else BODY_INK
        italic = seg[4] if len(seg) > 4 else False
        r = p.add_run(text)
        set_run_font(
            r,
            font_cn="微软雅黑",
            font_ascii="Consolas" if code else "Calibri",
            size_pt=9.5 if code else 10.5,
            bold=bold,
            italic=italic,
            color=col,
        )
    return p


def add_styled_table(doc, headers, rows, col_widths_cm, header_bg="1E3A8A", zebra_bg="F8FAFC", font_size=9.3):
    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    set_table_borders(tbl, border_color="CBD5E1", header_bottom_color=header_bg)

    # Header row
    hdr_row = tbl.rows[0]
    repeat_header_row(hdr_row)
    prevent_row_split(hdr_row)
    for ci, h_text in enumerate(headers):
        cell = hdr_row.cells[ci]
        cell.width = Cm(col_widths_cm[ci])
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_shading(cell, header_bg)
        set_cell_margins(cell, top=95, bottom=95, left=110, right=110)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(h_text)
        set_run_font(r, size_pt=font_size + 0.2, bold=True, color=WHITE)

    # Data rows
    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri + 1]
        prevent_row_split(row)
        bg = zebra_bg if ri % 2 == 1 else "FFFFFF"
        for ci, cell_spec in enumerate(row_data):
            cell = row.cells[ci]
            cell.width = Cm(col_widths_cm[ci])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=80, bottom=80, left=110, right=110)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.25
            if isinstance(cell_spec, str):
                r = p.add_run(cell_spec)
                set_run_font(r, size_pt=font_size, bold=(ci == 0), color=NAVY if ci == 0 else BODY_INK)
            else:
                for seg in cell_spec:
                    text = seg[0]
                    bold = seg[1] if len(seg) > 1 else False
                    code = seg[2] if len(seg) > 2 else False
                    col = seg[3] if len(seg) > 3 else BODY_INK
                    r = p.add_run(text)
                    set_run_font(
                        r,
                        font_cn="微软雅黑",
                        font_ascii="Consolas" if code else "Calibri",
                        size_pt=font_size - 0.3 if code else font_size,
                        bold=bold,
                        color=col,
                    )

    sp = doc.add_paragraph()
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.space_after = Pt(5)
    return tbl


def add_figure(doc, img_path, caption_text, width_cm=16.4):
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(4)
    p_img.paragraph_format.space_after = Pt(3)
    p_img.paragraph_format.keep_with_next = True
    r_img = p_img.add_run()
    r_img.add_picture(img_path, width=Cm(width_cm))

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(0)
    p_cap.paragraph_format.space_after = Pt(8)
    r_cap = p_cap.add_run(caption_text)
    set_run_font(r_cap, size_pt=9.2, bold=False, italic=False, color=SLATE)


def load_milestone_appendix_rows():
    """Directly parse actual milestone steps from gz_01 history.jsonl & rollout/*.json."""
    history = [json.loads(l) for l in open(os.path.join(RUN_DIR, "public", "history.jsonl"), encoding="utf-8") if l.strip()]
    rollouts = [json.load(open(f, encoding="utf-8")) for f in sorted(glob.glob(os.path.join(RUN_DIR, "rollout", "*.json")))]
    t0 = datetime.fromisoformat(history[0]["at"].replace("Z", "+00:00"))

    key_indices = [1, 2, 5, 6, 8, 10, 11, 13, 14, 22, 39, 45, 46, 55, 57]
    notes_map = {
        1: "初始平视仅见白墙，开始观察",
        2: "主动低头 0.695 rad 搜寻桌面",
        5: "头部就位，锁定蓝/黑双方块",
        6: "尝试降躯干至 -0.30 m 扩大可达空间",
        8: "开始在桌后安全空间抬升右臂",
        10: "步长 0.052m > 0.05m 被安全层拦截",
        11: "检测到 lift 仍在移动，拦截并要求重观",
        13: "躯干降至 -0.15m 稳定到位 (arrived)",
        14: "正式开启右臂连续逼近阶段",
        22: "试探底盘前移未动，笔记记录止损",
        39: "蓝方块首次进入右腕相机视野",
        45: "擦近桌缘受阻，察觉风险并停步",
        46: "自主抬高 3.4 cm 至 Z=0.928m 脱困",
        55: "蓝方块居中于右腕像素 (150,109)",
        57: "右爪跨悬于蓝方块正上方（达 5M 上限停）",
    }
    rows = []
    for idx in key_indices:
        h = history[idx - 1]
        r = rollouts[idx - 1]
        dt = (datetime.fromisoformat(h["at"].replace("Z", "+00:00")) - t0).total_seconds()
        obs = h.get("observation")
        if obs:
            rx, ry, rz = obs["arms"]["right"]["xyz"]
            pose_str = f"({rx:+.3f}, {ry:+.3f}, {rz:+.3f})\nsim={obs['stamp_s']:.1f}s"
        else:
            pose_str = "复用上一帧\n（被安全层拦截）"
        st = h["status"]
        st_color = TEAL if st in ("observed", "arrived") else (RED_DARK if st == "rejected" else RGBColor(180, 83, 9))
        rows.append([
            [("#{:02d}".format(idx), True, True, NAVY)],
            [(f"+{dt:.0f}s", False, True, SLATE)],
            [(h["tool"], True, True, BLUE)],
            [(st, True, True, st_color)],
            [(pose_str, False, True, BODY_INK)],
            [(notes_map.get(idx, ""), False, False, BODY_INK)],
        ])
    return rows


def main():
    metrics = json.load(open(METRICS_PATH, encoding="utf-8"))
    appendix_rows = load_milestone_appendix_rows()

    doc = Document()

    # Configure A4 page & margins
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.different_first_page_header_footer = True

    # Configure Normal style
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal._element.get_or_add_rPr().insert(0, parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="微软雅黑"/>'))

    # Header & Footer (Pages 2+)
    hdr = section.header
    p_hdr = hdr.paragraphs[0]
    p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_hdr = p_hdr.add_run("GPT-6 Astra × ROBOTIS AI Worker (gz_01)  |  Windows 11 首次复现与研究评估报告")
    set_run_font(r_hdr, size_pt=8.5, color=MUTED)

    ftr = section.footer
    p_ftr = ftr.paragraphs[0]
    p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_f1 = p_ftr.add_run("第 ")
    set_run_font(r_f1, size_pt=8.5, color=MUTED)
    r_pg = p_ftr.add_run()
    set_run_font(r_pg, size_pt=8.5, color=MUTED)
    add_page_number_fields(r_pg)
    r_f2 = p_ftr.add_run(" 页 / 共 ")
    set_run_font(r_f2, size_pt=8.5, color=MUTED)
    r_np = p_ftr.add_run()
    set_run_font(r_np, size_pt=8.5, color=MUTED)
    add_numpages_fields(r_np)
    r_f3 = p_ftr.add_run(" 页")
    set_run_font(r_f3, size_pt=8.5, color=MUTED)

    # ------------------------------------------------------------------
    # Title Banner Block
    # ------------------------------------------------------------------
    banner = doc.add_table(rows=1, cols=1)
    banner.alignment = WD_TABLE_ALIGNMENT.CENTER
    banner.autofit = False
    b_cell = banner.cell(0, 0)
    b_cell.width = Cm(16.6)
    set_cell_shading(b_cell, "0F172A")
    set_cell_margins(b_cell, top=220, bottom=220, left=240, right=240)
    prevent_row_split(banner.rows[0])

    bp1 = b_cell.paragraphs[0]
    bp1.paragraph_format.space_before = Pt(0)
    bp1.paragraph_format.space_after = Pt(4)
    br1 = bp1.add_run("具身智能复现工程评估报告  ·  RUN ID: GZ_01")
    set_run_font(br1, size_pt=9.5, bold=True, color=RGBColor(56, 189, 248))

    bp2 = b_cell.add_paragraph()
    bp2.paragraph_format.space_before = Pt(2)
    bp2.paragraph_format.space_after = Pt(6)
    br2 = bp2.add_run("GPT-6 Astra × ROBOTIS AI Worker\nWindows 11 首次端到端复现与技术评估")
    set_run_font(br2, size_pt=19.0, bold=True, color=WHITE)

    bp3 = b_cell.add_paragraph()
    bp3.paragraph_format.space_before = Pt(0)
    bp3.paragraph_format.space_after = Pt(0)
    br3 = bp3.add_run("“大模型低频决策 × 机器人高频运控”分层范式实测、完整过程录像解析与性能瓶颈诊断")
    set_run_font(br3, size_pt=10.5, color=RGBColor(203, 213, 225))

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)

    # Metadata Card Table
    add_styled_table(
        doc,
        headers=["实验参数项", "实测配置与数值", "实验参数项", "实测配置与数值"],
        rows=[
            [
                "实验代号",
                [("gz_01", True, True, BLUE)],
                "复现时间",
                "2026-11-22 16:18–16:40 (UTC+8)",
            ],
            [
                "自然语言指令",
                [("\"pick up the blue block\"", True, True, NAVY)],
                "仿真场景",
                [("table.sdf", False, True, BODY_INK), ("（桌面蓝/黑双方块）", False, False, SLATE)],
            ],
            [
                "决策模型",
                [("gpt-6-astra", True, True, NAVY), (" (effort: low)", False, False, SLATE)],
                "运行环境",
                "Win11 Pro + WSL2 + Docker + RTX 5070",
            ],
            [
                "总现实耗时",
                [(f"{metrics['elapsed_s_result']} s（20 分 42 秒）", True, False, NAVY)],
                "结束状态",
                [("halted:token_limit", True, True, RED_DARK), ("（夹爪已悬停蓝方块正上方）", False, False, SLATE)],
            ],
        ],
        col_widths_cm=[2.8, 5.5, 2.8, 5.5],
        header_bg="1E293B",
        font_size=9.2,
    )

    # Core Verdict Callout
    add_callout(
        doc,
        title="核心结论与最大工程发现（Executive Summary）",
        paragraphs_spec=[
            [
                ("1. 端到端闭环跑通：", True, False, NAVY),
                ("已在 Windows 11 消费级笔记本上完整打通 ", False, False, None),
                ("GPT-6 Astra → Codex App Server → Harness → ROS 2 (Zenoh) / Cyclo → Gazebo", True, True, BLUE),
                (" 全链路。在零深度测距、零物体坐标预编码的纯三路 RGB 条件下，模型自主完成了", False, False, None),
                ("低头搜寻 → 降躯干 → 绕桌缘抬臂 → 避碰自救 → 像素视差对准", True, False, NAVY),
                ("，在第 57 步触及默认 500 万 Token 上限暂停时，右臂夹爪已精准跨停在蓝色方块正上方（仅差最后“下降 2 cm → 合爪 → 抬起”3 步）。", False, False, None),
            ],
            [
                ("2. 真正耗时瓶颈并非大模型推理：", True, False, NAVY),
                ("全程 1296.3 秒（Call 1–57）中，大模型单次多模态视觉思考均值仅 ", False, False, None),
                ("7.67 秒", True, False, BLUE),
                ("（占 33.1%）；高达 ", False, False, None),
                ("56.7%（734.5 秒）", True, False, RED_DARK),
                (" 竟是模型自主发现 Gazebo 运行在 ", False, False, None),
                ("0.082×", True, True, RED_DARK),
                (" 慢动作下，自发调用了 ", False, False, None),
                ("26 次 sleep()", True, True, BODY_INK),
                (" 主动等待机械臂运动到位。一旦修复慢仿真使 RTF 恢复至 0.8–1.0×，预计 3–5 分钟即可完成抓取。", False, False, None),
            ],
        ],
        fill_hex="EFF6FF",
        accent_hex="1D4ED8",
        title_color=BLUE,
    )

    # ------------------------------------------------------------------
    # Section 1: Video & Key Milestones
    # ------------------------------------------------------------------
    add_heading_1(doc, "1. 完整复现过程视频与关键阶段演进")
    add_heading_2(doc, "1.1 完整过程评估视频（79.7 秒 · 1440×810 H.264 MP4）")
    add_rich_paragraph(doc, [
        ("为直观评估", False, False, BODY_INK),
        ("“大模型低频决策 × 机器人高频运控”", True, False, NAVY),
        ("的完整交互过程，本报告配套生成了由 ", False, False, BODY_INK),
        ("gz_01", False, True, BLUE),
        (" 原始全部 ", False, False, BODY_INK),
        ("57 次工具调用", True, False, NAVY),
        ("（55 组三路同步实拍相机图像 + 2 次安全拦截事件）合成的高清回放视频，同屏展示上层模型推理依据、自主 ", False, False, BODY_INK),
        ("sleep", False, True, BODY_INK),
        (" 节拍与底层 100 Hz 运控反馈轨迹：", False, False, BODY_INK),
    ])

    # Video links callout
    p_v1 = doc.add_paragraph()
    p_v1.paragraph_format.left_indent = Cm(0.55)
    p_v1.paragraph_format.first_line_indent = Cm(-0.35)
    p_v1.paragraph_format.space_after = Pt(3)
    r_b1 = p_v1.add_run("•  仓储高清视频文件（相对路径）：")
    set_run_font(r_b1, size_pt=10.2, bold=True, color=NAVY)
    add_hyperlink(p_v1, "media/gz_01_full_replay.mp4（2.61 MB，1440×810 H.264）", VIDEO_REL_URL, size_pt=10.2)

    p_v2 = doc.add_paragraph()
    p_v2.paragraph_format.left_indent = Cm(0.55)
    p_v2.paragraph_format.first_line_indent = Cm(-0.35)
    p_v2.paragraph_format.space_after = Pt(3)
    r_b2 = p_v2.add_run("•  浏览器在线播放入口（本地 5500 服务开启时有效）：")
    set_run_font(r_b2, size_pt=10.2, bold=True, color=NAVY)
    add_hyperlink(p_v2, "http://localhost:5500/ffw_codex/runs/gz_01/gz_01_full_replay.mp4", "http://localhost:5500/ffw_codex/runs/gz_01/gz_01_full_replay.mp4", size_pt=9.8)

    p_v3 = doc.add_paragraph()
    p_v3.paragraph_format.left_indent = Cm(0.55)
    p_v3.paragraph_format.first_line_indent = Cm(-0.35)
    p_v3.paragraph_format.space_after = Pt(6)
    r_b3 = p_v3.add_run("•  交互式逐帧审查面板（Live Viewer，填入 gz_01 点 Follow run）：")
    set_run_font(r_b3, size_pt=10.2, bold=True, color=NAVY)
    add_hyperlink(p_v3, "http://localhost:5500/ffw_codex/run_viewer.html", "http://localhost:5500/ffw_codex/run_viewer.html", size_pt=9.8)

    add_heading_2(doc, "1.2 六大关键里程碑双视角演进（头部主摄 + 右腕特写）")
    add_figure(
        doc,
        IMG_MILESTONES,
        "图 1  gz_01 任务六大关键里程碑双视角演进（顶部左侧为头部主视角 672×376，右侧为右腕相机特写 424×240）",
        width_cm=16.4,
    )

    # ------------------------------------------------------------------
    # Section 2: Architecture
    # ------------------------------------------------------------------
    add_heading_1(doc, "2. 系统架构剖析：“大模型低频决策 × 机器人高频运控”")
    add_rich_paragraph(doc, [
        ("该研究最核心的工程设计思想，是将", False, False, BODY_INK),
        ("开放世界语义理解与长程视觉规划", True, False, NAVY),
        ("与", False, False, BODY_INK),
        ("确定性高频实时运动控制", True, False, NAVY),
        ("彻底解耦，中间由 ", False, False, BODY_INK),
        ("Harness 校验守卫层", True, False, TEAL),
        (" 严格把关安全边界、坐标系契约与多传感器时间同步。图 2 给出了结合本次 ", False, False, BODY_INK),
        ("gz_01", False, True, BLUE),
        (" 实测数据的三层解耦闭环架构。", False, False, BODY_INK),
    ])
    add_figure(
        doc,
        IMG_ARCH,
        "图 2  “大模型低频决策 × 机器人高频运控”三层解耦闭环架构与 gz_01 实测参数标注",
        width_cm=16.4,
    )

    add_heading_2(doc, "2.1 跨 3 个数量级的控制频率分层对照")
    add_styled_table(
        doc,
        headers=["系统层级", "核心组件与源码配置文件", "运行频率 / 同步指标", "等效周期", "职责边界与安全性分工"],
        rows=[
            [
                "物理动力学层",
                [("Gazebo Harmonic\n", True, False, NAVY), ("table.sdf: max_step_size=0.001", False, True, SLATE)],
                [("1000 Hz", True, False, BLUE)],
                "1.0 ms",
                "刚体动力学积分、桌面/方块接触碰撞与摩擦计算",
            ],
            [
                "关节伺服环",
                [("ros2_control controller_manager\n", True, False, NAVY), ("ffw_sg2_follower_ai_hardware_controller.yaml", False, True, SLATE)],
                [("100 Hz", True, False, BLUE)],
                "10.0 ms",
                "双臂、头部、升降与底盘共 6 组活跃控制器闭环追踪",
            ],
            [
                "笛卡尔规划层",
                [("Cyclo MoveL 控制器\n", True, False, NAVY), ("ai_worker_config.yaml: control_frequency", False, True, SLATE)],
                [("100 Hz", True, False, BLUE)],
                "10.0 ms",
                "末端直线插补、逆运动学求解与基础自碰撞防护",
            ],
            [
                "移动底盘层",
                [("底盘速度斜坡发布\n", True, False, NAVY), ("config_gazebo.yaml: base.publish_hz", False, True, SLATE)],
                [("20 Hz", True, False, TEAL)],
                "50.0 ms",
                "/cmd_vel 速度斜坡加减速、里程计追踪与静止判定",
            ],
            [
                "多传感器同步",
                [("Harness 观测守卫\n", True, False, NAVY), ("observation_guard_gazebo.py (实测55帧)", False, True, SLATE)],
                [("同步窗 ≤ 15 ms", True, False, TEAL)],
                "实测均值 2.4 ms\n(最大 5.0 ms)",
                "对齐 3 路 RGB 图像、/joint_states 与 /odom 时间戳",
            ],
            [
                "大模型决策\n(理论 1× 实时)",
                [("GPT-6 Astra (扣除 sleep)\n", True, False, NAVY), ("纯三路 RGB + 文本输出 6D 目标", False, False, SLATE)],
                [("~0.12 Hz", True, False, BLUE)],
                "约 8.5 s / 步",
                "低频语义规划、视觉定位、异常恢复（均值思考 7.67 s）",
            ],
            [
                "大模型决策\n(本次 gz_01 实测)",
                [("含 26 次慢仿真自适应 sleep\n", True, False, NAVY), ("57 次调用 / 27 次动作", False, False, SLATE)],
                [("0.046 Hz\n(动作 0.022 Hz)", True, False, RED_DARK)],
                "21.8 s / 调用\n(46.0 s / 动作)",
                "比底层 100 Hz 运控低 ~2,200× 至 ~4,600×",
            ],
        ],
        col_widths_cm=[2.6, 5.2, 2.5, 2.5, 3.8],
        font_size=8.8,
    )

    # ------------------------------------------------------------------
    # Section 3: Telemetry & Bottleneck Diagnosis
    # ------------------------------------------------------------------
    add_heading_1(doc, "3. 量化实验数据与核心瓶颈诊断")
    add_figure(
        doc,
        IMG_TELEMETRY,
        "图 3  gz_01 量化遥测与分层架构分析四联图：(A) 三元耗时拆解；(B) 对数频率对比；(C) 右臂 3D 轨迹；(D) 单步构成与 Token 曲线",
        width_cm=16.4,
    )

    add_heading_2(doc, "3.1 gz_01 完整实测指标总表")
    add_styled_table(
        doc,
        headers=["评估维度", "实测数值", "工程解读与数据来源"],
        rows=[
            [
                "总现实耗时",
                "1242.4 s（20 分 42 秒）",
                "来自 result.json；首尾工具调用时间跨度 1296.32 s（calls/*.json）",
            ],
            [
                "仿真内经过时间",
                "106.46 s（sim_s: 21.22 → 127.68 s）",
                "平均实时因子 RTF = 0.0821×（仿真速度约为现实时间的 1/12）",
            ],
            [
                "工具调用构成（共 57 次）",
                "observe: 27 | move: 25 | lift: 2 | start: 1 | head: 1 | base: 1",
                "实际下发物理动作 27 次，同步观测 55 次；26 次动作中仅 lift 报 1 次 arrived",
            ],
            [
                "安全守卫拦截（2 次）",
                "invalid_action: 1 | observation_rejected: 1",
                "Call #10 步幅 0.052m > 0.05m 被拒；Call #11 检测到 lift 漂移被拒并要求重观",
            ],
            [
                "耗时三元拆解",
                "sleep: 734.5 s (56.7%) | LLM+API: 429.3 s (33.1%) | 运控: 132.5 s (10.2%)",
                "纯 LLM 多模态思考+API 均值 7.67 s（中位数 6.50 s）；26 次自主 sleep 占主要时间",
            ],
            [
                "Token 消耗与成本",
                "总计 5,024,728（缓存命中 4,917,760，命中率 98.03%）",
                "未缓存输入 98,773 | 输出 8,195 | 推理 1,068；按 API 价估算约 $6.315",
            ],
            [
                "最终机械臂状态",
                "Right EE = (0.444, -0.202, 0.937) m, gripper = 0.001",
                "右臂从身侧 (-0.015, -0.278, 0.576) 伸至蓝色方块正上方，夹爪张开就位",
            ],
        ],
        col_widths_cm=[3.4, 5.8, 7.4],
        font_size=9.0,
    )

    add_heading_2(doc, "3.2 为什么跑了 20 分钟？——慢仿真根因深度定位")
    add_rich_paragraph(doc, [
        ("精确对齐 ", False, False, BODY_INK),
        ("calls/*_request.json", False, True, BLUE),
        ("、", False, False, BODY_INK),
        ("calls/*_result.json", False, True, BLUE),
        (" 与 ", False, False, BODY_INK),
        ("rpc_in.jsonl", False, True, BLUE),
        (" 中的底层事件时间戳后，我们发现了两个极具价值的工程事实：", False, False, BODY_INK),
    ])
    add_bullet(doc, "大模型在线自适应节拍（Adaptive Waiting）：", [
        ("因为 Gazebo 运行在 ", False, False, None),
        ("0.082×", True, True, RED_DARK),
        (" 慢动作下，一条仿真内需 2–3 秒的移动指令需要现实 25–35 秒才能走完。模型在初始几步发现工具返回 ", False, False, None),
        ("stopped before its target", False, True, BODY_INK),
        (" 后，竟自主总结出规律并开始在两次工具调用之间插入 ", False, False, None),
        ("20–30 秒的 sleep()", True, False, NAVY),
        ("（共 26 次、累计 734.52 秒，占全程 56.7%），从而精准踩点观测机械臂到位。", False, False, None),
    ])
    add_bullet(doc, "慢仿真根因已通过日志实证定位：", [
        ("① 图形渲染回退到 CPU 软渲染：实测检查容器内 ", False, False, None),
        ("/root/.gz/rendering/ogre2.log", False, True, BLUE),
        (" 显示 Ogre2 正在使用 ", False, False, None),
        ("GL_RENDERER = llvmpipe (LLVM 20.1.2, 256 bits)", True, True, RED_DARK),
        (" 与 ", False, False, None),
        ("EGL_MESA_device_software", False, True, BODY_INK),
        ("，且 ", False, False, None),
        ("nvidia-smi", False, True, BODY_INK),
        (" 显示 Gazebo 进程尚未挂载到 RTX 5070（", False, False, None),
        ("No running processes found", False, True, BODY_INK),
        ("），导致 ", False, False, None),
        ("gz sim server", False, True, BODY_INK),
        ("（217% CPU）与 ", False, False, None),
        ("gz sim gui", False, True, BODY_INK),
        ("（201% CPU）需纯靠 CPU 渲染 3 路相机与 GUI；② 物理配置限制：同时 ", False, False, None),
        ("table.sdf", False, True, BLUE),
        (" 中声明了 ", False, False, None),
        ("<max_step_size>0.001</max_step_size>", False, True, BODY_INK),
        (" 与 ", False, False, None),
        ("<real_time_update_rate>100</real_time_update_rate>", False, True, BODY_INK),
        ("。两者叠加将全过程均值拉低至 ", False, False, None),
        ("0.0821×", True, True, RED_DARK),
        ("。若在下一轮排查启用 WSLg D3D12/NVIDIA 硬件渲染（或 ", False, False, None),
        ("gui:=false", False, True, BODY_INK),
        ("）并解除更新率限制、恢复接近 1.0× 实时运行，省去 26 次冗余 ", False, False, None),
        ("sleep", False, True, BODY_INK),
        (" 后，推算同类任务耗时可降至 ", False, False, None),
        ("约 5.5 分钟（~330 s）", True, False, TEAL),
        ("。", False, False, None),
    ])

    # ------------------------------------------------------------------
    # Section 4: Emergent Behaviors
    # ------------------------------------------------------------------
    add_heading_1(doc, "4. 具身智能涌现行为深度观察（研究亮点）")
    add_rich_paragraph(doc, [
        ("尽管仿真速度受限，但日志完整记录到了 ", False, False, BODY_INK),
        ("6 项未经过任务特定硬编码或微调的具身涌现能力", True, False, NAVY),
        ("，充分体现了新一代通用视觉推理模型在具身控制上层决策中的独特优势：", False, False, BODY_INK),
    ])
    add_bullet(doc, "1. 主动视觉搜索（Active Perception）：", [
        ("Call #01 初始平视画面全白，模型立刻判断 “Head view is above the workspace; tilt down to locate the blue block”，下发 ", False, False, None),
        ("robot_head(0.695 rad)", False, True, BLUE),
        (" 主动低头锁定桌面与红/蓝/黑场景结构。", False, False, None),
    ])
    add_bullet(doc, "2. 全身自由度协同（Whole-body Coordination）：", [
        ("Call #06–#13 自主决定先降低躯干高度（", False, False, None),
        ("lift_joint = -0.15 m", False, True, BODY_INK),
        ("），扩展右臂对桌面的俯仰与前伸可达工作空间，并严格在动作前验证安全余量。", False, False, None),
    ])
    add_bullet(doc, "3. 物理接触察觉与避碰自救（Collision-aware Recovery）：", [
        ("Call #45 时，模型将运控反馈的 ", False, False, None),
        ("stopped .042 m short", False, True, BODY_INK),
        (" 与头部相机中“下手指紧贴近桌缘”的视觉线索相互印证，判断发生潜在擦碰，果断抬臂 3.4 cm（", False, False, None),
        ("z: 0.894 → 0.928 m", False, True, TEAL),
        ("），观察到指下留出安全间隙后再继续推进。", False, False, None),
    ])
    add_bullet(doc, "4. 零深度纯 RGB 像素追踪与视差测距（Visual Servoing & Parallax）：", [
        ("在没有任何深度图、标定矩阵或外部目标检测器情况下，自 Call #39 蓝色方块刚进入右腕相机边缘起，模型连续追踪方块在图像中的像素中心 ", False, False, None),
        ("(280,52) → (227,73) → (183,96) → (150,109)", True, True, BLUE),
        ("，结合已知机械臂位移利用双帧视差（Parallax）估计方块位于 ", False, False, None),
        ("x≈0.50, y≈-0.20", False, True, BODY_INK),
        ("，最终成功将夹爪对准方块正上方。", False, False, None),
    ])
    add_bullet(doc, "5. 在线系统辨识与持久化工作记忆（NOTES.md）：", [
        ("模型在 Codex 沙盒中自发用终端命令编写并更新了工作笔记 ", False, False, None),
        ("notes/NOTES.md", False, True, BLUE),
        ("，自行归纳仿真延迟与物体坐标估算：", False, False, None),
    ])

    add_callout(
        doc,
        title="模型自主编写的工作记忆原文摘录（agent/notes/NOTES.md）",
        paragraphs_spec=[
            [("\"Most commands report stopped early, settle over ~25s wall; some remain short. Suspected near-table contact at EE z .887; raised to .935 and now head shows gap. Blue cube wrist center (280,52), about 70px wide. Estimated cube x~.50, y~-.20; table height still uncertain likely ~.88-.90. Base attempt no progress; did not repeat.\"", False, True, SLATE)],
        ],
        fill_hex="F8FAFC",
        accent_hex="64748B",
        title_color=NAVY,
    )

    add_bullet(doc, "6. 失败策略快速止损（Fast Failure Pivot）：", [
        ("Call #22 尝试驱动底盘 ", False, False, None),
        ("robot_base", False, True, BODY_INK),
        (" 前移未获位移，模型在对比前后观测画像后立即在笔记中标记“Base attempt no progress; did not repeat”，果断放弃底盘试探，转而全力通过臂展完成接近。", False, False, None),
    ])

    # ------------------------------------------------------------------
    # Section 5: Evaluation & Comparison
    # ------------------------------------------------------------------
    add_heading_1(doc, "5. 研究范式综合评估：优势、边界与对比")
    add_heading_2(doc, "5.1 与主流端到端 VLA（Vision-Language-Action）路线的本质差异")
    add_styled_table(
        doc,
        headers=["评估维度", "本路线：通用大模型低频决策 + 工具契约 + 高频运控", "端到端 VLA 路线（RT-2 / OpenVLA / π0 等）"],
        rows=[
            [
                "零样本泛化与推理深度",
                [("极强：", True, False, TEAL), ("可跨视角视差估计、写在线笔记、异常避碰自救、多工具协同", False, False, BODY_INK)],
                "依赖遥操作示教数据覆盖面，长程逻辑纠错与异常恢复能力较弱",
            ],
            [
                "数据与训练门槛",
                [("几乎为零：", True, False, TEAL), ("无需采集海量真机轨迹，核心工作转为编写工具契约与安全 Harness", False, False, BODY_INK)],
                "需要大规模高质量真机/仿真遥操作数据采集与模型微调",
            ],
            [
                "闭环频率与动态响应",
                [("极低（~0.1–0.2 Hz）：", True, False, RED_DARK), ("受限于云端 API 延迟与多图高分辨率推理时间", False, False, BODY_INK)],
                "中高（5–50 Hz），本地 GPU 可支撑高频连续视觉伺服与灵巧手操作",
            ],
            [
                "安全可审计性与可解释性",
                [("高：", True, False, TEAL), ("每一步都有显式自然语言理由 + 硬限幅校验 + 传统底层安全控制器兜底", False, False, BODY_INK)],
                "端到端黑盒直接输出连续动作块，安全边界较难形式化审计",
            ],
            [
                "推理计算成本",
                "较高（长程多轮上下文达数百万 Token，高度依赖 Prompt Cache 降至 ~2% 有效输入成本）",
                "单次前向计算固定且边际成本极低，适合高并发长期部署",
            ],
            [
                "最适用任务谱系",
                "开放语义指令、非结构化长程多步骤规划、跨部件协同、准静态操作",
                "高动态物体接抛、接触力敏感装配、工业高速节拍重复抓取",
            ],
        ],
        col_widths_cm=[3.2, 6.9, 6.5],
        font_size=9.0,
    )

    add_heading_2(doc, "5.2 本次复现暴露的 4 项关键研究局限")
    add_bullet(doc, "1. 单步限幅过细导致“步数碎片化”与上下文膨胀：", [
        ("默认 ", False, False, None),
        ("limits.max_step_m = 0.05 m", False, True, BLUE),
        (" 使机械臂从身侧伸到桌前 45 cm 至少需十余次独立调用，每步附带 3 张图像迅速累积至 500 万 Token（虽有 98.03% 缓存命中，仍触及上限）；同时模型未能充分利用 ", False, False, None),
        ("robot_execute_plan", False, True, BODY_INK),
        (" 在开阔空间内打包连续 3–5 步移动。", False, False, None),
    ])
    add_bullet(doc, "2. 动作执行期“开环盲区”风险：", [
        ("发出 ", False, False, None),
        ("robot_move", False, True, BODY_INK),
        (" 到轨迹走完期间大模型无法实时看图，若遇动态障碍物或物体滑落，只能等运动停止后才能察觉，完全依赖底层控制器力矩限幅与物理急停保障安全。", False, False, None),
    ])
    add_bullet(doc, "3. 缺少深度/力觉使 Z 轴桌面高度估计保守：", [
        ("如模型自己在 ", False, False, None),
        ("NOTES.md", False, True, BLUE),
        (" 中记录的 “table height still uncertain likely ~.88-.90”，纯 RGB 缺乏精确测距使得桌面附近操作偏保守，拉长了前期试探步数。", False, False, None),
    ])
    add_bullet(doc, "4. 对仿真器/硬件时序一致性高度敏感：", [
        ("当底层执行墙上耗时超过 Harness 固定等待窗口时，极易产生 ", False, False, None),
        ("stopped", False, True, BODY_INK),
        (" 假停顿，迫使模型花费大量 Token 与时间额外执行观测与等待。", False, False, None),
    ])

    # ------------------------------------------------------------------
    # Section 6 & 7: Next Steps & Environment Index
    # ------------------------------------------------------------------
    add_heading_1(doc, "6. 下一轮实验建议（gz_02 提速与多场景验证）")
    add_bullet(doc, "第一步：解除 Gazebo 软渲染与慢仿真瓶颈（最优先）：", [
        ("在容器内排查启用 WSLg GPU 硬件渲染（解决 ", False, False, None),
        ("ogre2.log", False, True, BLUE),
        (" 回退 ", False, False, None),
        ("llvmpipe", False, True, RED_DARK),
        (" 问题，如切换 Mesa ", False, False, None),
        ("d3d12", False, True, BODY_INK),
        (" / NVIDIA EGL 或采用 ", False, False, None),
        ("gui:=false", False, True, BODY_INK),
        (" 无头渲染配合网页 Live Viewer），并核查调整 ", False, False, None),
        ("table.sdf", False, True, BLUE),
        (" 中的 ", False, False, None),
        ("<real_time_update_rate>", False, True, BODY_INK),
        ("，将 RTF 恢复至接近 1.0× 实时后重跑 ", False, False, None),
        ("gz_02", True, True, BLUE),
        ("，验证完整抓取蓝方块的耗时与 Token 表现。", False, False, None),
    ])
    add_bullet(doc, "第二步：评估运动步幅与多步批处理策略：", [
        ("在纯仿真下对比 ", False, False, None),
        ("max_step_m: 0.05", False, True, BODY_INK),
        (" 与 ", False, False, None),
        ("0.08–0.10", False, True, BODY_INK),
        (" 及引导使用 ", False, False, None),
        ("robot_execute_plan", False, True, BODY_INK),
        ("，量化耗时与 Token 下降幅度。", False, False, None),
    ])
    add_bullet(doc, "第三步：横向评测复杂官方世界：", [
        ("在 1× 实时环境下继续评测 ", False, False, None),
        ("articulated_cabinet", False, True, BLUE),
        ("（开抽屉取物）与 ", False, False, None),
        ("pick_and_deliver", False, True, BLUE),
        ("（移动底盘跨房间抓放），全面检验长程多部件协同成功率。", False, False, None),
    ])

    add_heading_1(doc, "7. 复现环境与原始数据档案索引")
    add_styled_table(
        doc,
        headers=["类别", "详细规格 / 路径说明"],
        rows=[
            ["宿主机与硬件", "Windows 11 Pro (10.0.26200) | Intel Core i9-14900HX (24C/32T) | 32 GB RAM | RTX 5070 Laptop GPU (8 GB, 582.05)"],
            ["容器与 ROS 2 环境", "robotis/ai-worker:2.3.1 (ROS 2 Jazzy + Gazebo Harmonic + Cyclo MoveL + rmw_zenoh_cpp)"],
            ["Codex 与认证方式", "codex-cli 0.171.0 | 隔离配置目录 /root/.codex_robot | ChatGPT OAuth 授权"],
            ["WSL2 适配脚本", "configs/.wslconfig.example  |  configs/docker-compose.wsl.yml  |  configs/start_sim.sh"],
            ["原始实验档案 (gz_01)", "data/gz_01/ (含 result.json, gz01_metrics.json, rollout/, public/, NOTES.md)"],
            ["配套评估录像", "media/gz_01_full_replay.mp4（79.7 s / 1440×810 / H.264 / 2.61 MB）"],
        ],
        col_widths_cm=[3.8, 12.8],
        font_size=8.9,
    )

    # ------------------------------------------------------------------
    # Appendix: Milestone Execution Log Table
    # ------------------------------------------------------------------
    add_heading_1(doc, "附录：gz_01 关键工具调用全时序摘要（精选 15 个核心节点）")
    add_styled_table(
        doc,
        headers=["Call", "时刻", "工具名", "执行状态", "右臂末端 (base_link) & 仿真时间", "关键行为与系统观察"],
        rows=appendix_rows,
        col_widths_cm=[1.2, 1.3, 2.7, 2.0, 4.3, 5.1],
        header_bg="0F172A",
        font_size=8.3,
    )

    doc.save(OUT_DOCX)
    print(f"Successfully saved Word report: {OUT_DOCX} ({os.path.getsize(OUT_DOCX)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
