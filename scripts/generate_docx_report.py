#!/usr/bin/env python3
"""
Generate the v2.0 Word (.docx) evaluation report for gz_01 (CPU llvmpipe baseline)
vs gz_02 (RTX 5070 D3D12 accelerated full pickup), reading exact telemetry metrics
and milestone trajectories from both runs.
"""
import json
import os
from datetime import datetime

import docx
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GZ1_RUN_DIR = os.path.join(REPO_ROOT, "data", "gz_01")
GZ2_RUN_DIR = os.path.join(REPO_ROOT, "data", "gz_02")
GZ1_METRICS = os.path.join(GZ1_RUN_DIR, "gz01_metrics.json")
GZ2_METRICS = os.path.join(GZ2_RUN_DIR, "gz02_metrics.json")
OUT_DOCX = os.path.join(REPO_ROOT, "report", "gz_01_evaluation_report.docx")

IMG_GZ1_MILESTONES = os.path.join(REPO_ROOT, "assets", "gz_01_key_milestones.png")
IMG_GZ2_MILESTONES = os.path.join(REPO_ROOT, "assets", "gz_02_key_milestones.png")
IMG_ARCH           = os.path.join(REPO_ROOT, "assets", "gz_01_architecture_diagram.png")
IMG_GZ1_TELEMETRY  = os.path.join(REPO_ROOT, "assets", "gz_01_telemetry_charts.png")
IMG_AB_CHARTS      = os.path.join(REPO_ROOT, "assets", "gz_02_ab_comparison_charts.png")

VIDEO_GZ1_URL = "../media/gz_01_full_replay.mp4"
VIDEO_GZ2_URL = "../media/gz_02_full_replay.mp4"

NAVY     = RGBColor(15, 23, 42)
BLUE     = RGBColor(29, 78, 216)
TEAL     = RGBColor(4, 120, 87)
SLATE    = RGBColor(71, 85, 105)
BODY_INK = RGBColor(30, 41, 59)
MUTED    = RGBColor(100, 116, 139)
RED_DARK = RGBColor(185, 28, 28)
AMBER    = RGBColor(180, 83, 9)
WHITE    = RGBColor(255, 255, 255)


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


def set_cell_margins(cell, top=85, bottom=85, left=120, right=120):
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
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def repeat_header_row(row):
    row._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))


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
    for xml_str in [
        r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls("w"),
        r'<w:instrText %s xml:space="preserve"> PAGE </w:instrText>' % nsdecls("w"),
        r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls("w"),
        r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls("w"),
    ]:
        run._r.append(parse_xml(xml_str))


def add_numpages_fields(run):
    for xml_str in [
        r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls("w"),
        r'<w:instrText %s xml:space="preserve"> NUMPAGES </w:instrText>' % nsdecls("w"),
        r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls("w"),
        r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls("w"),
    ]:
        run._r.append(parse_xml(xml_str))


def add_callout(doc, title, paragraphs_spec, fill_hex="EFF6FF", accent_hex="2563EB", title_color=BLUE):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Cm(16.6)
    set_cell_shading(cell, fill_hex)
    set_cell_margins(cell, top=135, bottom=135, left=190, right=175)
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
        p.paragraph_format.line_spacing = 1.3
        for text, is_bold, is_code, col in segments:
            r = p.add_run(text)
            set_run_font(
                r,
                font_cn="微软雅黑",
                font_ascii="Consolas" if is_code else "Calibri",
                size_pt=9.5 if is_code else 10.0,
                bold=is_bold,
                color=col if col else BODY_INK,
            )

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(5)


def add_heading_1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    pPr = p._p.get_or_add_pPr()
    pPr.append(parse_xml(
        f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="10" w:space="4" w:color="1D4ED8"/></w:pBdr>'
    ))
    r = p.add_run(text)
    set_run_font(r, size_pt=14.2, bold=True, color=NAVY)
    return p


def add_heading_2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    set_run_font(r, size_pt=11.8, bold=True, color=BLUE)
    return p


def add_rich_paragraph(doc, segments, space_after=5):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
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
            size_pt=9.5 if code else 10.4,
            bold=bold,
            italic=italic,
            color=col,
        )
    return p


def add_code_block(doc, code_lines):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Cm(16.6)
    set_cell_shading(cell, "0F172A")
    set_cell_margins(cell, top=110, bottom=110, left=160, right=160)
    prevent_row_split(tbl.rows[0])
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.25
    r = p.add_run("\n".join(code_lines))
    set_run_font(r, font_cn="微软雅黑", font_ascii="Consolas", size_pt=9.2, color=RGBColor(226, 232, 240))
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)


def add_bullet(doc, lead_bold, body_segments, space_after=4):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.55)
    p.paragraph_format.first_line_indent = Cm(-0.35)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35

    r_dot = p.add_run("•  ")
    set_run_font(r_dot, size_pt=10.4, bold=True, color=BLUE)
    if lead_bold:
        r_lead = p.add_run(lead_bold)
        set_run_font(r_lead, size_pt=10.4, bold=True, color=NAVY)
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
            size_pt=9.5 if code else 10.4,
            bold=bold,
            italic=italic,
            color=col,
        )
    return p


def add_styled_table(doc, headers, rows, col_widths_cm, header_bg="1E3A8A", zebra_bg="F8FAFC", font_size=9.1):
    tbl = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    set_table_borders(tbl, border_color="CBD5E1", header_bottom_color=header_bg)

    hdr_row = tbl.rows[0]
    repeat_header_row(hdr_row)
    prevent_row_split(hdr_row)
    for ci, h_text in enumerate(headers):
        cell = hdr_row.cells[ci]
        cell.width = Cm(col_widths_cm[ci])
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_shading(cell, header_bg)
        set_cell_margins(cell, top=90, bottom=90, left=105, right=105)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(h_text)
        set_run_font(r, size_pt=font_size + 0.2, bold=True, color=WHITE)

    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri + 1]
        prevent_row_split(row)
        bg = zebra_bg if ri % 2 == 1 else "FFFFFF"
        for ci, cell_spec in enumerate(row_data):
            cell = row.cells[ci]
            cell.width = Cm(col_widths_cm[ci])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            set_cell_shading(cell, bg)
            set_cell_margins(cell, top=75, bottom=75, left=105, right=105)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.24
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
    set_run_font(r_cap, size_pt=9.1, color=SLATE)


def load_milestone_rows(run_dir, key_indices, notes_map):
    history = [json.loads(l) for l in open(os.path.join(run_dir, "public", "history.jsonl"), encoding="utf-8") if l.strip()]
    t0 = datetime.fromisoformat(history[0]["at"].replace("Z", "+00:00"))
    rows = []
    for idx in key_indices:
        h = history[idx - 1]
        dt = (datetime.fromisoformat(h["at"].replace("Z", "+00:00")) - t0).total_seconds()
        obs = h.get("observation")
        if obs:
            rx, ry, rz = obs["arms"]["right"]["xyz"]
            rg = obs["arms"]["right"]["gripper"]
            pose_str = f"({rx:+.3f},{ry:+.3f},{rz:+.3f})\ngrp={rg:.2f} sim={obs['stamp_s']:.1f}s"
        else:
            pose_str = "无新观测\n（完成声明或拦截）"
        st = h["status"]
        if st in ("observed", "arrived", "plan_completed", "completed"):
            st_color = TEAL
        elif st == "rejected":
            st_color = RED_DARK
        else:
            st_color = AMBER
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
    m1 = json.load(open(GZ1_METRICS, encoding="utf-8"))
    m2 = json.load(open(GZ2_METRICS, encoding="utf-8"))

    gz2_rows = load_milestone_rows(
        GZ2_RUN_DIR,
        [1, 2, 3, 4, 10, 11, 16, 24, 31, 33, 34, 35, 36, 37, 38],
        {
            1: "初始平视仅见白墙，开始观测",
            2: "一次 arrived 低头 0.695 rad 锁定蓝方块",
            3: "躯干一次到位降至 -0.35 m",
            4: "底盘试探无位移，立刻止损放弃",
            10: "多步批处理计划（4步）顺利推进至桌前",
            11: "二轮批处理（4步）快速跨桌缘抵达上方",
            16: "首次全闭 (1.0) 将方块挤滑，未幻觉误报",
            24: "二次全闭再次挤偏后主动追踪新坐标",
            31: "完成重定位，俯仰调至 -0.20 rad 准备下探",
            33: "垂直精准下探至抓取点 Z=0.852 m",
            34: "切换温和半闭策略：第一段收爪至 0.45",
            35: "第二段收爪至 0.68 稳稳咬合方块",
            36: "小步垂直提拉至 Z=0.875 m（方块离桌）",
            37: "续抬至 Z=0.900 m，投影明显分离",
            38: "结合 Obs #44 视觉确认悬空，成功结束任务！",
        },
    )

    gz1_rows = load_milestone_rows(
        GZ1_RUN_DIR,
        [1, 2, 5, 10, 11, 13, 22, 39, 46, 57],
        {
            1: "初始平视白墙，开始首次观测",
            2: "低头因慢仿真未到位报 stopped",
            5: "历经 3 次 observe + sleep 才看到方块",
            10: "步长 0.052m > 0.05m 被安全层拦截",
            11: "检测到 lift 漂移被拦截并要求重观",
            13: "躯干降至 -0.15m 到位 (唯一一次 arrived)",
            22: "试探底盘未动，笔记止损",
            39: "蓝色方块首次进入右腕相机边缘",
            46: "察觉桌缘摩擦，主动抬高至 Z=0.928m 脱困",
            57: "右爪跨悬方块上方时触达 5M 上限暂停",
        },
    )

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.different_first_page_header_footer = True

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.4)
    normal._element.get_or_add_rPr().insert(0, parse_xml(f'<w:rFonts {nsdecls("w")} w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="微软雅黑"/>'))

    hdr = section.header
    p_hdr = hdr.paragraphs[0]
    p_hdr.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r_hdr = p_hdr.add_run("GPT-6 Astra × ROBOTIS AI Worker (v2.0)  |  Windows 11 复现与 GPU 提速 A/B 研究评估报告")
    set_run_font(r_hdr, size_pt=8.5, color=MUTED)

    ftr = section.footer
    p_ftr = ftr.paragraphs[0]
    p_ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for txt, fn in [("第 ", None), ("", add_page_number_fields), (" 页 / 共 ", None), ("", add_numpages_fields), (" 页", None)]:
        rf = p_ftr.add_run(txt)
        set_run_font(rf, size_pt=8.5, color=MUTED)
        if fn:
            fn(rf)

    # ------------------------------------------------------------------
    # Title Banner Block
    # ------------------------------------------------------------------
    banner = doc.add_table(rows=1, cols=1)
    banner.alignment = WD_TABLE_ALIGNMENT.CENTER
    banner.autofit = False
    b_cell = banner.cell(0, 0)
    b_cell.width = Cm(16.6)
    set_cell_shading(b_cell, "0F172A")
    set_cell_margins(b_cell, top=210, bottom=210, left=230, right=230)
    prevent_row_split(banner.rows[0])

    bp1 = b_cell.paragraphs[0]
    bp1.paragraph_format.space_after = Pt(4)
    set_run_font(bp1.add_run("具身智能复现工程评估报告 (V2.0)  ·  GZ_01 基线 VS GZ_02 加速对照"), size_pt=9.5, bold=True, color=RGBColor(52, 211, 153))

    bp2 = b_cell.add_paragraph()
    bp2.paragraph_format.space_before = Pt(2)
    bp2.paragraph_format.space_after = Pt(6)
    set_run_font(bp2.add_run("GPT-6 Astra × ROBOTIS AI Worker\nWindows 11 端到端复现与 GPU 提速 A/B 实证评估"), size_pt=18.5, bold=True, color=WHITE)

    bp3 = b_cell.add_paragraph()
    bp3.paragraph_format.space_after = Pt(0)
    set_run_font(bp3.add_run("“大模型低频决策 × 机器人高频运控”架构解析 · 10.2× 提速实测 · 完整抓起蓝色方块录像与闭环验证"), size_pt=10.2, color=RGBColor(203, 213, 225))

    doc.add_paragraph().paragraph_format.space_after = Pt(5)

    # Metadata Card
    add_styled_table(
        doc,
        headers=["对照维度", "gz_01（CPU 软渲染基线）", "gz_02（RTX 5070 D3D12 加速版）"],
        rows=[
            ["任务指令与模型", [("\"pick up the blue block\" | gpt-6-astra (low)", False, True, BODY_INK)], [("\"pick up the blue block\" | gpt-6-astra (low) [控制变量一致]", False, True, NAVY)]],
            ["渲染后端", [("llvmpipe (LLVM 20.1.2, CPU)", False, True, RED_DARK)], [("D3D12 (NVIDIA GeForce RTX 5070 Laptop GPU)", True, True, TEAL)]],
            ["平均实时因子 (RTF)", [(f"{m1['avg_rtf']}× (慢动作 ~12×)", False, False, RED_DARK)], [(f"{m2['avg_rtf']}× (提速 10.2×)", True, False, TEAL)]],
            ["现实总耗时 / Token", [(f"{m1['elapsed_s_result']} s | {m1['tokens']['total']:,}", False, False, BODY_INK)], [(f"{m2['elapsed_s_result']} s (-50.9%) | {m2['tokens']['total']:,} (-59.3%)", True, False, TEAL)]],
            ["最终结局", [("halted:token_limit (悬停上方未闭合)", True, True, AMBER)], [("task_complete (成功抓起并悬空抬离桌面)", True, True, TEAL)]],
        ],
        col_widths_cm=[3.4, 6.4, 6.8],
        header_bg="1E293B",
        font_size=9.0,
    )

    add_callout(
        doc,
        title="核心结论：A/B 对照实证闭环（Executive Summary）",
        paragraphs_spec=[
            [
                ("1. 提速直击瓶颈，任务从暂停变为 100% 成功：", True, False, NAVY),
                ("在完全保持 ", False, False, None),
                ("gpt-6-astra (low)", False, True, BLUE),
                ("、", False, False, None),
                ("max_step_m=0.05", False, True, BLUE),
                (" 与桌面场景不变的前提下，通过 WSLg Mesa D3D12 启用 RTX 5070 硬件渲染，仿真 RTF 从 ", False, False, None),
                ("0.0821× 跃升至 0.8359×（10.2× 加速）", True, False, TEAL),
                ("，模型自主 ", False, False, None),
                ("sleep()", False, True, BODY_INK),
                (" 从 26 次（734.5s）彻底降为 ", False, False, None),
                ("0 次", True, False, TEAL),
                ("，单步一次到位 ", False, False, None),
                ("arrived", False, True, BODY_INK),
                (" 从 1 次激增至 ", False, False, None),
                ("26 次", True, False, TEAL),
                ("，总耗时腰斩（1242.4s → 610.1s）、Token 消耗直降 59.3%（5.02M → 2.04M），", False, False, None),
                ("最终稳稳夹起蓝色方块并举离桌面完成 task_complete！", True, False, TEAL),
            ],
            [
                ("2. 激发出高阶多步规划与容错纠偏能力：", True, False, NAVY),
                ("稳定高速的底层运控让模型得以主动调用 5 次 ", False, False, None),
                ("robot_execute_plan", False, True, BLUE),
                (" 批处理；在经历两次全闭失误将方块挤偏后，模型拒绝幻觉，主动追踪到新坐标并切换为", False, False, None),
                ("“两段式温和半闭（0.45 → 0.68）”", True, False, NAVY),
                ("成功抓起，充分证明“通用大模型低频决策 × 传统高频运控”在可靠性、可审计性与零样本泛化上的工程价值。", False, False, None),
            ],
        ],
        fill_hex="ECFDF5",
        accent_hex="059669",
        title_color=TEAL,
    )

    # ------------------------------------------------------------------
    # Section 1: Replay Videos & Milestone Visuals
    # ------------------------------------------------------------------
    add_heading_1(doc, "1. 双阶段完整过程回放视频与关键里程碑演进")
    add_heading_2(doc, "1.1 完整过程高清评估录像（点击直达）")
    add_rich_paragraph(doc, [
        ("本报告配套生成了两阶段完整过程的高清合成回放视频（1440×810 H.264 MP4），同屏呈现三路同步相机画面、大模型原始决策理由、", False, False, BODY_INK),
        ("robot_execute_plan", False, True, BLUE),
        (" / ", False, False, BODY_INK),
        ("sleep", False, True, BODY_INK),
        (" 状态以及底层 100 Hz 运控轨迹：", False, False, BODY_INK),
    ])

    for label, link_text, url, http_url in [
        ("•  gz_02 加速成功版录像（61.6 s，强烈推荐）：", "gz_02_full_replay.mp4（点击播放，1.81 MB）", VIDEO_GZ2_URL, "http://localhost:5500/ffw_codex/runs/gz_02/gz_02_full_replay.mp4"),
        ("•  gz_01 软渲染基线版录像（79.7 s）：", "gz_01_full_replay.mp4（点击播放，2.68 MB）", VIDEO_GZ1_URL, "http://localhost:5500/ffw_codex/runs/gz_01/gz_01_full_replay.mp4"),
    ]:
        pv = doc.add_paragraph()
        pv.paragraph_format.left_indent = Cm(0.5)
        pv.paragraph_format.first_line_indent = Cm(-0.3)
        pv.paragraph_format.space_after = Pt(3)
        set_run_font(pv.add_run(label), size_pt=10.1, bold=True, color=NAVY)
        add_hyperlink(pv, link_text, url, size_pt=10.1)
        set_run_font(pv.add_run("  |  浏览器入口："), size_pt=9.5, color=SLATE)
        add_hyperlink(pv, http_url, http_url, size_pt=9.2)

    add_heading_2(doc, "1.2 gz_02 六大关键里程碑演进（从抓滑失误到稳健抓起）")
    add_figure(
        doc,
        IMG_GZ2_MILESTONES,
        "图 1  gz_02 (RTX 5070 D3D12 加速) 六大关键阶段双视角演进：包含多步批处理抵近、两次全闭滑移重追与温和半闭成功举起",
        width_cm=16.4,
    )

    add_heading_2(doc, "1.3 gz_01 六大关键里程碑演进（基线对比参考）")
    add_figure(
        doc,
        IMG_GZ1_MILESTONES,
        "图 2  gz_01 (CPU llvmpipe 基线) 六大关键阶段双视角演进：最终夹爪悬停蓝方块正上方时触达 5M Token 上限",
        width_cm=16.4,
    )

    # ------------------------------------------------------------------
    # Section 2: Architecture
    # ------------------------------------------------------------------
    add_heading_1(doc, "2. 系统架构剖析：“大模型低频决策 × 机器人高频运控”")
    add_rich_paragraph(doc, [
        ("该架构将", False, False, BODY_INK),
        ("开放世界语义规划", True, False, NAVY),
        ("与", False, False, BODY_INK),
        ("确定性高频运动控制", True, False, NAVY),
        ("彻底解耦，中间由 ", False, False, BODY_INK),
        ("Harness 校验守卫层", True, False, TEAL),
        (" 把控参数限幅、观测新鲜度与多路相机时间同步：", False, False, BODY_INK),
    ])
    add_figure(
        doc,
        IMG_ARCH,
        "图 3  “大模型低频决策 × 机器人高频运控”三层解耦闭环架构与实测参数标注",
        width_cm=16.4,
    )

    add_styled_table(
        doc,
        headers=["系统层级", "核心组件与源码配置文件", "运行频率 / 同步指标", "等效周期", "职责边界"],
        rows=[
            ["物理动力学层", [("Gazebo Harmonic\n", True, False, NAVY), ("table.sdf: max_step_size=0.001", False, True, SLATE)], [("1000 Hz", True, False, BLUE)], "1.0 ms", "刚体动力学积分、接触碰撞与摩擦"],
            ["关节伺服环", [("ros2_control controller_manager\n", True, False, NAVY), ("update_rate: 100", False, True, SLATE)], [("100 Hz", True, False, BLUE)], "10.0 ms", "双臂、头部、升降、底盘 6 组控制器追踪"],
            ["笛卡尔规划层", [("Cyclo MoveL 控制器\n", True, False, NAVY), ("control_frequency: 100.0", False, True, SLATE)], [("100 Hz", True, False, BLUE)], "10.0 ms", "末端直线插补、IK 逆解与自碰撞防护"],
            ["移动底盘层", [("底盘速度控制\n", True, False, NAVY), ("base.publish_hz: 20.0", False, True, SLATE)], [("20 Hz", True, False, TEAL)], "50.0 ms", "/cmd_vel 斜坡加减速与静止判定"],
            ["多传感器同步", [("Harness 观测守卫\n", True, False, NAVY), ("snapshot_tolerance_s: 0.015", False, True, SLATE)], [("同步窗 ≤ 15 ms", True, False, TEAL)], f"gz_01 {m1['sync_mean_ms']}ms\ngz_02 {m2['sync_mean_ms']}ms", "3路 RGB 与 /joint_states、/odom 时间戳对齐（最大 ≤ 5.0 ms）"],
            ["大模型决策\n(gz_02 加速后)", [("GPT-6 Astra (0 sleep)\n", True, False, NAVY), ("38 次调用 / 43 物理动作", False, False, SLATE)], [("0.062 Hz", True, False, TEAL)], "调用 15.8 s/次\n(纯思考 8.69 s)", "低频视觉规划、批处理动作与容错纠偏"],
            ["大模型决策\n(gz_01 基线)", [("含 26 次慢仿真 sleep\n", True, False, NAVY), ("57 次调用 / 27 物理动作", False, False, SLATE)], [("0.046 Hz\n(动作 0.022 Hz)", True, False, RED_DARK)], "调用 21.8 s/次\n(动作 46.0 s/次)", "比底层 100 Hz 运控低 ~1,600× 至 ~4,600×"],
        ],
        col_widths_cm=[2.6, 5.0, 2.5, 2.7, 3.8],
        font_size=8.8,
    )

    # ------------------------------------------------------------------
    # Section 3: A/B Comparison & Bottleneck Diagnosis
    # ------------------------------------------------------------------
    add_heading_1(doc, "3. 量化遥测与 gz_01 vs gz_02 A/B 对照实证")
    add_figure(
        doc,
        IMG_AB_CHARTS,
        "图 4  gz_01 (CPU 软渲染) vs gz_02 (RTX 5070 D3D12) A/B 对照四联图：(A) 耗时三元拆解；(B) 核心指标对比；(C) gz_02 抓取全轨迹；(D) 耗时 vs Token 曲线",
        width_cm=16.4,
    )

    add_heading_2(doc, "3.1 全维度 A/B 指标对照表")
    add_styled_table(
        doc,
        headers=["评估维度", "gz_01（优化前：llvmpipe）", "gz_02（优化后：RTX 5070 D3D12）", "对比结论"],
        rows=[
            ["任务结局", "halted:token_limit（未抓起）", [("task_complete（成功抓起并抬起）", True, False, TEAL)], "0% → 100% 闭环"],
            ["平均实时因子 (RTF)", f"{m1['avg_rtf']}×（sim {m1['sim_span_s']}s / {m1['wall_span_calls_s']}s）", [(f"{m2['avg_rtf']}×（sim {m2['sim_span_s']}s / {m2['wall_span_calls_s']}s）", True, False, TEAL)], "10.2× 提速"],
            ["现实总耗时 (elapsed_s)", f"{m1['elapsed_s_result']} s（20分42秒）", [(f"{m2['elapsed_s_result']} s（10分10秒）", True, False, TEAL)], "-50.9%（腰斩）"],
            ["模型自主 sleep()", f"{m1['sleep_count']} 次 / {m1['total_sleep_s']}s（{m1['sleep_pct']}%）", [("0 次 / 0.00s（0.0%）", True, False, TEAL)], "彻底消除"],
            ["冗余 robot_observe", f"{m1['tool_counts']['robot_observe']} 次", [("0 次", True, False, TEAL)], "彻底消除"],
            ["LLM 思考 + API 往返", f"{m1['total_llm_s']}s（{m1['llm_pct']}%，均值 {m1['llm_mean_s']}s）", f"{m2['total_llm_s']}s（{m2['llm_pct']}%，均值 {m2['llm_mean_s']}s）", "单次延迟一致"],
            ["Harness + 物理运控", f"{m1['total_tool_s']}s（{m1['tool_pct']}%）", f"{m2['total_tool_s']}s（{m2['tool_pct']}%）", "算力真正花在运动上"],
            ["调用数 / 物理动作数", f"{m1['total_calls']} 调用 / {m1['actions_executed']} 动作", [(f"{m2['total_calls']} 调用 / {m2['actions_executed']} 动作（含5次批处理）", True, False, BLUE)], "少33%调用 多59%动作"],
            ["单步一次到位 arrived", "1 次（另有 26 次 stopped）", [("26 次（另有 2 次 plan_completed）", True, False, TEAL)], "26× 提升"],
            ["Token 总量（缓存命中）", f"{m1['tokens']['total']:,}（{m1['cache_hit_pct']}%）", [(f"{m2['tokens']['total']:,}（{m2['cache_hit_pct']}%）", True, False, TEAL)], "-59.3%"],
            ["API 等效成本估算", f"${m1['cost_usd_estimate']:.3f}", [(f"${m2['cost_usd_estimate']:.3f}", True, False, TEAL)], "-50.5%"],
        ],
        col_widths_cm=[3.4, 4.5, 5.2, 3.5],
        font_size=8.8,
    )

    add_heading_2(doc, "3.2 慢仿真根因实证与 RTX 5070 D3D12 提速方法")
    add_rich_paragraph(doc, [
        ("在 ", False, False, BODY_INK),
        ("gz_01", False, True, BLUE),
        (" 完成后，检查容器内 ", False, False, BODY_INK),
        ("/root/.gz/rendering/ogre2.log", False, True, BLUE),
        (" 实证定位到慢仿真真凶：Ogre2 回退使用了 CPU 软渲染 ", False, False, BODY_INK),
        ("GL_RENDERER = llvmpipe (LLVM 20.1.2, 256 bits)", True, True, RED_DARK),
        (" 与 ", False, False, BODY_INK),
        ("EGL_MESA_device_software", False, True, BODY_INK),
        ("（", False, False, BODY_INK),
        ("gz sim server", False, True, BODY_INK),
        (" 占 217% CPU、", False, False, BODY_INK),
        ("gz sim gui", False, True, BODY_INK),
        (" 占 201% CPU）。通过在 ", False, False, BODY_INK),
        ("start_sim.sh", False, True, BLUE),
        (" 中显式注入 WSL 2 Mesa D3D12 环境变量（完整保留 Gazebo 3D 窗口，无需修改上游模型或世界文件）：", False, False, BODY_INK),
    ])
    add_code_block(doc, [
        "export LD_LIBRARY_PATH=\"/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}\"",
        "export GALLIUM_DRIVER=d3d12",
        "export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA",
    ])
    add_rich_paragraph(doc, [
        ("重启仿真后，", False, False, BODY_INK),
        ("ogre2.log", False, True, BLUE),
        (" 立即切换为 ", False, False, BODY_INK),
        ("GL_RENDERER = D3D12 (NVIDIA GeForce RTX 5070 Laptop GPU)", True, True, TEAL),
        ("，5 秒窗口实测 RTF 飙升至 ", False, False, BODY_INK),
        ("0.8916×", True, False, TEAL),
        ("（全流程平均 ", False, False, None),
        ("0.8359×", True, False, TEAL),
        ("），彻底释放了上层大模型的操作效能。", False, False, BODY_INK),
    ])

    add_heading_2(doc, "3.3 gz_01 基线遥测与耗时拆解（归档参考）")
    add_figure(
        doc,
        IMG_GZ1_TELEMETRY,
        "图 5  gz_01 基线单轮遥测与每步耗时构成（供与图 4 对照分析）",
        width_cm=16.4,
    )

    # ------------------------------------------------------------------
    # Section 4: Emergent Behaviors Across gz_01 & gz_02
    # ------------------------------------------------------------------
    add_heading_1(doc, "4. 具身智能涌现行为深度观察（研究亮点）")
    add_bullet(doc, "1. 主动视觉搜索与全身协同：", [
        ("两次实验都在 Call #02 自主低头 ", False, False, None),
        ("robot_head(0.695 rad)", False, True, BLUE),
        (" 锁定桌面，再通过 ", False, False, None),
        ("robot_lift", False, True, BODY_INK),
        ("（", False, False, None),
        ("gz_01", False, True, BODY_INK),
        (" -0.15m，", False, False, None),
        ("gz_02", False, True, BODY_INK),
        (" -0.35m）扩展前向工作空间。", False, False, None),
    ])
    add_bullet(doc, "2. 高阶多步批处理能力激活（robot_execute_plan）：", [
        ("在 ", False, False, None),
        ("gz_02", False, True, BLUE),
        (" 高实时性下，模型主动调用 5 次 ", False, False, None),
        ("robot_execute_plan", False, True, BLUE),
        ("（Call #10、#11 一次完成 8 个连续空间逼近点），用 38 次决策执行了 43 个物理动作，显著摊薄多图推理开销。", False, False, None),
    ])
    add_bullet(doc, "3. 两次抓滑失误后的拒绝幻觉与主动重追（gz_02 核心亮点）：", [
        ("Call #16 与 Call #24 全闭夹爪（", False, False, None),
        ("gripper=1.0", False, True, BODY_INK),
        ("）连续两次将蓝色方块挤偏（", False, False, None),
        ("y: -0.23 → -0.12 → +0.01", False, True, BODY_INK),
        ("）。模型没有产生任何“已完成”幻觉，而是对照腕部与头部图像诚实判定未抓到，持续追物重定位至 ", False, False, None),
        ("(0.536, +0.010, +0.852)", False, True, BLUE),
        ("。", False, False, None),
    ])
    add_bullet(doc, "4. 抓取策略自主切换（全闭失败 → 温和两段式半闭）：", [
        ("经历两次全闭滑移后，模型调整腕部俯仰 ", False, False, None),
        ("-0.20 rad", False, True, BODY_INK),
        ("，在 Call #34–#35 改为先收至 ", False, False, None),
        ("0.45", True, True, TEAL),
        (" 再渐进合拢至 ", False, False, None),
        ("0.70", True, True, TEAL),
        ("（在 ", False, False, None),
        ("0.676", False, True, BODY_INK),
        (" 咬合），随后分两步稳稳举升至 ", False, False, None),
        ("z=0.900 m", True, True, TEAL),
        ("。", False, False, None),
    ])
    add_bullet(doc, "5. 零深度纯 RGB 像素视差定位与在线笔记（NOTES.md）：", [
        ("模型在沙盒中自主记录了物体像素尺寸估计（约 85px / 6cm 立方体）、滑移复盘与成功判据。以下为 ", False, False, None),
        ("gz_02/agent/notes/NOTES.md", False, True, BLUE),
        (" 原文摘录：", False, False, None),
    ])
    add_callout(
        doc,
        title="gz_02 模型自建工作记忆原文摘录（agent/notes/NOTES.md）",
        paragraphs_spec=[
            [("\"Two full-close attempts displaced cube and changed scene relative robot; no grasp claimed. Third approach at EE (.536,.010,.851), rpy (.0331,-.20,-.0021), partial close .45 then .7. Gripper stopped initially .676; cube remained bracketed. Two small lifts to measured z .8751 then .9003 show blue cube suspended below fingers with visible separation above table and shadow. Cube rotated during lift; held near finger ends. Latest observation 44 is pickup evidence.\"", False, True, SLATE)],
        ],
        fill_hex="F8FAFC",
        accent_hex="64748B",
        title_color=NAVY,
    )

    # ------------------------------------------------------------------
    # Section 5 & 6: Paradigm Evaluation & Next Steps
    # ------------------------------------------------------------------
    add_heading_1(doc, "5. 研究范式综合评估与端到端 VLA 路线对比")
    add_styled_table(
        doc,
        headers=["评估维度", "本路线：通用大模型低频决策 + 工具契约 + 高频运控", "端到端 VLA 路线（RT-2 / OpenVLA / π0 等）"],
        rows=[
            ["零样本泛化与异常恢复", [("极强：", True, False, TEAL), ("抓滑重追、策略切换、跨视角视差估计、在线笔记", False, False, BODY_INK)], "依赖示教分布覆盖面，长程异常恢复较弱"],
            ["数据与训练门槛", [("几乎为零：", True, False, TEAL), ("仅需定义清晰的工具契约与安全 Harness", False, False, BODY_INK)], "需要大规模高质量遥操作轨迹采集与微调"],
            ["闭环频率与实时性", [("低（gz_02 ~0.06–0.12 Hz）：", True, False, AMBER), ("受限于云端 API 与多图推理耗时", False, False, BODY_INK)], "中高（5–50 Hz），本地 GPU 支持高频伺服"],
            ["安全与可审计性", [("高：", True, False, TEAL), ("显式语言理由 + 硬限幅校验 + 传统底层安全兜底", False, False, BODY_INK)], "黑盒连续输出，安全边界较难形式化审计"],
            ["单任务推理成本", "中等（gz_02 完整抓起耗 2.04M Token / 约 $3.12，缓存 96.3%）", "单次前向推理固定，长期部署边际成本低"],
        ],
        col_widths_cm=[3.2, 6.9, 6.5],
        font_size=8.9,
    )

    add_heading_1(doc, "6. 后续拓展实验建议")
    add_bullet(doc, "1. 复杂多步骤官方场景评测：", [
        ("在当前 RTX 5070 D3D12 加速环境下，继续测试 ", False, False, None),
        ("articulated_cabinet", False, True, BLUE),
        ("（开抽屉取物）与 ", False, False, None),
        ("pick_and_deliver", False, True, BLUE),
        ("（底盘移动跨房间搬运），评估长程多部件协调成功率。", False, False, None),
    ])
    add_bullet(doc, "2. 步幅与批处理策略消融：", [
        ("对比 ", False, False, None),
        ("max_step_m = 0.05", False, True, BODY_INK),
        (" 与 ", False, False, None),
        ("0.08–0.10", False, True, BODY_INK),
        (" 在复杂场景下的 Token 降幅与碰撞安全权衡。", False, False, None),
    ])

    # ------------------------------------------------------------------
    # Section 7: Environment & Appendix Tables
    # ------------------------------------------------------------------
    add_heading_1(doc, "7. 复现环境与双阶段档案索引")
    add_styled_table(
        doc,
        headers=["类别", "详细规格 / 路径说明"],
        rows=[
            ["宿主机与硬件", "Windows 11 Pro (10.0.26200) | Intel Core i9-14900HX (24C/32T) | 32 GB RAM | RTX 5070 Laptop GPU (8 GB, 582.05)"],
            ["容器与 ROS 2 环境", "robotis/ai-worker:2.3.1 (ROS 2 Jazzy + Gazebo Harmonic + Cyclo MoveL + rmw_zenoh_cpp)"],
            ["Codex 与认证", "codex-cli 0.171.0 | 隔离目录 /root/.codex_robot | ChatGPT OAuth"],
            ["gz_02 档案（加速成功）", "data/gz_02/ (result.json, gz02_metrics.json, rollout/, public/, NOTES.md) | media/gz_02_full_replay.mp4"],
            ["gz_01 档案（基线对比）", "data/gz_01/ (result.json, gz01_metrics.json, rollout/, public/, NOTES.md) | media/gz_01_full_replay.mp4"],
        ],
        col_widths_cm=[3.8, 12.8],
        font_size=8.8,
    )

    add_heading_1(doc, "附录 A：gz_02（RTX 5070 加速成功版）关键节点实测轨迹摘要")
    add_styled_table(
        doc,
        headers=["Call", "时刻", "工具名", "状态", "右臂末端 & 爪/仿真时间", "关键行为与演进说明"],
        rows=gz2_rows,
        col_widths_cm=[1.1, 1.3, 2.9, 2.2, 4.1, 5.0],
        header_bg="065F46",
        font_size=8.2,
    )

    add_heading_1(doc, "附录 B：gz_01（CPU 软渲染基线版）关键节点对比摘要")
    add_styled_table(
        doc,
        headers=["Call", "时刻", "工具名", "状态", "右臂末端 & 爪/仿真时间", "关键行为与演进说明"],
        rows=gz1_rows,
        col_widths_cm=[1.1, 1.3, 2.9, 2.2, 4.1, 5.0],
        header_bg="1E293B",
        font_size=8.2,
    )

    doc.save(OUT_DOCX)
    print(f"Successfully saved v2.0 Word report: {OUT_DOCX} ({os.path.getsize(OUT_DOCX)/1024:.1f} KB)")


if __name__ == "__main__":
    main()
