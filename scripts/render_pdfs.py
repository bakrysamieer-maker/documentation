#!/usr/bin/env python3
"""Layer 4 (part 2): render supplier profile PDFs and the batch summary.

Usage:
    python3 scripts/render_pdfs.py runs/batch-01

Reads 1-discovery.json, 2-vetting.json, 3-deep-dive.json and 4-report.json from the run folder
and writes the PDFs to <run>/reports/:
    00-batch-summary.pdf            overview, ranked tables, rejected suppliers
    <batch>-full-report.pdf         the summary followed by every profile (with bookmarks)
    garment/NN-ID-name.pdf          one profile per confirmed garment factory
    fabric/NN-ID-name.pdf           one profile per confirmed fabric mill
"""
import argparse
import json
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

INK = colors.HexColor('#1F2933')
MUTED = colors.HexColor('#5B6675')
FAINT = colors.HexColor('#8A94A6')
ACCENT = colors.HexColor('#0B6E4F')
LIGHT = colors.HexColor('#EEF2F5')
BORDER = colors.HexColor('#D5DCE3')
LINK = '#1D4ED8'

REC_LABEL = {'shortlist': 'SHORTLIST', 'consider': 'CONSIDER', 'low_priority': 'LOW PRIORITY'}
REC_COLOR = {'shortlist': ACCENT, 'consider': colors.HexColor('#B7791F'), 'low_priority': colors.HexColor('#9B2C2C')}
KSA_COLOR = {'strong': '#0B6E4F', 'moderate': '#B7791F', 'weak': '#9B2C2C', 'unknown': '#5B6675'}
SEGMENT_LABEL = {'garment': 'Garment factory', 'fabric': 'Woven fabric mill'}
SEGMENT_TITLE = {'garment': 'Garment factories', 'fabric': 'Woven fabric mills'}
REASON_LABEL = {
    'TRADING_COMPANY': 'trading company',
    'NO_FACTORY_EVIDENCE': 'no own-factory evidence',
    'KNIT_SPECIALIST': 'knitting specialist',
    'NOT_CLOTHING': 'not clothing',
    'NOT_WOVEN': 'not woven',
    'QUALITY_BAR_NOT_MET': 'below quality bar',
    'TOO_NEW': 'too new (< 3 years)',
    'DUPLICATE': 'duplicate',
    'INSUFFICIENT_INFO': 'not enough information',
}
SCORE_ROWS = [('factory', 'Own factory', 30), ('quality', 'Quality', 25), ('ksa_export', 'KSA export', 25),
              ('scale', 'Scale', 10), ('contactability', 'Contactability', 10)]

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
CJK_RUN = re.compile(r'[⺀-⿿　-〿぀-ヿ㐀-䶿一-鿿豈-﫿＀-￯]+')

FONTS = {}


def register_fonts():
    """Embed DejaVu for Latin text and WenQuanYi for Chinese; fall back to built-in fonts."""
    candidates = {
        'Body': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'Body-Bold': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        'CJK': '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    }
    for name, path in candidates.items():
        if Path(path).exists():
            options = {'subfontIndex': 0} if path.endswith('.ttc') else {}
            pdfmetrics.registerFont(TTFont(name, path, **options))
            FONTS[name] = name
    FONTS.setdefault('Body', 'Helvetica')
    FONTS.setdefault('Body-Bold', 'Helvetica-Bold')
    if 'CJK' not in FONTS:
        pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        FONTS['CJK'] = 'STSong-Light'
    if FONTS['Body'] == 'Body':
        for bold, italic, face in [(0, 0, 'Body'), (1, 0, 'Body-Bold'), (0, 1, 'Body'), (1, 1, 'Body-Bold')]:
            addMapping('Body', bold, italic, face)


def make_styles():
    body, bold = FONTS['Body'], FONTS['Body-Bold']
    base = dict(fontName=body, fontSize=8.8, leading=11.8, textColor=INK, splitLongWords=1)

    def style(name, **overrides):
        return ParagraphStyle(name, **{**base, **overrides})

    return {
        'body': style('body'),
        'small': style('small', fontSize=7.6, leading=10, textColor=MUTED),
        'cell': style('cell', fontSize=8, leading=10.4),
        'cell_bold': style('cell_bold', fontName=bold, fontSize=8, leading=10.4),
        'label': style('label', fontName=bold, fontSize=7.8, leading=10.2, textColor=MUTED),
        'title': style('title', fontName=bold, fontSize=18, leading=23),
        'h1': style('h1', fontName=bold, fontSize=15, leading=19, spaceAfter=1),
        'h1_cn': style('h1_cn', fontSize=11, leading=15, textColor=MUTED),
        'h2': style('h2', fontName=bold, fontSize=10.5, leading=14, textColor=ACCENT, spaceBefore=9, spaceAfter=3),
        'badge': style('badge', fontName=bold, fontSize=8.5, leading=11, textColor=colors.white, alignment=TA_CENTER),
        'badge_big': style('badge_big', fontName=bold, fontSize=15, leading=18, textColor=colors.white, alignment=TA_CENTER),
    }


# ---------- text helpers ----------

NOT_FOUND = f'<font color="{FAINT.hexval().replace("0x", "#")}">not found</font>'


def rich(text):
    """Escape text for a Paragraph and switch Chinese runs to the CJK font."""
    if text is None:
        return ''
    return CJK_RUN.sub(lambda m: f'<font name="{FONTS["CJK"]}">{m.group(0)}</font>', escape(str(text)))


def value(x):
    if x is None or x == '' or x == []:
        return NOT_FOUND
    if isinstance(x, bool):
        return 'yes' if x else 'no'
    if isinstance(x, list):
        return '<br/>'.join(rich(item) for item in x)
    return rich(x)


def short_url(url, limit=72):
    text = re.sub(r'^https?://(www\.)?', '', url or '').rstrip('/')
    return text if len(text) <= limit else text[:limit - 1] + '…'


def link(url, text=None):
    if not url:
        return NOT_FOUND
    target = url if re.match(r'^(https?://|mailto:|#)', url) else f'https://{url}'
    href = escape(target, {'"': '&quot;'})
    return f'<a href="{href}" color="{LINK}">{rich(text or short_url(url))}</a>'


def slug(text, limit=48):
    s = re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')
    return s[:limit].rstrip('-') or 'supplier'


def colored(text, hex_color, bold=False):
    inner = f'<b>{rich(text)}</b>' if bold else rich(text)
    return f'<font color="{hex_color}">{inner}</font>'


# ---------- flowables ----------

class Bar(Flowable):
    """A small horizontal score bar."""

    def __init__(self, score, maximum, width=52 * mm, height=3.4 * mm):
        super().__init__()
        self.score, self.maximum, self.width, self.height = score or 0, maximum, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(LIGHT)
        c.roundRect(0, 0, self.width, self.height, 1.4, stroke=0, fill=1)
        filled = self.width * max(0.0, min(1.0, self.score / self.maximum))
        if filled > 0:
            c.setFillColor(ACCENT)
            c.roundRect(0, 0, filled, self.height, 1.4, stroke=0, fill=1)


class Bookmark(Flowable):
    """Adds a PDF outline entry at its position (used in the combined report)."""

    def __init__(self, title, key, level=0):
        super().__init__()
        self.title, self.key, self.level = title, key, level

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=self.level, closed=False)


def kv_table(rows, st, label_width=38 * mm):
    """Two-column label/value table. Rows are (label, html_value) pairs."""
    data = [[Paragraph(rich(label), st['label']), Paragraph(html, st['cell'])] for label, html in rows]
    table = Table(data, colWidths=[label_width, CONTENT_W - label_width])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.4, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
    ]))
    return table


def grid_table(header, rows, widths, st, header_bg=ACCENT):
    data = [[Paragraph(f'<font color="white"><b>{rich(h)}</b></font>', st['cell']) for h in header]]
    data += [[cell if isinstance(cell, Flowable) else Paragraph(cell, st['cell']) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.3, BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return table


def section(title, st):
    """A section heading that starts a new page when less than 25 mm is left, so it never sits alone."""
    return [CondPageBreak(25 * mm), Paragraph(rich(title), st['h2'])]


# ---------- data loading ----------

def load_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def load_run(run_dir):
    discovery = load_json(run_dir / '1-discovery.json', {})
    vetting = load_json(run_dir / '2-vetting.json', [])
    deep = load_json(run_dir / '3-deep-dive.json', [])
    report = load_json(run_dir / '4-report.json', None)
    meta = load_json(run_dir / 'run.json', {})
    return discovery, vetting, deep, report, meta


def rank_profiles(deep, report):
    """Confirmed profiles per segment, in rank order, each paired with its ranking entry."""
    confirmed = [p for p in deep if p.get('final_verdict') == 'CONFIRMED']
    rankings = {r['id']: r for r in (report or {}).get('rankings', [])}
    ranked = {}
    for segment in ('garment', 'fabric'):
        items = []
        for p in confirmed:
            if p['segment'] != segment:
                continue
            entry = rankings.get(p['id'])
            if entry is None:
                entry = {'id': p['id'], 'rank': None, 'final_score': sum(p['scores'].values()),
                         'adjustment_note': None, 'one_line': ''}
            items.append((p, entry))
        items.sort(key=lambda pe: (pe[1]['rank'] is None, pe[1]['rank'] or 0, -pe[1]['final_score'],
                                   -pe[0]['scores']['ksa_export'], -pe[0]['scores']['factory']))
        for i, (p, entry) in enumerate(items, start=1):
            entry['rank'] = i
        ranked[segment] = items
    return ranked


def merged_contacts(profile, vet):
    """Layer 3 contacts first, then any extra ones Layer 2 saw, without duplicates."""
    merged = {}
    sources = [profile.get('contacts') or {}, (vet or {}).get('contacts') or {}]
    for kind in ('emails', 'phones', 'wechat', 'whatsapp', 'linkedin'):
        seen, items = set(), []
        for contacts in sources:
            for c in contacts.get(kind) or []:
                key = re.sub(r'[\s\-+()]', '', str(c.get('value', '')).lower())
                if key and key not in seen:
                    seen.add(key)
                    items.append(c)
        merged[kind] = items
    merged['website'] = next((c.get('website') for c in sources if c.get('website')), None)
    merged['b2b_profiles'] = list(dict.fromkeys(u for c in sources for u in (c.get('b2b_profiles') or [])))
    people, seen = [], set()
    for contacts in sources:
        for person in contacts.get('people') or []:
            key = (person.get('name', '').lower(), person.get('title', '').lower())
            if key not in seen:
                seen.add(key)
                people.append(person)
    merged['people'] = people
    return merged


# ---------- profile ----------

def place(p):
    loc = p.get('location') or {}
    return ', '.join(x for x in [loc.get('city'), loc.get('province')] if x)


def profile_story(p, entry, vet, cand, st, segment_size, batch_label, outline_level=0):
    story = [Bookmark(f"{p['id']} · {p['name_en']}", key=f"profile-{p['id']}", level=outline_level)]
    rec = p.get('recommendation', 'consider')
    total = entry.get('final_score', sum(p['scores'].values()))

    left = [Paragraph(rich(p['name_en']), st['h1'])]
    if p.get('name_cn'):
        left.append(Paragraph(rich(p['name_cn']), st['h1_cn']))
    established = (p.get('registry') or {}).get('established')
    meta_bits = [SEGMENT_LABEL.get(p['segment'], p['segment']), place(p), f'est. {established}' if established else None,
                 f"ID {p['id']}"]
    left.append(Paragraph(rich(' · '.join(b for b in meta_bits if b)), st['small']))
    badge = Table([[Paragraph(REC_LABEL.get(rec, rec.upper()), st['badge'])], [Paragraph(f'{total}/100', st['badge_big'])]],
                  colWidths=[34 * mm])
    badge.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), REC_COLOR.get(rec, MUTED)),
                               ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    header = Table([[left, badge]], colWidths=[CONTENT_W - 36 * mm, 36 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                ('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
    story += [header, Spacer(1, 5)]

    rank_line = f"Rank {entry['rank']} of {segment_size} {SEGMENT_TITLE[p['segment']].lower()} in {batch_label}"
    if entry.get('one_line'):
        rank_line += f" — {entry['one_line']}"
    story.append(Paragraph(f'<b>{rich(rank_line)}</b>', st['body']))
    story.append(Spacer(1, 3))
    story.append(Paragraph(rich(p.get('summary')), st['body']))

    # Scores
    story += section('Scores', st)
    score_rows = [[Paragraph(rich(label), st['cell']), Bar(p['scores'].get(key, 0), maximum),
                   Paragraph(f"<b>{p['scores'].get(key, 0)}</b> / {maximum}", st['cell'])]
                  for key, label, maximum in SCORE_ROWS]
    score_rows.append([Paragraph('<b>Total</b>', st['cell']), Bar(total, 100),
                       Paragraph(f'<b>{total}</b> / 100', st['cell'])])
    scores = Table(score_rows, colWidths=[32 * mm, 58 * mm, 24 * mm], hAlign='LEFT')
    scores.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 1.5),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5), ('LEFTPADDING', (0, 0), (-1, -1), 2)]))
    story.append(scores)
    if entry.get('adjustment_note'):
        story.append(Paragraph(f"Score adjusted by the batch editor: {rich(entry['adjustment_note'])}", st['small']))

    # Strengths and risks
    strengths = '<br/>'.join(f'+ {rich(s)}' for s in p.get('strengths') or []) or NOT_FOUND
    risks = '<br/>'.join(f'– {rich(r)}' for r in p.get('risks') or []) or 'none found'
    sr = Table([[Paragraph('<b>Strengths</b>', st['cell']), Paragraph('<b>Risks</b>', st['cell'])],
                [Paragraph(strengths, st['cell']), Paragraph(risks, st['cell'])]],
               colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    sr.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
                            ('LINEBELOW', (0, 0), (-1, 0), 0.4, BORDER)]))
    story += [Spacer(1, 6), sr]

    # Contacts
    contacts = merged_contacts(p, vet)
    story += section('Contacts', st)
    contact_rows = []
    for kind, label in [('emails', 'Email'), ('phones', 'Phone'), ('wechat', 'WeChat'), ('whatsapp', 'WhatsApp'),
                        ('linkedin', 'LinkedIn')]:
        for c in contacts[kind]:
            shown = link(c['value'], c['value']) if kind == 'linkedin' else rich(c['value'])
            contact_rows.append([rich(label), shown, rich(c.get('label')), link(c.get('source_url'), 'source')])
    for person in contacts['people']:
        contact_rows.append(['Person', rich(person.get('name')), rich(person.get('title')),
                             link(person.get('source_url'), 'source')])
    if contact_rows:
        story.append(grid_table(['Type', 'Contact', 'Note', 'Found on'], contact_rows,
                                [22 * mm, 68 * mm, CONTENT_W - 112 * mm, 22 * mm], st))
    else:
        story.append(Paragraph('No direct contacts found. Use the website or B2B profiles below.', st['body']))
    story.append(Spacer(1, 3))
    story.append(kv_table([
        ('Website', link(contacts['website'])),
        ('B2B profiles', '<br/>'.join(link(u) for u in contacts['b2b_profiles']) or NOT_FOUND),
    ], st))

    # Canton Fair evidence
    cf = (cand or {}).get('canton_fair') or {}
    story += section('Canton Fair evidence (from public sources)', st)
    story.append(kv_table([
        ('Evidence strength', value(cf.get('strength'))),
        ('Session', value(cf.get('session'))),
        ('Booth', value(cf.get('booth'))),
        ('What the source says', value(cf.get('evidence_note'))),
        ('Source', link(cf.get('evidence_url'))),
    ], st))

    # Company and registry
    reg = p.get('registry') or {}
    story += section('Company and registry (China)', st)
    story.append(kv_table([
        ('Chinese name', value(p.get('name_cn'))),
        ('Established', value(reg.get('established'))),
        ('Registered capital', value(reg.get('registered_capital'))),
        ('Company type', value(reg.get('company_type'))),
        ('Production in business scope', value(reg.get('production_in_scope'))),
        ('Insured employees', value(reg.get('insured_employees'))),
        ('Registered address', value(reg.get('registered_address'))),
        ('Status', value(reg.get('status'))),
        ('Credit code', value(reg.get('credit_code'))),
        ('Risk findings', value(reg.get('risk_findings')) if reg.get('risk_findings') else 'none found'),
        ('Business type (Layer 2)', value((vet or {}).get('business_type'))),
        ('Registry sources', '<br/>'.join(link(u) for u in reg.get('source_urls') or []) or NOT_FOUND),
    ], st))

    # Factory and capacity
    loc, cap = p.get('location') or {}, p.get('capacity') or {}
    story += section('Factory and capacity', st)
    factory_signals = '<br/>'.join(
        f"[{rich(s.get('strength'))}] {rich(s.get('signal'))} ({link(s.get('source_url'), 'source')})"
        for s in (vet or {}).get('factory_signals') or []) or NOT_FOUND
    story.append(kv_table([
        ('Factory address', value(loc.get('factory_addresses'))),
        ('Industrial cluster', value(loc.get('industrial_cluster'))),
        ('Plant area', value(loc.get('plant_area'))),
        ('Other sites', value(loc.get('other_sites'))),
        ('Address check', value(loc.get('address_note'))),
        ('Workforce', value(cap.get('workforce'))),
        ('Equipment', value(cap.get('equipment'))),
        ('Monthly output', value(cap.get('monthly_output'))),
        ('MOQ', value(cap.get('moq'))),
        ('Lead time', value(cap.get('lead_time'))),
        ('Main products', value(cap.get('main_products'))),
        ('Named customers', value(cap.get('customers'))),
        ('Factory evidence', factory_signals),
    ], st))

    # Quality
    q = p.get('quality') or {}
    story += section('Quality and certificates', st)
    cert_rows = [[rich(c.get('name')),
                  colored('verified', '#0B6E4F', True) if c.get('verified') else 'self-reported',
                  value(c.get('holder_match')),
                  link(c.get('source_url'), 'source')]
                 for c in q.get('certifications') or []]
    if cert_rows:
        story.append(grid_table(['Certificate', 'Status', 'Holder name matches', 'Found on'], cert_rows,
                                [CONTENT_W - 92 * mm, 26 * mm, 40 * mm, 26 * mm], st))
    audits = '<br/>'.join(
        f"{rich(a.get('signal'))} — {'verified' if a.get('verified') else 'self-reported'} ({link(a.get('source_url'), 'source')})"
        for a in q.get('audits') or []) or NOT_FOUND
    story.append(kv_table([('Third-party audits', audits), ('Notes', value(q.get('notes')))], st))

    # KSA export
    ksa = p.get('ksa_export') or {}
    rating = ksa.get('rating', 'unknown')
    story += section('Ability to export to Saudi Arabia (KSA)', st)
    signals = '<br/>'.join(f"{rich(s.get('signal'))} ({link(s.get('source_url'), 'source')})"
                           for s in ksa.get('signals') or []) or NOT_FOUND
    story.append(kv_table([
        ('Rating', colored(rating.upper(), KSA_COLOR.get(rating, '#5B6675'), True)),
        ('SASO / SABER experience', value(ksa.get('saso_saber'))),
        ('Export markets', value(ksa.get('markets'))),
        ('Evidence', signals),
        ('Notes', value(ksa.get('notes'))),
    ], st))

    # Chinese web presence
    web = p.get('chinese_web') or {}
    story += section('Chinese web presence', st)
    news = '<br/>'.join(link(n.get('url'), n.get('title')) for n in web.get('news') or []) or NOT_FOUND
    story.append(kv_table([
        ('Chinese website', link(web.get('chinese_website'))),
        ('1688 store', link(web.get('store_1688'))),
        ('WeChat official account', value(web.get('wechat_official_account'))),
        ('Other platforms', '<br/>'.join(link(u) for u in web.get('other_platforms') or []) or NOT_FOUND),
        ('News', news),
    ], st))

    # Sources
    urls = []
    for s in p.get('sources') or []:
        urls.append((s.get('title') or short_url(s.get('url')), s.get('url')))
    for u in reg.get('source_urls') or []:
        urls.append((short_url(u), u))
    if cf.get('evidence_url'):
        urls.append(('Canton Fair evidence', cf['evidence_url']))
    seen, numbered = set(), []
    for title, url in urls:
        if url and url not in seen:
            seen.add(url)
            numbered.append(f'{len(numbered) + 1}. {link(url, title)} <font color="#8A94A6">{rich(short_url(url, 60))}</font>')
    story += section('Sources', st)
    story.append(Paragraph('<br/>'.join(numbered) or NOT_FOUND, st['small']))
    story.append(Spacer(1, 4))
    story.append(Paragraph('Claims marked self-reported come from the company itself. Verify certificates, '
                           'factory status and SABER documents directly with the supplier before ordering.', st['small']))
    return story


# ---------- batch summary ----------

def summary_story(discovery, vetting, deep, report, ranked, st, batch_label, date_label, internal_links=False):
    story = [Bookmark('Batch summary', key='summary', level=0)]
    story.append(Paragraph(rich(f'Supplier Scout — {batch_label} summary'), st['title']))
    story.append(Paragraph(rich(f'{date_label} · clothing textiles from China for export to Saudi Arabia'), st['small']))
    story.append(Spacer(1, 8))

    checked = len(vetting)
    passed = sum(1 for v in vetting if v.get('verdict') == 'PASS')
    confirmed = sum(len(items) for items in ranked.values())
    stats = Table([[Paragraph(f'<b>{n}</b><br/>{rich(label)}', st['cell']) for n, label in [
        (len((discovery or {}).get('selected', [])), 'candidates found'),
        (checked, 'vetted (Layer 2)'),
        (passed, 'passed vetting'),
        (confirmed, 'confirmed (Layer 3)'),
        (len(ranked.get('garment', [])), 'garment factories'),
        (len(ranked.get('fabric', [])), 'fabric mills'),
    ]]], colWidths=[CONTENT_W / 6] * 6)
    stats.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), LIGHT), ('BOX', (0, 0), (-1, -1), 0.4, BORDER),
                               ('INNERGRID', (0, 0), (-1, -1), 0.4, BORDER), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(stats)

    story += section('Overview', st)
    overview = (report or {}).get('overview') or 'The batch editor did not return an overview for this batch.'
    story.append(Paragraph(rich(overview), st['body']))

    for segment in ('garment', 'fabric'):
        story += section(f'{SEGMENT_TITLE[segment]} — ranked', st)
        rows = []
        for p, entry in ranked.get(segment, []):
            name = f'<a href="#profile-{p["id"]}" color="{LINK}">{rich(p["name_en"])}</a>' if internal_links else rich(p['name_en'])
            if p.get('name_cn'):
                name += f"<br/><font color='#5B6675'>{rich(p['name_cn'])}</font>"
            rating = (p.get('ksa_export') or {}).get('rating', 'unknown')
            rec = p.get('recommendation', 'consider')
            rows.append([
                str(entry['rank']),
                name,
                rich(place(p)) or NOT_FOUND,
                f"<b>{entry['final_score']}</b>",
                colored(rating, KSA_COLOR.get(rating, '#5B6675'), True),
                colored(REC_LABEL.get(rec, rec), REC_COLOR.get(rec, MUTED).hexval().replace('0x', '#'), True),
                rich(entry.get('one_line')),
            ])
        if rows:
            story.append(grid_table(['#', 'Company', 'Location', 'Score', 'KSA', 'Advice', 'Why'], rows,
                                    [7 * mm, 44 * mm, 24 * mm, 14 * mm, 20 * mm, 25 * mm, CONTENT_W - 134 * mm], st))
        else:
            story.append(Paragraph('No confirmed suppliers in this segment.', st['body']))

    rejected = []
    for v in vetting:
        if v.get('verdict') == 'REJECT':
            reasons = ', '.join(REASON_LABEL.get(r, r) for r in v.get('reject_reasons') or []) or 'rejected'
            rejected.append((v['id'], v.get('name_en'), 'Layer 2', reasons, v.get('summary')))
    for p in deep:
        if p.get('final_verdict') == 'REJECT':
            rejected.append((p['id'], p.get('name_en'), 'Layer 3', 'overturned in deep dive', p.get('reject_reason')))
    story += section(f'Rejected suppliers ({len(rejected)})', st)
    if rejected:
        rows = [[rich(i), rich(n), rich(stage), rich(reasons), rich((why or '')[:260])]
                for i, n, stage, reasons, why in sorted(rejected)]
        story.append(grid_table(['ID', 'Company', 'Stage', 'Reason', 'Details'], rows,
                                [12 * mm, 44 * mm, 15 * mm, 32 * mm, CONTENT_W - 103 * mm], st,
                                header_bg=colors.HexColor('#5B6675')))
    else:
        story.append(Paragraph('None.', st['body']))

    story += section('How this batch was made', st)
    story.append(Paragraph(
        'Layer 1 found Canton Fair exhibitors through public sources (company websites, B2B platforms and search '
        'results). The Canton Fair website itself was not used, because it asks AI tools not to access it. '
        'Layer 2 removed trading companies, suppliers without their own factory, knitting specialists and '
        'suppliers below the quality bar. Layer 3 researched Chinese sources, factory locations, export ability to '
        'Saudi Arabia and contacts. All rules are in the guidelines folder of the supplier-scout branch.', st['body']))
    return story


# ---------- rendering ----------

def footer(batch_label, date_label):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONTS['Body'], 7)
        canvas.setFillColor(FAINT)
        canvas.drawString(MARGIN, 9 * mm, f'Supplier Scout · {batch_label} · {date_label}')
        canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, f'page {doc.page}')
        canvas.restoreState()
    return draw


def build_pdf(path, story, title, batch_label, date_label):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=title, author='Supplier Scout')
    draw = footer(batch_label, date_label)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir
    if not (run_dir / '3-deep-dive.json').exists():
        sys.exit(f'{run_dir}/3-deep-dive.json not found')

    register_fonts()
    st = make_styles()
    discovery, vetting, deep, report, meta = load_run(run_dir)
    batch_label = meta.get('batch') or run_dir.name
    date_label = meta.get('date') or ''
    cands = {c['id']: c for c in (discovery or {}).get('selected', [])}
    vets = {v['id']: v for v in vetting}
    ranked = rank_profiles(deep, report)
    out = run_dir / 'reports'

    summary = summary_story(discovery, vetting, deep, report, ranked, st, batch_label, date_label)
    build_pdf(out / '00-batch-summary.pdf', summary, f'{batch_label} summary', batch_label, date_label)

    combined = summary_story(discovery, vetting, deep, report, ranked, st, batch_label, date_label, internal_links=True)
    written = 1
    for segment in ('garment', 'fabric'):
        items = ranked.get(segment, [])
        if items:
            combined += [PageBreak(), Bookmark(SEGMENT_TITLE[segment], key=f'segment-{segment}', level=0)]
        for i, (p, entry) in enumerate(items):
            story = profile_story(p, entry, vets.get(p['id']), cands.get(p['id']), st, len(items), batch_label)
            name = f"{entry['rank']:02d}-{p['id']}-{slug(p['name_en'])}.pdf"
            build_pdf(out / segment / name, story, p['name_en'], batch_label, date_label)
            written += 1
            if i:
                combined.append(PageBreak())
            combined += profile_story(p, entry, vets.get(p['id']), cands.get(p['id']), st, len(items), batch_label,
                                      outline_level=1)
    build_pdf(out / f'{slug(batch_label)}-full-report.pdf', combined, f'{batch_label} full report', batch_label, date_label)
    print(f'wrote {written + 1} PDFs to {out}')


if __name__ == '__main__':
    main()
