# BlueLotus V3

BlueLotus V3 is a research and documentation system for organizing market, portfolio, thesis, and scenario information.

The active LLM-facing role is the **Chief Clerk / Contradiction Mapper**. It is not a strategist, adviser, portfolio manager, execution agent, or decision-maker. Its job is to preserve source context, cite inputs, map contradictions, summarize readiness changes, and surface what still requires manual CIO review.

## Research-Only Notice

BlueLotus V3 is provided for research, documentation, contradiction mapping, and scenario organization only. It does not provide financial, legal, operational, medical, investment, safety, tax, or strategic advice.

Outputs may be incomplete, outdated, incorrect, or unsuitable for a specific situation. Users are solely responsible for independently verifying all information and for any decisions or actions they take.

BlueLotus V3 does not generate, route, place, or authorize orders. All actions require independent human review.

## Safety Posture

- `CIO_ONLY_MANUAL` is the execution doctrine.
- `ORDER_ROUTING_ENABLED` is false.
- `SYSTEM_ORDERS_GENERATED` must remain zero.
- LLM outputs are contradiction maps and summaries, not recommendations.
- Any apparent recommendation language is legacy compatibility text or a defect requiring cleanup.

## Key Generated Reports

Fresh reports are generated under:

```text
C:\bluelotus3\research\Bluelotus_V3_Report.txt
C:\bluelotus3\research\Bluelotus_V3_Report.docx
C:\bluelotus3\research\Bluelotus_V3_Report.xlsx
```

The report must include:

```text
CONTRADICTION MAP
READINESS CHANGE LOG
Situation Summary As-Is
```

## License And Disclaimer

See `LICENSE` and `DISCLAIMER.md` before using, modifying, or publishing this project.
