# Security And Sanitization

This repository is a sanitized public version of the BlueLotus V3 research platform.

Excluded categories:

- `.env` files and local credentials.
- Live broker account metadata.
- Direct order-routing scripts and working order books.
- Raw `data/` snapshots, generated datasets, and execution state.
- Local database files and editor indexes.
- Logs, caches, temporary files, and replay/archive outputs.
- Generated portfolio reports containing current private account values.

If you discover credentials, account IDs, private portfolio data, or live execution instructions in this repository, remove them immediately and rotate any affected secrets.

BlueLotus V3 is designed as a decision-support and research system. It should not be used as autonomous trading software.

