from dataclasses import dataclass
from enum import Enum
from typing import List


class Status(Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


@dataclass(frozen=True)
class EvaluationResult:
    status: Status
    reasons: List[str]


def evaluate_scholarship(
    age: int,
    gpa: float,
    attendance_rate: float,
    has_required_courses: bool,
    disciplinary_record: bool
) -> EvaluationResult:
    _validate_inputs(gpa, attendance_rate)

    rejection_reasons = []
    review_reasons = []

    # Rule 1 - Age
    if age < 16:
        rejection_reasons.append("Applicant is younger than the minimum age.")
    elif age <= 17:
        review_reasons.append("Applicant is under 18 and requires manual review.")

    # Rule 2 - GPA
    if gpa < 6.0:
        rejection_reasons.append("GPA is below the minimum required.")
    elif gpa < 7.0:
        review_reasons.append("GPA is in the manual review range.")

    # Rule 3 - Attendance
    if attendance_rate < 75.0:
        rejection_reasons.append("Attendance rate is below the minimum required.")
    elif attendance_rate < 80.0:
        review_reasons.append("Attendance rate is in the manual review range.")

    # Rule 4 - Required courses
    if not has_required_courses:
        rejection_reasons.append("Required courses have not been completed.")

    # Rule 5 - Disciplinary record
    if disciplinary_record:
        rejection_reasons.append("Applicant has a disciplinary record.")

    # Final decision
    if rejection_reasons:
        return EvaluationResult(
            status=Status.REJECTED,
            reasons=rejection_reasons
        )

    if review_reasons:
        return EvaluationResult(
            status=Status.MANUAL_REVIEW,
            reasons=review_reasons
        )

    return EvaluationResult(
        status=Status.APPROVED,
        reasons=["Applicant meets all scholarship requirements."]
    )


def _validate_inputs(gpa: float, attendance_rate: float) -> None:
    if gpa < 0.0 or gpa > 10.0:
        raise ValueError("GPA must be between 0 and 10.")

    if attendance_rate < 0.0 or attendance_rate > 100.0:
        raise ValueError("Attendance rate must be between 0 and 100.")


if __name__ == "__main__":
    result = evaluate_scholarship(
        age=18,
        gpa=8.5,
        attendance_rate=92.0,
        has_required_courses=True,
        disciplinary_record=False
    )
    print(result)
