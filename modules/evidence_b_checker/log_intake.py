"""保险/工业监控日志的 B 侧接收检查；不替代 A 的建链及业务语义审核。"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def pointer_part(value):
    return str(value).replace('~', '~0').replace('/', '~1')


def resolve(record, pointer):
    if pointer == '':
        return record
    if not pointer.startswith('/'):
        raise ValueError('定位必须是 JSON Pointer')
    value = record
    for part in pointer[1:].split('/'):
        if '~' in part.replace('~1', '').replace('~0', ''):
            raise ValueError('非法 JSON Pointer 转义')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not part.isascii() or not part.isdigit() or (len(part) > 1 and part.startswith('0')):
                raise ValueError('非法数组下标')
            value = value[int(part)]
        else:
            value = value[part]
    return value


def walk(value, path):
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, path + '/' + pointer_part(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from walk(v, path + '/' + str(i))


def inspect_log(record):
    """保留原始日志、内容指纹与定位。异常是观察项，不自动映射为业务四态。"""
    if not isinstance(record, dict):
        raise ValueError('每条日志必须为对象')
    for key in ('case_id', 'run_id', 'user_question', 'ai_answer'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('缺少非空字符串：' + key)
    if not isinstance(record.get('visible_context'), dict) or not isinstance(record.get('trace'), list):
        raise ValueError('visible_context 必须为对象，trace 必须为数组')
    signature = digest(record)
    evidence, notes, observations, event_ids = [], [], [], set()
    for i, event in enumerate(record['trace']):
        path = '/trace/' + str(i)
        if not isinstance(event, dict) or not isinstance(event.get('id'), str) or not event['id'].strip():
            raise ValueError('事件必须有非空 id：' + path)
        if event['id'] in event_ids:
            raise ValueError('同一次运行内事件 id 重复：' + event['id'])
        event_ids.add(event['id'])
        if event.get('event') == 'assistant_progress_note':
            if not isinstance(event.get('text'), str) or not event['text'].strip():
                raise ValueError('阶段性说明缺少 text：' + path)
            notes.append({'event_id': event['id'], 'pointer': path + '/text', 'text': event['text']})
            continue
        if event.get('event') != 'tool_call':
            raise ValueError('尚未对齐的事件类型：' + path)
        if (not isinstance(event.get('tool'), str) or not event['tool'].strip()
                or not isinstance(event.get('type'), str) or not event['type'].strip()
                or not isinstance(event.get('arguments'), dict) or 'result' not in event):
            raise ValueError('工具事件缺少 tool/type/arguments/result：' + path)
        evidence.append({'event_id': event['id'], 'tool': event['tool'],
                         'arguments_pointer': path + '/arguments', 'result_pointer': path + '/result'})
        for location, value in walk(event['result'], path + '/result'):
            code = None
            if isinstance(value, dict) and (
                    value.get('has_more') is True or value.get('pagination_complete') is False
                    or (type(value.get('page')) is int and type(value.get('total_pages')) is int
                        and 1 <= value['page'] < value['total_pages'])):
                code = 'PARTIAL_PAGE_RESPONSE'
            elif location.endswith('/data_completeness') and value == 'PARTIAL':
                code = 'REPORTED_PARTIAL_DATA'
            elif value is None:
                code = 'NULL_VALUE'
            elif value == []:
                code = 'EMPTY_ARRAY'
            elif isinstance(value, str) and value in ('TIMEOUT', 'ACCESS_DENIED', 'FORBIDDEN', 'ERROR', 'SENSOR_OFFLINE', 'UNAVAILABLE', 'NO_DATA'):
                code = 'REPORTED_TOOL_OR_DATA_ERROR'
            if code:
                observations.append({'code': code, 'event_id': event['id'], 'pointer': location,
                                     'value': deepcopy(value), 'business_effect': 'pending_review'})
    return {'case_id': record['case_id'], 'run_id': record['run_id'],
            'log_sha256': signature, 'review_stage': 'log_intake',
            'format_valid': True, 'semantic_review_status': 'not_performed',
            'answer_verdict': None, 'answer_pointer': '/ai_answer',
            'evidence_index': evidence, 'progress_notes': notes,
            'observations': observations,
            'pending': ['A 的同次候选图、命题和适用规则', '新版图与日志引用的字段映射',
                        'Loop 补查接口及新回执与运行版本的关联约定'],
            'raw_log': deepcopy(record)}


def verify_reference(report, pointer, expected_value):
    """定位、值及整条日志绑定；只证明引用存在，不证明结论成立。"""
    try:
        raw = report['raw_log']
        return (digest(raw) == report['log_sha256']
                and digest(resolve(raw, pointer)) == digest(expected_value))
    except (ValueError, KeyError, TypeError, IndexError):
        return False


def inspect_dataset(records):
    records = [records] if isinstance(records, dict) else records
    if not isinstance(records, list) or not records:
        raise ValueError('输入必须是日志对象或非空日志数组')
    results, seen = [], set()
    for record in records:
        report = inspect_log(record)
        key = report['case_id'], report['run_id']
        if key in seen:
            raise ValueError('同一批次 case_id/run_id 重复：' + str(key))
        seen.add(key)
        results.append(report)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error('输出不可覆盖输入日志')
    results = inspect_dataset(json.loads(args.input.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'接收 {len(results)} 条日志；业务语义审核未执行。')


if __name__ == '__main__':
    main()
