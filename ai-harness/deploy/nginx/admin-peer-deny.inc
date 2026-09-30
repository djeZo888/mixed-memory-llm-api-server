# Root-owned /etc/ai-harness/admin-peer-deny.inc. Actual peers only.
# No real_ip_header/set_real_ip_from in this server or inherited http context.
# Before activation inventory and add ALL harness own IPv4/IPv6/Slirp egress IPs.
deny 127.0.0.0/8;
deny ::1;
deny 10.156.100.61;
allow all;
