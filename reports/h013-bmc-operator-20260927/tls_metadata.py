#!/usr/bin/env python3
"""Read public certificate metadata on ai-harness; no credentials or HTTP."""
import argparse
import json
import socket
import ssl
import subprocess
from datetime import datetime, timezone
import probe

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true', required=True)
    p.parse_args()
    result = {'at':datetime.now(timezone.utc).isoformat(),'host':probe.HOST,'port':443,'requests':0}
    c = probe.PinnedConnection()
    try:
        c.connect()
        result['pin_verified'] = True
        der = c.sock.getpeercert(binary_form=True)
        pem = ssl.DER_cert_to_PEM_cert(der).encode()
        result['leaf_metadata'] = subprocess.run(
            ['openssl','x509','-noout','-dates','-subject','-issuer','-ext','subjectAltName'],
            input=pem,capture_output=True,timeout=4,check=True).stdout.decode()
        ip_check = subprocess.run(
            ['openssl','x509','-noout','-checkip',probe.HOST],input=pem,capture_output=True,timeout=4)
        result['ip_check_output'] = ip_check.stdout.decode().strip()
        result['ip_match'] = result['ip_check_output'] == 'IP ' + probe.HOST + ' does match certificate'
    finally:
        c.close()
    try:
        with socket.create_connection((probe.HOST,443),timeout=5) as raw:
            with ssl.create_default_context().wrap_socket(raw,server_hostname=probe.HOST):
                result['normal_ca_verified'] = True
    except ssl.SSLCertVerificationError as e:
        result['normal_ca_verified'] = False
        result['normal_ca_error_code'] = e.verify_code
        result['normal_ca_error'] = e.verify_message
    result['pin_checks'] = probe.PIN_CHECKS
    result['tls_connections'] = 2
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
