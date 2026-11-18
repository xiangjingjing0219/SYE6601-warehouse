"""Independent provenance audit for A's egraph output; not a business verdict engine."""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
try:
    from .log_intake import inspect_log, digest, walk
except ImportError:
    from log_intake import inspect_log, digest, walk


def locate(record, locator):
    """Strictly resolve A trace[event_id].result locators; never eval."""
    match = re.fullmatch(r'trace\[([^\]]+)\]\.result(.*)', locator or '')
    if not match:
        raise ValueError('unsupported locator')
    matches = [(i, e) for i, e in enumerate(record['trace']) if e.get('id') == match[1]]
    if len(matches) != 1 or matches[0][1].get('event') != 'tool_call':
        raise ValueError('locator must identify one tool result')
    i, event = matches[0]
    value, pointer, rest = event['result'], f'/trace/{i}/result', match[2]
    while rest:
        part = re.match(r'(?:\.([^\.\[\]]+)|\[(0|[1-9][0-9]*)\])', rest)
        if not part:
            raise ValueError('unsupported locator suffix')
        if part[1] is not None:
            key = part[1]
            if not isinstance(value, dict):
                raise ValueError('expected object')
        else:
            key = int(part[2])
            if not isinstance(value, list):
                raise ValueError('expected list')
        value = value[key]
        pointer += '/' + str(key).replace('~', '~0').replace('/', '~1')
        rest = rest[part.end():]
    return pointer, value


def audit(record, graph):
    intake = inspect_log(record)
    findings, references = [], []
    def flag(code, subject, detail):
        findings.append(dict(code=code, subject=subject, detail=detail))
    for key in ('case_id', 'run_id'):
        if graph.get(key) != record[key]:
            flag('RUN_MISMATCH', key, 'graph and source differ')
    nodes, checks = graph.get('nodes', []), graph.get('checks', [])
    ids = [n.get('id') for n in nodes]
    check_ids = [c.get('check_id') for c in checks]
    for kind, values in [('node', ids), ('check', check_ids)]:
        for ident, count in Counter(values).items():
            if not ident or count != 1:
                flag('INVALID_ID', kind, str(ident))
    def ref(ident, subject, allowed=ids):
        if ident is not None and ident not in allowed:
            flag('DANGLING_REFERENCE', subject, str(ident))
    for edge in graph.get('edges', []):
        ref(edge.get('source'), edge.get('id')); ref(edge.get('target'), edge.get('id'))
    for node in nodes:
        if node.get('meta', {}).get('check_id'):
            ref(node['meta']['check_id'], node.get('id'), check_ids)
    for check in checks:
        for key in ('target_node', 'evidence_ref', 'rule_id'):
            ref(check.get(key), check.get('check_id'))
        for ident in check.get('affected_claims', []):
            ref(ident, check.get('check_id'))
    for path in graph.get('paths', []):
        ref(path.get('goal_claim'), path.get('path_id'))
        for ident in path.get('conditions', []):
            ref(ident, path.get('path_id'))
        if not set(path.get('satisfied_conditions', [])).issubset(path.get('conditions', [])):
            flag('PATH_SET_MISMATCH', path.get('path_id'), 'satisfied conditions outside path')
    for obj in nodes + checks:
        subject = obj.get('id', obj.get('check_id'))
        loc = obj.get('locator')
        if not loc:
            continue
        try:
            pointer, value = locate(record, loc)
            references.append(dict(subject=subject, pointer=pointer, value_sha256=digest(value)))
            excerpt = obj.get('excerpt')
            if excerpt and (not isinstance(value, str) or excerpt not in value):
                if type(value) in (bool, int, float) and excerpt == str(value):
                    flag('SCALAR_RENDERING', subject, 'excerpt is a string rendering of a typed scalar, not a verbatim text quote')
                else:
                    flag('EXCERPT_NOT_VERIFIED', subject, 'excerpt is not a substring of resolved string')
            if 'check_id' in obj and obj.get('actual') is not None and digest(obj['actual']) != digest(value):
                flag('CHECK_ACTUAL_NOT_IDENTICAL', subject, 'actual differs from resolved value; derived values need explicit calculation')
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            flag('UNRESOLVED_LOCATOR', subject, type(exc).__name__)
    clauses = []
    for i, event in enumerate(record['trace']):
        if event.get('event') != 'tool_call':
            continue
        for pointer, value in walk(event['result'], f'/trace/{i}/result'):
            if pointer.endswith('_excerpt') and isinstance(value, str) and value:
                represented = any(n.get('excerpt') == value for n in nodes if n.get('type') == 'rule')
                clauses.append(dict(pointer=pointer, text=value, represented_as_rule=represented))
    claims = [dict(id=n['id'], content=n.get('content'), a_status=n.get('evidence_status'),
                   b_status='UNKNOWN', reason='PROVENANCE_AUDIT_ONLY_SEMANTIC_REVIEW_PENDING')
              for n in nodes if n.get('type') in ('claim', 'obligation')]
    weak = [c.get('check_id') for c in checks if c.get('verdict') == 'SUPPORT' and c.get('kind') in ('field_restatement', 'value_match')]
    return dict(case_id=record['case_id'], run_id=record['run_id'], source_sha256=intake['log_sha256'],
                graph_sha256=digest(graph), audit_scope='provenance_and_structure_only',
                semantic_review_status='not_performed', claims=claims, findings=findings,
                references=references, insurance_clause_inventory=clauses,
                narrow_support_checks_requiring_review=weak, source_observations=intake['observations'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--logs', required=True); p.add_argument('--graphs', required=True); p.add_argument('--out', required=True)
    args = p.parse_args()
    records = json.loads(Path(args.logs).read_text(encoding='utf-8'))
    seen = set(); reports = []
    for record in records:
        if record['case_id'] in seen:
            raise ValueError('duplicate case_id')
        seen.add(record['case_id'])
        case = record['case_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', case):
            raise ValueError('unsafe case_id')
        graph = json.loads((Path(args.graphs) / (case + '_graph.json')).read_text(encoding='utf-8'))
        reports.append(audit(record, graph))
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    summary = dict(cases=len(reports), semantic_review_status='not_performed',
                   findings=dict(Counter(f['code'] for r in reports for f in r['findings'])),
                   references=sum(len(r['references']) for r in reports),
                   insurance_clauses=sum(len(r['insurance_clause_inventory']) for r in reports),
                   clauses_not_represented_as_rule=sum(not c['represented_as_rule'] for r in reports for c in r['insurance_clause_inventory']),
                   cases_with_narrow_support=sum(bool(r['narrow_support_checks_requiring_review']) for r in reports))
    for name, value in [('audit_reports.json', reports), ('summary.json', summary)]:
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    main()
