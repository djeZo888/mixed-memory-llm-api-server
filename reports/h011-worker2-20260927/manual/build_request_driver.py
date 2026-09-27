"""Extract reviewed H010 buffered reader/telemetry functions, preserving provenance."""
import ast
import hashlib
from pathlib import Path

SOURCE_HASH = None  # Exact SHA stored alongside all baseline dependencies.
NAMES = {'buffer','persist','run','remaining','cancel','call','proc_fields','sample',
         'resource_reason','request_payload','stream','sampling','periodic_writer','qualify'}

def build(path):
    source = Path(path).read_text()
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
    if {node.name for node in functions} != NAMES:
        raise ValueError('request_driver_functions_missing')
    text = '\n\n'.join(ast.get_source_segment(source,node) for node in functions) + '\n'
    # Closed H011 lane/budget adjustments; no reader fsync/guard/lifecycle work.
    if text.count("HTTPConnection('127.0.0.1', 30010") != 2:
        raise ValueError('request_driver_port_edit_mismatch')
    text = text.replace("HTTPConnection('127.0.0.1', 30010", "HTTPConnection('127.0.0.1', 30011")
    text = text.replace("len(samples) <= 1600", "len(samples) <= 3000")
    sent_site = """        connection.request('POST', '/v1/chat/completions', wire_body,
                           {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})"""
    if text.count(sent_site) != 1:
        raise ValueError('request_body_sent_edit_mismatch')
    text = text.replace(sent_site, sent_site + "\n        row['request_body_sent_utc'] = now()", 1)

    header = '''"""H011 reuse of H010 reader/sampler. Import is inert; no main/dispatch."""
import copy, datetime, hashlib, http.client, json, os, pathlib, re, signal, socket, subprocess, threading, time
P = pathlib.Path
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
'''
    return (header + text).encode()
