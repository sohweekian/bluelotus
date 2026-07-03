from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List

from .config_loader import ConfigError, env_bool, load_yaml_from_env


class PromptRejected(ValueError):
    pass


@dataclass
class GuardedPrompt:
    system_prompt: str
    user_prompt: str
    blocked: bool
    reasons: List[str]


def load_safety_policy() -> Dict:
    policy = load_yaml_from_env("LLM_SAFETY_POLICY_PATH")
    if not isinstance(policy.get("forbidden_terms"), list):
        raise ConfigError("Safety policy missing forbidden_terms list.")
    if not isinstance(policy.get("allowed_action_language"), list):
        raise ConfigError("Safety policy missing allowed_action_language list.")
    if not isinstance(policy.get("doctrine"), dict):
        raise ConfigError("Safety policy missing doctrine mapping.")
    return policy


def guard_prompt(system_prompt: str, user_prompt: str) -> GuardedPrompt:
    policy = load_safety_policy()
    allow_order_language = env_bool("LLM_ALLOW_ORDER_LANGUAGE", default=False)
    reasons = forbidden_term_matches([system_prompt, user_prompt], policy.get("forbidden_terms", []))
    doctrine = policy.get("doctrine", {})
    if doctrine.get("broker_execution_forbidden") is not True:
        reasons.append("Safety policy must forbid broker execution.")
    if doctrine.get("llm_order_generation_forbidden") is not True:
        reasons.append("Safety policy must forbid LLM order generation.")
    if reasons and not allow_order_language:
        raise PromptRejected("; ".join(reasons))
    return GuardedPrompt(
        system_prompt=build_doctrine_prefix(policy) + "\n\n" + system_prompt.strip(),
        user_prompt=user_prompt.strip(),
        blocked=False,
        reasons=[],
    )


def forbidden_term_matches(texts: Iterable[str], forbidden_terms: Iterable[str]) -> List[str]:
    combined = "\n".join(texts).lower()
    matches = []
    for term in forbidden_terms:
        needle = str(term).lower()
        if needle and has_non_negated_match(combined, needle):
            matches.append(f"Forbidden execution language detected: {term}")
    return matches


def has_non_negated_match(text: str, needle: str) -> bool:
    for match in re.finditer(re.escape(needle), text):
        prefix = text[max(0, match.start() - 40):match.start()]
        if any(marker in prefix for marker in ["must not", "do not", "may not", "never", "forbid", "forbidden", "not "]):
            continue
        return True
    return False


def build_doctrine_prefix(policy: Dict) -> str:
    allowed = ", ".join(str(x) for x in policy.get("allowed_action_language", []))
    return (
        "BlueLotus safety doctrine: analyze only; no broker execution; no order generation; "
        "deterministic operator blocks remain binding; CIO manual verification is required. "
        f"Allowed action language: {allowed}."
    )
