import pytest

from acms_cop.classifiers.confirmation_gate_classifier import enforce_execution_safety


def test_execution_safety_hard_fails_on_bad_authority():
    with pytest.raises(ValueError):
        enforce_execution_safety({"execution_authority": "AUTO", "order_routing_enabled": False, "llm_order_generation_enabled": False, "system_generated_orders": 0})


def test_execution_safety_hard_fails_on_routing_or_generated_orders():
    with pytest.raises(ValueError):
        enforce_execution_safety({"execution_authority": "CIO_ONLY_MANUAL", "order_routing_enabled": True, "llm_order_generation_enabled": False, "system_generated_orders": 0})
    with pytest.raises(ValueError):
        enforce_execution_safety({"execution_authority": "CIO_ONLY_MANUAL", "order_routing_enabled": False, "llm_order_generation_enabled": True, "system_generated_orders": 0})
    with pytest.raises(ValueError):
        enforce_execution_safety({"execution_authority": "CIO_ONLY_MANUAL", "order_routing_enabled": False, "llm_order_generation_enabled": False, "system_generated_orders": 1})

