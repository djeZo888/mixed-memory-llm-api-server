# Troubleshooting

## `/data` is not mounted

Do not download models, build containers, or write service logs. Continue only with the approved M2 dry-run and setup path.

## Disk identity is ambiguous

Stop. Do not partition or format any disk until the intended non-root 2 TB data disk is proven unused and unmounted.

## Secret scan finds a real secret

Stop. Do not commit or push. Remove the secret from the working tree and assess whether history cleanup is required.

## API is reachable without auth

Stop exposure work and return to localhost binding until auth and firewall policy are verified.
