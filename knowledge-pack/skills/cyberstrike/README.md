# CyberStrike skills library

Imported from [CyberStrikeus/CyberStrike](https://github.com/CyberStrikeus/CyberStrike)
(`.cyberstrike/skill/`) and organized into five categories:

- `attack-methodologies/` — web attack techniques (SSRF, JWT, SSTI, XXE, ...)
- `post-exploitation/` — post-exploitation playbooks (Linux/Windows/cloud/K8s)
- `domain-knowledge/` — AD, CI/CD, cloud, eBPF, LLM security, recon methodology
- `mobile/` — MITRE Mobile techniques (APK / mobile testing)
- `compliance/` — reference library (CIS, NIST, MITRE ATT&CK + ICS) — browse on demand only

## Token discipline

This library is NEVER loaded into context. Only the skills index
(`~/.hermes/skills/index.yaml` → `cyberstrike/index.yaml`) lists names and
descriptions. The agent opens a single `SKILL.md` only when its description
matches the task. See SOUL.md "المهارات".
