---
name: report-template
description: Professional security report structure — executive summary, scope, methodology, findings by severity, evidence, remediation, assets, positives.
---

# Report Template

Use `templates/report-template.md` as the scaffold. Write in the user's language (Arabic default).
Filename contract: `<target-domain>.<ext>` (full domain incl. TLD) inside `~/recon/<target>/`.

## Structure
1. Executive summary — verdict, critical findings count, key risks
2. Scope & authorization — declared targets, dates, tools
3. Methodology — passive → active → validation, tools used
4. Findings by severity (Critical / High / Medium / Low / Info)
   Each finding: title, evidence (exact request/response), impact, remediation, confirmation status
5. Asset inventory — domains, IPs, tech stack, versions
6. Positives — what the target does well
7. Appendices — raw outputs, references
