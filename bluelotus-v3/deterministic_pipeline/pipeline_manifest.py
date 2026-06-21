from __future__ import annotations

PIPELINE_VERSION = "v3.2-deterministic-pipeline"

STAGE_NAMES = [
    "Universe Selection",
    "Signal Quality",
    "Source Capacity",
    "Sleeve Rule",
    "PEI Event Gate",
    "STR Kelly",
    "Risk Overlay",
    "Target Vector",
    "CIO Review",
]


def stage_shell(name: str, input_keys: list[str], output_keys: list[str]) -> dict:
    return {
        "stage_name": name,
        "stage_version": PIPELINE_VERSION,
        "input_keys": input_keys,
        "output_keys": output_keys,
        "status": "PASS",
        "warnings": [],
        "errors": [],
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "orders_generated": 0,
    }

