from appointment_workflow import (
    AppointmentRequest,
    AppointmentStatus,
    decide_appointment,
    notification_messages,
)


def test_reschedule_keeps_existing_time_until_staff_confirms() -> None:
    request = AppointmentRequest(
        appointment_id="apt-2048",
        patient_first_name="Mina",
        action="reschedule",
        scheduled_for="2026-10-03 09:30 Asia/Shanghai",
        requested_time="2026-10-04 14:00 Asia/Shanghai",
    )

    decision = decide_appointment(request)
    messages = notification_messages(request, decision)

    assert decision.status is AppointmentStatus.NEEDS_SCHEDULING
    assert "existing appointment remains" in decision.operational_instruction
    assert "Staff must confirm" in decision.operational_instruction
    assert "needs_scheduling" in messages[1]["content"]
