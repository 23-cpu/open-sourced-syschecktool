# syscheck

A lightweight, read-only system health snapshot tool.

This is a small script I built to reduce repetitive troubleshooting steps
(disk/memory/load/uptime/network) into a single command that outputs a
clear summary and optionally writes a JSON report.

## Features
- OS / kernel information
- Uptime (best-effort)
- CPU load snapshot (best-effort)
- Memory summary (best-effort)
- Disk usage for one or more paths
- Basic network checks (DNS resolve + ping)
- Optional JSON output

## Quick start

```bash
# text report
python3 src/syscheck.py

# write JSON report
python3 src/syscheck.py --json report.json

# choose disk paths
python3 src/syscheck.py --disk / --disk /home
```

## Makefile helpers

```bash
make run
make json
make lint
make test
```

## Example output

```
SYSHECK REPORT (UTC)
platform: Linux 6.x ...
...
```

## Resume-friendly one-liner

**syscheck (Python):** automated common system health checks (disk/memory/load/network) into a single report (text + JSON) to speed up triage.

## Notes
- On Windows, some checks fall back to best-effort command outputs.
- This tool is read-only; it does not change system settings.
