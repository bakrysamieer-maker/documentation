#!/usr/bin/env python3
"""Glue between the workflows and the run folder.

Workflow agents return their structured results inside their transcripts. This script reads those
transcripts and writes the run files, so large results never need to be copied by hand.

Usage:
    batch.py save-discovery RUN_DIR WORKFLOW_DIR --batch NAME --date YYYY-MM-DD
        Write 1-discovery.json, candidates/<id>.json and run.json from the discovery workflow.
    batch.py collect RUN_DIR WORKFLOW_DIR [WORKFLOW_DIR ...]
        Merge vetting and deep-dive results from research workflows into 2-vetting.json and 3-deep-dive.json.
    batch.py report-input RUN_DIR
        Write report-input.json (compact confirmed profiles and stats) for the batch editor.
    batch.py save-report RUN_DIR WORKFLOW_DIR
        Write 4-report.json from the report workflow.
    batch.py registry RUN_DIR
        Add this batch's suppliers to data/processed.json and its unused candidates to data/backlog.json.
    batch.py known-names
        Print the names already processed (JSON), for the next discovery run.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def agent_results(workflow_dir):
    """Yield (label, result) for each agent of a workflow, in start order.

    The result is the input of the agent's last successful StructuredOutput call, or None.
    """
    workflow_dir = Path(workflow_dir)
    order = []
    journal = workflow_dir / 'journal.jsonl'
    if journal.exists():
        for line in journal.read_text(encoding='utf-8').splitlines():
            entry = json.loads(line)
            if entry.get('type') == 'started' and entry.get('agentId') not in order:
                order.append(entry['agentId'])
    for meta_path in workflow_dir.glob('agent-*.meta.json'):
        agent_id = meta_path.name[len('agent-'):-len('.meta.json')]
        if agent_id not in order:
            order.append(agent_id)

    for agent_id in order:
        meta = read_json(workflow_dir / f'agent-{agent_id}.meta.json', {})
        transcript = workflow_dir / f'agent-{agent_id}.jsonl'
        if not transcript.exists():
            continue
        calls, failed = {}, set()
        for line in transcript.read_text(encoding='utf-8').splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            content = (entry.get('message') or {}).get('content')
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get('type') == 'tool_use' and block.get('name') == 'StructuredOutput':
                    calls[block['id']] = block.get('input')
                elif block.get('type') == 'tool_result' and block.get('is_error'):
                    failed.add(block.get('tool_use_id'))
        good = [result for call_id, result in calls.items() if call_id not in failed]
        yield meta.get('description', agent_id), (good[-1] if good else None)


def norm(name):
    name = re.sub(r'\(.*?\)|（.*?）', ' ', str(name or '').lower())
    name = re.sub(r'co\.?,?\s*ltd\.?|company limited|limited|ltd\.?|corporation|corp\.?|co\.|inc\.?|有限责任公司|有限公司|股份', ' ', name)
    return re.sub(r'[^a-z0-9一-鿿]+', '', name)


def save_discovery(run_dir, workflow_dir, batch, date):
    """Rebuild the discovery result from the agents' outputs, using the same rules as the workflow."""
    run_dir = Path(run_dir)
    found, seen, notes = [], set(norm(n) for n in known_names()), []
    for label, result in agent_results(workflow_dir):
        if not result or not label.startswith(('discover:', 'topup:')):
            continue
        slice_id = label.split(':', 1)[1]
        notes.append({'slice': slice_id, 'notes': result.get('search_notes')})
        for c in result.get('candidates') or []:
            keys = [k for k in (norm(c.get('name_en')), norm(c.get('name_cn'))) if k]
            if not keys or any(k in seen for k in keys):
                continue
            seen.update(keys)
            found.append({**c, 'slice': slice_id})

    strength = {'strong': 0, 'medium': 1, 'weak': 2}
    business = {'manufacturer': 0, 'manufacturer_and_trading': 1, 'unknown': 2, 'trading': 3}

    def promise(c):
        return (strength.get((c.get('canton_fair') or {}).get('strength'), 3),
                business.get(c.get('business_type_claimed'), 2), len(c.get('flags') or []))

    workflow_args = read_json(run_dir / 'discovery-args.json', {})
    per_segment, total = workflow_args.get('per_segment', 25), workflow_args.get('total', 50)
    garments = sorted((c for c in found if c['segment'] == 'garment'), key=promise)
    fabrics = sorted((c for c in found if c['segment'] == 'fabric'), key=promise)
    take_g, take_f = min(len(garments), per_segment), min(len(fabrics), per_segment)
    spare = total - take_g - take_f
    if spare > 0:
        more_g = min(spare, len(garments) - take_g)
        take_g, spare = take_g + more_g, spare - more_g
        take_f += min(spare, len(fabrics) - take_f)
    selected = ([{'id': f'G{i + 1:02d}', **c} for i, c in enumerate(garments[:take_g])]
                + [{'id': f'F{i + 1:02d}', **c} for i, c in enumerate(fabrics[:take_f])])
    extras = garments[take_g:] + fabrics[take_f:]

    write_json(run_dir / '1-discovery.json', {
        'selected': selected, 'extras': extras, 'search_notes': notes,
        'stats': {'found': len(found), 'garment_found': len(garments), 'fabric_found': len(fabrics),
                  'selected_garment': take_g, 'selected_fabric': take_f},
    })
    for c in selected:
        write_json(run_dir / 'candidates' / f"{c['id']}.json", c)
    write_json(run_dir / 'run.json', {'batch': batch, 'date': date})
    print(f'selected {len(selected)} (garment {take_g}, fabric {take_f}) of {len(found)} found; {len(extras)} extras')


def collect(run_dir, workflow_dirs):
    run_dir = Path(run_dir)
    vetting, deep = {}, {}
    for workflow_dir in workflow_dirs:
        for label, result in agent_results(workflow_dir):
            if not result:
                if label.startswith(('vet', 'deep')):
                    print(f'warning: {label} returned no result')
                continue
            if label.startswith('vet'):
                for r in result.get('results') or []:
                    vetting[r['id']] = r
            elif label.startswith('deep'):
                for r in result.get('suppliers') or []:
                    deep[r['id']] = r
    selected = read_json(run_dir / '1-discovery.json', {}).get('selected', [])
    order = {c['id']: i for i, c in enumerate(selected)}
    write_json(run_dir / '2-vetting.json', sorted(vetting.values(), key=lambda r: order.get(r['id'], 999)))
    write_json(run_dir / '3-deep-dive.json', sorted(deep.values(), key=lambda r: order.get(r['id'], 999)))
    passed = [r['id'] for r in vetting.values() if r['verdict'] == 'PASS']
    missing_vet = [c['id'] for c in selected if c['id'] not in vetting]
    missing_deep = [i for i in passed if i not in deep]
    confirmed = sum(1 for r in deep.values() if r['final_verdict'] == 'CONFIRMED')
    print(f'vetted {len(vetting)}/{len(selected)}, passed {len(passed)}, deep-dived {len(deep)}, confirmed {confirmed}')
    if missing_vet:
        print('not vetted:', ','.join(missing_vet))
    if missing_deep:
        print('passed but no deep dive:', ','.join(missing_deep))


def report_input(run_dir):
    run_dir = Path(run_dir)
    vetting = read_json(run_dir / '2-vetting.json', [])
    deep = read_json(run_dir / '3-deep-dive.json', [])
    confirmed = [p for p in deep if p['final_verdict'] == 'CONFIRMED']
    profiles = [{
        'id': p['id'], 'name_en': p['name_en'], 'segment': p['segment'],
        'city': (p.get('location') or {}).get('city'), 'scores': p['scores'], 'total': sum(p['scores'].values()),
        'ksa_rating': (p.get('ksa_export') or {}).get('rating'), 'saso_saber': (p.get('ksa_export') or {}).get('saso_saber'),
        'recommendation': p['recommendation'], 'summary': p['summary'], 'strengths': p['strengths'], 'risks': p['risks'],
        'workforce': (p.get('capacity') or {}).get('workforce'),
        'certifications': [c['name'] + (' (verified)' if c.get('verified') else ' (self-reported)')
                           for c in (p.get('quality') or {}).get('certifications') or []],
    } for p in confirmed]
    stats = {
        'candidates': len(read_json(run_dir / '1-discovery.json', {}).get('selected', [])),
        'vetted': len(vetting),
        'passed_vetting': sum(1 for v in vetting if v['verdict'] == 'PASS'),
        'rejected_in_vetting': {},
        'deep_dived': len(deep),
        'confirmed': len(confirmed),
        'overturned_in_deep_dive': [p['id'] for p in deep if p['final_verdict'] == 'REJECT'],
    }
    for v in vetting:
        for reason in v.get('reject_reasons') or []:
            stats['rejected_in_vetting'][reason] = stats['rejected_in_vetting'].get(reason, 0) + 1
    write_json(run_dir / 'report-input.json', {'stats': stats, 'profiles': profiles})
    print(f'report input: {len(profiles)} confirmed profiles')


def save_report(run_dir, workflow_dir):
    report = None
    for label, result in agent_results(workflow_dir):
        if label == 'batch-editor' and result:
            report = result
    if report is None:
        raise SystemExit('no batch-editor result found')
    write_json(Path(run_dir) / '4-report.json', report)
    print(f"report saved: {len(report.get('rankings', []))} rankings")


def registry(run_dir):
    run_dir = Path(run_dir)
    meta = read_json(run_dir / 'run.json', {})
    discovery = read_json(run_dir / '1-discovery.json', {})
    vetting = {v['id']: v for v in read_json(run_dir / '2-vetting.json', [])}
    deep = {d['id']: d for d in read_json(run_dir / '3-deep-dive.json', [])}
    processed = read_json(DATA / 'processed.json', [])
    done = {norm(p['name_en']) for p in processed}
    for c in discovery.get('selected', []):
        if norm(c['name_en']) in done:
            continue
        v, d = vetting.get(c['id']), deep.get(c['id'])
        outcome = d['final_verdict'] if d else (v['verdict'] if v else 'NOT_VETTED')
        processed.append({'name_en': c['name_en'], 'name_cn': c.get('name_cn'), 'segment': c['segment'],
                          'batch': meta.get('batch'), 'id': c['id'], 'outcome': outcome})
        done.add(norm(c['name_en']))
    write_json(DATA / 'processed.json', processed)
    backlog = [c for c in read_json(DATA / 'backlog.json', []) if norm(c['name_en']) not in done]
    known_backlog = {norm(c['name_en']) for c in backlog}
    backlog += [c for c in discovery.get('extras', []) if norm(c['name_en']) not in done | known_backlog]
    write_json(DATA / 'backlog.json', backlog)
    print(f'processed: {len(processed)} suppliers in total; backlog: {len(backlog)} candidates')


def known_names():
    return [p['name_en'] for p in read_json(DATA / 'processed.json', [])]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('save-discovery')
    p.add_argument('run_dir')
    p.add_argument('workflow_dir')
    p.add_argument('--batch', required=True)
    p.add_argument('--date', required=True)
    p = sub.add_parser('collect')
    p.add_argument('run_dir')
    p.add_argument('workflow_dirs', nargs='+')
    p = sub.add_parser('report-input')
    p.add_argument('run_dir')
    p = sub.add_parser('save-report')
    p.add_argument('run_dir')
    p.add_argument('workflow_dir')
    p = sub.add_parser('registry')
    p.add_argument('run_dir')
    sub.add_parser('known-names')
    args = parser.parse_args()

    if args.command == 'save-discovery':
        save_discovery(args.run_dir, args.workflow_dir, args.batch, args.date)
    elif args.command == 'collect':
        collect(args.run_dir, args.workflow_dirs)
    elif args.command == 'report-input':
        report_input(args.run_dir)
    elif args.command == 'save-report':
        save_report(args.run_dir, args.workflow_dir)
    elif args.command == 'registry':
        registry(args.run_dir)
    elif args.command == 'known-names':
        print(json.dumps(known_names(), ensure_ascii=False))


if __name__ == '__main__':
    main()
