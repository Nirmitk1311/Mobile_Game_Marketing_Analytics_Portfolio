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

Before publishing, run `python src/privacy_scan.py`. The scanner checks text files for known confidential names, absolute local paths, email addresses and common credential patterns.
