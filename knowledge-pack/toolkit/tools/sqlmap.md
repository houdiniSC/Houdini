# sqlmap

- Category: SQL injection detection and exploitation
- Usage: `sqlmap -u "<url>" --batch --level 2 --risk 2`
- Warnings: intrusive — can trigger WAFs and rate limits; use `--delay` and `--random-agent`
- Never use destructive flags on live targets without explicit user confirmation
