"""Deterministic appointment decisions and patient-safe notification context."""

from enum import Enum

from pydantic import BaseModel, Field


class AppointmentAction(str, Enum):
    CONFIRM = "confirm"
    RESCHEDULE = "reschedule"
    CANCEL = "cancel"


class AppointmentStatus(str, Enum):
    CONFIRMED = "confirmed"
    NEEDS_SCHEDULING = "needs_scheduling"
    CANCELLED = "cancelled"


class AppointmentRequest(BaseModel):
    appointment_id: str = Field(min_length=1, max_length=80)
    patient_first_name: str = Field(min_length=1, max_length=80)
    action: AppointmentAction
    scheduled_for: str = Field(min_length=1, max_length=120)
    requested_time: str | None = Field(default=None, max_length=120)


class AppointmentDecision(BaseModel):
    appointment_id: str
    status: AppointmentStatus
    operational_instruction: str


def decide_appointment(request: AppointmentRequest) -> AppointmentDecision:
    """Apply the workflow transition before any model-generated wording is shown."""
    if request.action is AppointmentAction.RESCHEDULE:
        return AppointmentDecision(
            appointment_id=request.appointment_id,
            status=AppointmentStatus.NEEDS_SCHEDULING,
            operational_instruction=(
                f"The existing appointment remains at {request.scheduled_for}. "
                f"The requested time is {request.requested_time or 'not specified'}. "
                "Staff must confirm a new time before the patient changes plans."
            ),
        )
    if request.action is AppointmentAction.CANCEL:
        return AppointmentDecision(
            appointment_id=request.appointment_id,
            status=AppointmentStatus.CANCELLED,
            operational_instruction=(
                f"The appointment at {request.scheduled_for} is cancelled. "
                "Tell the patient to contact the clinic if this was unexpected."
            ),
        )
    return AppointmentDecision(
        appointment_id=request.appointment_id,
        status=AppointmentStatus.CONFIRMED,
        operational_instruction=(
            f"The appointment remains confirmed for {request.scheduled_for}. "
            "Ask the patient to contact the clinic for scheduling changes."
        ),
    )


def notification_messages(
    request: AppointmentRequest, decision: AppointmentDecision
) -> list[dict[str, str]]:
    """Build constrained copy instructions while preserving the deterministic decision."""
    return [
        {
            "role": "system",
            "content": (
                "Write a brief operational appointment notification. Repeat the supplied "
                "status and instruction accurately. Do not give medical advice, interpret "
                "symptoms, or imply that a requested time is confirmed. End with: For urgent "
                "medical concerns, contact local emergency services."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Patient first name: {request.patient_first_name}\n"
                f"Appointment ID: {decision.appointment_id}\n"
                f"Status: {decision.status.value}\n"
                f"Instruction: {decision.operational_instruction}"
            ),
        },
    ]
