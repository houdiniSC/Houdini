# nuclei

- Category: vulnerability scanning (template-driven)
- Detects: known CVEs, misconfigurations, exposures via YAML templates
- Usage: `nuclei -u <target> -t <templates> -severity high,critical`
- Templates: `~/nuclei-templates` (update with `nuclei -update-templates`)
- Limits: keep concurrency moderate (`-c 10`); batch targets
- Notes: excellent for breadth — validate every hit manually before reporting
