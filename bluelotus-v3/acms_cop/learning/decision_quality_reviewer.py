from __future__ import annotations


DECISION_QUALITY_CLASSES = {
    "PENDING_REVIEW",
    "CORRECT_PROCESS_CORRECT_OUTCOME",
    "CORRECT_PROCESS_WRONG_OUTCOME",
    "WRONG_PROCESS_CORRECT_OUTCOME",
    "WRONG_PROCESS_WRONG_OUTCOME",
    "LUCKY_WIN",
    "AVOIDABLE_MISTAKE",
    "UNKNOWABLE_OUTCOME",
    "DATA_QUALITY_FAILURE",
    "EXECUTION_DISCIPLINE_SUCCESS",
    "EXECUTION_DISCIPLINE_FAILURE",
}


def classify_decision_quality(process_correct: bool | None, outcome_positive: bool | None, discipline_success: bool | None = None) -> str:
    if discipline_success is True:
        return "EXECUTION_DISCIPLINE_SUCCESS"
    if discipline_success is False:
        return "EXECUTION_DISCIPLINE_FAILURE"
    if process_correct is None or outcome_positive is None:
        return "PENDING_REVIEW"
    if process_correct and outcome_positive:
        return "CORRECT_PROCESS_CORRECT_OUTCOME"
    if process_correct and not outcome_positive:
        return "CORRECT_PROCESS_WRONG_OUTCOME"
    if not process_correct and outcome_positive:
        return "WRONG_PROCESS_CORRECT_OUTCOME"
    return "WRONG_PROCESS_WRONG_OUTCOME"

