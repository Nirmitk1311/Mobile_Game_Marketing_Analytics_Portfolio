# Privacy design

This repository was built as a clean-room portfolio implementation.

- No original raw file is copied.
- No production identifier is transformed or hashed; all IDs are newly generated.
- Network, campaign, creative, product and company names are fictional.
- Dates were moved to a separate demonstration period.
- Financial values and outcomes are newly simulated.
- Business thresholds and recommendations are derived from the synthetic results.
- Scripts use relative paths and contain no workstation or employer paths.
- Reports contain no document author metadata.

## Daily pattern-only months (October 2025 onward)

Months from October 2025 are generated from aggregate patterns of a live, private pipeline, not by the clean-room generator. Safeguards:

- Only patterns are kept. Volumes, spend, revenue and retention levels are rescaled by secret random factors that are never published, and every row has added noise.
- Networks, campaigns and creatives receive fictional names. Countries are replaced by random region groups. Dates are moved back one year.
- Identifiers are new keyed hashes and cannot be traced back to any production identifier.
- Installs flagged as likely fraud are removed before the patterns are taken.
- Before every automated commit, all text files are checked against a private list of real names and identifiers built from the source data, and the scan below plus the unit tests must pass. Otherwise nothing is pushed.

Before publishing, run `python src/privacy_scan.py`. The scanner checks text files for known confidential names, absolute local paths, email addresses and common credential patterns.
