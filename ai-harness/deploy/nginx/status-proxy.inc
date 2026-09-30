# Root-owned /etc/ai-harness/status-proxy.inc. UDS only; never a TCP fallback.
proxy_pass http://unix:/run/ai-harness-status/http.sock;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host "";
proxy_set_header Forwarded "";
proxy_set_header X-AI-Harness-Approval-Proxy "";
proxy_set_header Connection "";
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 5s;
proxy_send_timeout 5s;
