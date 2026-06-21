# BlueLotus V3 CIO Context Capsule

The CIO Context Capsule is the portable institutional memory layer for BlueLotus V3.

It is built by:

```powershell
python C:\bluelotus3\build_cio_context_capsule.py
```

It embeds `cio_context_capsule` into:

```text
C:\bluelotus3\data\frontend\dataset_raw.json
```

It also writes:

```text
C:\bluelotus3\data\cio_context\cio_context_capsule_latest.json
C:\bluelotus3\data\cio_context\cio_context_capsule_history.jsonl
```

Reports consume the capsule and render it visibly in:

```text
C:\bluelotus3\research\Bluelotus_V3_Report.txt
C:\bluelotus3\research\Bluelotus_V3_Report.docx
C:\bluelotus3\research\Bluelotus_V3_Report.xlsx
```

The validator checks the dataset and rendered artifacts:

```powershell
python C:\bluelotus3\validate_cio_context_capsule.py
```

Governing rule:

```text
No Chief Strategist answer may be produced from tactical data alone.
```
