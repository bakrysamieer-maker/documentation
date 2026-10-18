#!/usr/bin/env python3
"""Smoke test for scripts/render_pdfs.py using made-up sample data (not real companies).

Usage:
    python3 tests/test_render.py [output_dir]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent

CONTACTS = {
    'emails': [{'value': 'sales@example.com', 'label': 'sales', 'source_url': 'https://example.com/contact'}],
    'phones': [{'value': '+86 575 0000 0000', 'label': 'office', 'source_url': 'https://example.com/contact'}],
    'wechat': [{'value': 'sample-wechat-id', 'label': 'export manager', 'source_url': 'https://example.com/contact'}],
    'whatsapp': [],
    'linkedin': [{'value': 'https://www.linkedin.com/company/example', 'label': 'company page',
                  'source_url': 'https://example.com/search-result'}],
    'website': 'https://example.com',
    'b2b_profiles': ['https://example.en.made-in-china.com/'],
    'people': [{'name': 'Sample Person', 'title': 'Export Manager', 'source_url': 'https://example.com/team'}],
}


def profile(pid, segment, name, name_cn, scores, rec, rating):
    return {
        'id': pid, 'name_en': name, 'name_cn': name_cn, 'segment': segment, 'final_verdict': 'CONFIRMED',
        'reject_reason': None,
        'registry': {'established': '2008-05-12', 'registered_capital': 'CNY 10,000,000', 'company_type': 'Limited liability company',
                     'production_in_scope': True, 'insured_employees': '186', 'registered_address': '示例工业区 88号 (sample address)',
                     'status': '存续 (active)', 'credit_code': None, 'risk_findings': [],
                     'source_urls': ['https://example.com/registry/very/long/path/that/keeps/going/and/going/to/test/wrapping?query=1&b=2']},
        'location': {'province': 'Zhejiang', 'city': 'Shaoxing', 'factory_addresses': ['Sample Industrial Park, Keqiao'],
                     'industrial_cluster': 'Shaoxing Keqiao', 'plant_area': '25,000 m²', 'other_sites': [],
                     'address_note': 'Registered and factory addresses match.'},
        'capacity': {'workforce': '200 (self-reported)', 'equipment': '120 air-jet looms', 'monthly_output': '1.5 million m',
                     'moq': '3,000 m per colour', 'lead_time': '25–35 days', 'main_products': ['TR suiting', 'thobe fabric'],
                     'customers': []},
        'quality': {'certifications': [
            {'name': 'OEKO-TEX Standard 100', 'holder_match': True, 'verified': True, 'source_url': 'https://example.com/cert'},
            {'name': 'ISO 9001', 'holder_match': None, 'verified': False, 'source_url': 'https://example.com/about'}],
            'audits': [{'signal': 'SGS audited supplier report (2025)', 'source_url': 'https://example.com/audit', 'verified': True}],
            'notes': 'Sample note.'},
        'chinese_web': {'chinese_website': 'https://example.cn', 'store_1688': None, 'wechat_official_account': None,
                        'other_platforms': [], 'news': [{'title': '示例新闻 sample news', 'url': 'https://example.com/news'}]},
        'ksa_export': {'rating': rating, 'markets': ['Saudi Arabia', 'UAE'], 'saso_saber': 'unknown',
                       'signals': [{'signal': 'Lists Saudi Arabia as a main market', 'source_url': 'https://example.com/about'}],
                       'notes': 'Sample.'},
        'contacts': CONTACTS,
        'scores': scores,
        'summary': f'{name} is sample data used to test the PDF layout. It is not a real company.',
        'strengths': ['Own weaving mill', 'Verified OEKO-TEX'], 'risks': ['No SABER proof found'],
        'recommendation': rec,
        'sources': [{'title': 'Company website', 'url': 'https://example.com'}],
    }


def write_sample(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    selected = [
        {'id': 'G01', 'name_en': 'Sample Garment Factory Co., Ltd. (TEST DATA)', 'segment': 'garment',
         'canton_fair': {'strength': 'strong', 'session': '139th, Apr 2026', 'booth': '0.0X00',
                         'evidence_url': 'https://example.com/news/canton-fair', 'evidence_note': 'Sample evidence.'}},
        {'id': 'F01', 'name_en': 'Sample Weaving Mill Co., Ltd. (TEST DATA)', 'segment': 'fabric',
         'canton_fair': {'strength': 'medium', 'session': None, 'booth': None,
                         'evidence_url': 'https://example.com/trade-shows', 'evidence_note': 'Sample evidence.'}},
        {'id': 'F02', 'name_en': 'Sample Trading Co., Ltd. (TEST DATA)', 'segment': 'fabric', 'canton_fair': {}},
    ]
    vet_base = {'confidence': 'high', 'business_type': 'manufacturer', 'knit_share': 'none',
                'factory_signals': [{'signal': 'Factory photos with looms', 'source_url': 'https://example.com/factory',
                                     'strength': 'strong'}],
                'trader_signals': [], 'quality_signals': [], 'established_year': 2008, 'employees': '200',
                'factory_address': 'Sample Industrial Park', 'website': 'https://example.com', 'contacts': CONTACTS}
    vetting = [
        {**vet_base, 'id': 'G01', 'name_en': selected[0]['name_en'], 'name_cn': None, 'segment': 'garment', 'verdict': 'PASS',
         'reject_reasons': [], 'summary': 'Sample pass.'},
        {**vet_base, 'id': 'F01', 'name_en': selected[1]['name_en'], 'name_cn': '示例纺织有限公司', 'segment': 'fabric',
         'verdict': 'PASS', 'reject_reasons': [], 'summary': 'Sample pass.'},
        {**vet_base, 'id': 'F02', 'name_en': selected[2]['name_en'], 'name_cn': None, 'segment': 'fabric', 'verdict': 'REJECT',
         'reject_reasons': ['TRADING_COMPANY'], 'business_type': 'trading',
         'summary': 'Sample reject: the business scope lists only sales and the address is an office.'},
    ]
    deep = [
        profile('G01', 'garment', selected[0]['name_en'], None,
                {'factory': 24, 'quality': 15, 'ksa_export': 14, 'scale': 7, 'contactability': 9}, 'consider', 'moderate'),
        profile('F01', 'fabric', selected[1]['name_en'], '示例纺织有限公司',
                {'factory': 28, 'quality': 20, 'ksa_export': 21, 'scale': 8, 'contactability': 10}, 'shortlist', 'strong'),
    ]
    report = {'overview': 'Sample overview for the layout test.', 'consistency_notes': [],
              'rankings': [{'id': 'G01', 'segment': 'garment', 'rank': 1, 'final_score': 69, 'adjustment_note': None,
                            'one_line': 'Sample one-line reason.'},
                           {'id': 'F01', 'segment': 'fabric', 'rank': 1, 'final_score': 87, 'adjustment_note': None,
                            'one_line': 'Sample one-line reason.'}]}
    files = {'1-discovery.json': {'selected': selected}, '2-vetting.json': vetting, '3-deep-dive.json': deep,
             '4-report.json': report, 'run.json': {'batch': 'sample-batch', 'date': '2026-01-01'}}
    for name, data in files.items():
        (run_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp()) / 'sample-run'
    write_sample(out)
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'render_pdfs.py'), str(out)], check=True)
    pdfs = sorted((out / 'reports').rglob('*.pdf'))
    names = [p.relative_to(out / 'reports').as_posix() for p in pdfs]
    expected = {'00-batch-summary.pdf', 'sample-batch-full-report.pdf',
                'garment/01-G01-sample-garment-factory-co-ltd-test-data.pdf',
                'fabric/01-F01-sample-weaving-mill-co-ltd-test-data.pdf'}
    missing = expected - set(names)
    assert not missing, f'missing PDFs: {missing}'
    full = PdfReader(str(out / 'reports' / 'sample-batch-full-report.pdf'))
    assert len(full.pages) >= 3, 'full report should have the summary plus two profiles'
    text = ''.join(page.extract_text() for page in full.pages)
    for needle in ['Sample Weaving Mill', 'SHORTLIST', 'Rejected suppliers (1)', 'trading company']:
        assert needle in text, f'{needle!r} not found in the full report'
    print(f'OK: {len(pdfs)} PDFs, full report has {len(full.pages)} pages ({out})')


if __name__ == '__main__':
    main()
