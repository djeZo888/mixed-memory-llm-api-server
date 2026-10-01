# Root-owned source template. Never read or embed the protected include's value.
# Reuses the installed actual-peer deny inventory; no forwarded-IP trust.
include /etc/ai-harness/admin-peer-deny.inc;
limit_except POST { deny all; }
client_max_body_size 1k;
client_body_timeout 5s;
include /etc/ai-harness/image-approval-proxy.conf;
proxy_pass http://127.0.0.1:8080;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host "";
proxy_set_header Forwarded "";
proxy_set_header Connection "";
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 15s;
proxy_send_timeout 15s;
