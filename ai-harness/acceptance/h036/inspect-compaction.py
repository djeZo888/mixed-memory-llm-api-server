#!/usr/bin/env python3
"""Inspect retained bytes offline. Emits review facts, never an acceptance PASS."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect(request_path, before_path, after_path, paste_path):
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    metadata = request.get('client_metadata', {})
    encoded = metadata.get('x-codex-turn-metadata')
    turn = json.loads(encoded) if isinstance(encoded, str) else {}
    before, after, paste = before_path.read_bytes(), after_path.read_bytes(), paste_path.read_text()
    events = [json.loads(line) for line in after.splitlines() if line.strip()]
    texts, token_events, compacted = [], [], []
    for event in events:
        payload = event.get('payload', {})
        if event.get('type') == 'response_item' and payload.get('type') == 'message' and payload.get('role') == 'user':
            texts.extend(part.get('text', '') for part in payload.get('content', []) if part.get('type') == 'input_text')
        if event.get('type') == 'event_msg' and payload.get('type') == 'token_count':
            token_events.append(payload.get('info'))
        if event.get('type') == 'compacted':
            compacted.append({'timestamp': event.get('timestamp'), 'payloadSha256': digest(json.dumps(payload, sort_keys=True).encode())})
    return {
        'state': 'REVIEW_REQUIRED_NOT_ACCEPTANCE',
        'requestSha256': digest(request_bytes), 'model': request.get('model'),
        'requestKind': turn.get('request_kind'), 'compactionMetadata': turn.get('compaction'),
        'threadId': metadata.get('thread_id'), 'turnId': metadata.get('turn_id'),
        'beforeSha256': digest(before), 'afterSha256': digest(after),
        'beforeIsExactPrefix': after.startswith(before),
        'pasteSha256': digest(paste.encode()), 'originalPastePresentVerbatim': any(paste in text for text in texts),
        'compactedRecords': compacted, 'reportedTokenUsage': token_events,
        'stillRequired': ['actual native count and dispatch bytes match', 'AUTO/context_limit metadata and canonical event lifecycle',
                          'unchanged production 400000 threshold / 65536 output reserve', 'recall judged without oracle in active prompt',
                          'successful subsequent useful tool and artifact hash', 'browser progress/reload', 'settlement and actual wrapper exit'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['request', 'before', 'after', 'paste']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.request, args.before, args.after, args.paste), indent=2))
