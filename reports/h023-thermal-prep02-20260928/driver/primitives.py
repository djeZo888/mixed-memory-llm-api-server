"""Narrow H013 persistence/full-drain/interval primitives; no network or lifecycle code."""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import threading
import zlib
from contract import Refusal, canonical, require, number

class Journal:
    """Every write stays on the held registered mount and anchored path.

    One immutable intent consumes the namespace forever. The phase RLock owns
    these task-only files; no canonical lifecycle lease is taken on hot paths.
    """
    def __init__(self, path, intent, *, storage_guard, anchored_root):
        require(storage_guard is not None and anchored_root is not None, 'live guarded journal required')
        self.path = Path(path)
        self.guard, self.root_cls = storage_guard, anchored_root
        self.lock = threading.RLock()
        with self.root_cls(str(self.path.parent), self.guard) as parent:
            require(parent.stat(self.path.name, missing_ok=True) is None, 'journal namespace already consumed')
            parent.mkdir(self.path.name, parents=False)
        self.write('INTENT', intent, exclusive=True)

    def write(self, name, value, exclusive=False):
        require(name and all(c.isalnum() or c in '-_' for c in name), 'invalid journal name')
        with self.lock, self.root_cls(str(self.path), self.guard) as root:
            if exclusive:
                with root.open(name+'.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600) as f:
                    f.write(canonical(value)+b'\n');f.fsync()
                os.fsync(root.fileno())
            else:
                root.atomic_json(name+'.json', value)

    def append(self, name, value):
        require(name and all(c.isalnum() or c in '-_' for c in name), 'invalid journal name')
        with self.lock, self.root_cls(str(self.path), self.guard) as root:
            with root.open(name+'.jsonl', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600) as f:
                f.write(canonical(value)+b'\n');f.fsync()
            os.fsync(root.fileno())


def stamp(row, name, clock):
    value = clock()
    row[name] = dict(value)
    return value


def capture_text(response, row, count, output_cap, clock):
    """Read through actual EOF after DONE; partial row survives any exception.

    Adapted from H013 request(). Fix: DONE is an event, never a break/settlement.
    No model content is retained. Native timings and usage are retained as received.
    """
    row.update(http_status=response.status, done=False, finish_reason=None, usage=None,
               response_errors=[], native_timings=[], http_drained=False)
    total = 0
    event = []
    try:
        if response.status != 200:
            error = response.read(65537)
            row['error_response_sha256'] = hashlib.sha256(error).hexdigest()
            row['error_response_truncated'] = len(error) > 65536
            raise Refusal('HTTP non-200 response')
        while True:
            line = response.readline(1024*1024+1)
            total += len(line)
            require(len(line) <= 1024*1024 and total <= 16*1024*1024, 'SSE bound exceeded')
            if not line:
                require(not event, 'unterminated SSE event at EOF')
                require(getattr(response,'length',0) in (0,None), 'HTTP content-length not fully drained')
                stamp(row, 'eof', clock)
                row['http_drained'] = True
                break
            require(line.endswith(b'\n'), 'truncated SSE line')
            if line.strip():
                if line.startswith(b'data:'):
                    event.append(line[5:].strip())
                elif not line.startswith((b':', b'event:', b'id:', b'retry:')):
                    raise Refusal('unexpected stream data')
                continue
            if not event:
                continue
            data = b'\n'.join(event)
            event = []
            require(not row['done'], 'data after DONE')
            if data == b'[DONE]':
                row['done'] = True
                stamp(row, 'done_at', clock)
                continue  # MUST keep reading to HTTP EOF
            obj = json.loads(data)
            require(isinstance(obj, dict), 'invalid SSE object')
            if obj.get('error') is not None:
                # Error payload may contain private details; retain error hash + safe type.
                row['response_errors'].append({'sha256': hashlib.sha256(data).hexdigest(), 'kind': 'native_error'})
                raise Refusal('native response error')
            if obj.get('id'):
                row['native_response_id'] = obj['id']
            if obj.get('usage') is not None:
                require(row['usage'] is None or row['usage'] == obj['usage'], 'conflicting usage')
                row['usage'] = obj['usage']
            if obj.get('timings') is not None:
                row['native_timings'].append(obj['timings'])
            for choice in obj.get('choices', []):
                require(choice.get('index', 0) == 0, 'multiple choices forbidden')
                if choice.get('finish_reason') is not None:
                    require(row['finish_reason'] is None or row['finish_reason'] == choice['finish_reason'], 'conflicting finish')
                    row['finish_reason'] = choice['finish_reason']
                    stamp(row, 'finish_at', clock)
                delta = choice.get('delta', {})
                require(not delta.get('tool_calls'), 'unexpected tools')
                if delta.get('content') or delta.get('reasoning_content') or delta.get('reasoning'):
                    if 'first_output' not in row:
                        stamp(row, 'first_output', clock)
                    stamp(row, 'last_output', clock)
        require(row['done'] and row['finish_reason'] in ('stop', 'length') and row['usage'], 'finish/usage/DONE required')
        usage = row['usage']
        require(all(type(usage.get(k)) is int for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')), 'integer native usage required')
        require(usage['prompt_tokens'] == count and 0 < usage['completion_tokens'] <= output_cap
                and usage['total_tokens'] == count+usage['completion_tokens'], 'native usage/count mismatch')
        require('first_output' in row, 'actual output required')
        row['response_complete'] = True
    except Exception as exc:
        row.setdefault('first_failure', {'kind': type(exc).__name__, 'reason': str(exc) if isinstance(exc, Refusal) else 'transport_or_parse_error'})
        row['response_complete'] = False
        raise
    finally:
        row['response_bytes'] = total
    return row


def decode_png(png, expected=(1920, 1080)):
    """Validate chunks/CRC, decompress and unfilter all native RGB(A)8 pixels.

    H013 only inspected IHDR; this explicitly proves a decodable complete PNG.
    Unsupported formats refuse rather than claim a header check is full decode.
    """
    require(png.startswith(b'\x89PNG\r\n\x1a\n'), 'PNG signature')
    offset, compressed, header, ended = 8, bytearray(), None, False
    while offset < len(png):
        require(offset+12 <= len(png), 'PNG truncated chunk')
        size = struct.unpack('>I', png[offset:offset+4])[0]
        kind = png[offset+4:offset+8]
        require(size <= 40*1024*1024 and offset+12+size <= len(png), 'PNG chunk bound')
        data = png[offset+8:offset+8+size]
        crc = struct.unpack('>I', png[offset+8+size:offset+12+size])[0]
        require(zlib.crc32(kind+data) & 0xffffffff == crc, 'PNG CRC')
        if header is None:
            require(kind == b'IHDR' and len(data) == 13, 'PNG IHDR first')
            header = struct.unpack('>IIBBBBB', data)
        elif kind == b'IHDR':
            raise Refusal('duplicate PNG IHDR')
        elif kind == b'IDAT':
            compressed.extend(data)
        elif kind == b'IEND':
            require(not data and offset+12 == len(png), 'PNG trailing/truncated IEND')
            ended = True
        elif kind[0] & 32 == 0:
            raise Refusal('unsupported critical PNG chunk')
        offset += size+12
    require(ended and header and compressed, 'complete PNG required')
    w, h, bits, color, compression, filtering, interlace = header
    require((w, h) == expected, 'image dimensions')
    require(bits == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0), 'unsupported native PNG format')
    bpp = 3 if color == 2 else 4
    stride = w*bpp
    maximum = h*(stride+1)
    z = zlib.decompressobj()
    raw = z.decompress(compressed, maximum+1)
    require(len(raw) == maximum and z.eof and not z.unused_data and not z.unconsumed_tail, 'PNG decode length/EOF')
    previous = bytearray(stride)
    pixel_hash = hashlib.sha256()
    for y in range(h):
        start = y*(stride+1)
        filter_type = raw[start]
        require(filter_type in range(5), 'PNG invalid filter')
        scan = bytearray(raw[start+1:start+1+stride])
        if filter_type:
            for x in range(stride):
                left = scan[x-bpp] if x >= bpp else 0
                up = previous[x]
                corner = previous[x-bpp] if x >= bpp else 0
                if filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left+up)//2
                else:
                    p = left+up-corner
                    distances = (abs(p-left), abs(p-up), abs(p-corner))
                    predictor = (left, up, corner)[distances.index(min(distances))]
                scan[x] = (scan[x]+predictor) & 255
        pixel_hash.update(scan)
        previous = scan
    return {'width': w, 'height': h, 'png_sha256': hashlib.sha256(png).hexdigest(),
            'decoded_pixels_sha256': pixel_hash.hexdigest(), 'decoded': True, 'bytes': len(png)}


def capture_image(response, row, clock):
    row.update(http_status=response.status, http_drained=False, response_complete=False)
    try:
        require(response.status == 200, 'image HTTP non-200')
        body = response.read(40*1024*1024+1)
        require(0 < len(body) <= 40*1024*1024, 'image response bound')
        stamp(row, 'first_output', clock)
        stamp(row, 'last_output', clock)
        require(response.read(1) == b'', 'image HTTP not drained')
        stamp(row, 'eof', clock)
        row['http_drained'] = True
        value = json.loads(body)
        require(not value.get('error') and len(value.get('data', [])) == 1, 'single image response required')
        png = base64.b64decode(value['data'][0]['b64_json'], validate=True)
        row['image'] = decode_png(png)
        row['native_timings'] = value.get('timings')  # absent is unavailable, not invented
        row['response_complete'] = True
    except Exception as exc:
        row.setdefault('first_failure', {'kind': type(exc).__name__, 'reason': str(exc) if isinstance(exc, Refusal) else 'image_transport_or_decode_error'})
        raise
    return row


def union(intervals):
    result = []
    for a, b in sorted(intervals):
        require(number(a) and number(b) and 0 <= a <= b, 'invalid interval')
        if result and a <= result[-1][1]:
            result[-1][1] = max(b, result[-1][1])
        else:
            result.append([a, b])
    return result


def intersect(left, right):
    out, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            out.append([start, end])
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return out


def interval_report(by_lane, start, end):
    require(number(start) and number(end) and 0 <= start <= end, 'report window')
    merged = {lane: union([[max(start, a), min(end, b)] for a, b in rows if b >= start and a <= end])
              for lane, rows in by_lane.items()}
    common = [[start, end]]
    lanes = {}
    for lane, rows in merged.items():
        common = intersect(common, rows)
        cursor, gaps = start, []
        for a, b in rows:
            gaps.append(a-cursor)
            cursor = b
        gaps.append(end-cursor)
        lanes[lane] = {'active_seconds': sum(b-a for a, b in rows), 'largest_idle_gap_seconds': max(gaps), 'intervals': rows}
    return {'window': [start, end], 'lanes': lanes, 'intersection_intervals': common if merged else [],
            'intersection_seconds': sum(b-a for a, b in common) if merged else 0}
