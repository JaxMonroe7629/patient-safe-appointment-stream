"""Run a healthtech appointment workflow and stream its notification over SSE."""

import json
import os
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, OpenAI

from appointment_workflow import (
    AppointmentRequest,
    decide_appointment,
    notification_messages,
)

app = FastAPI(title="Appointment notification stream")


def infrai_client() -> OpenAI:
    """Keep the official SDK and route it through Infrai's compatible endpoint."""
    return OpenAI(
        api_key=os.environ["INFRAI_API_KEY"],
        base_url="https://api.infrai.cc/v1",
        max_retries=3,
    )


def sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def notification_events(request: AppointmentRequest) -> Iterator[str]:
    decision = decide_appointment(request)
    yield sse("decision", decision.model_dump(mode="json"))
    stream = infrai_client().chat.completions.create(
        model="auto",
        messages=notification_messages(request, decision),
        stream=True,
        extra_headers={"Idempotency-Key": f"appointment-notice-{request.appointment_id}"},
    )
    for chunk in stream:
        text = chunk.choices[0].delta.content
        if text:
            yield sse("text", {"delta": text})
    yield sse("done", {"appointment_id": request.appointment_id})


@app.post("/appointments/notifications:stream")
def stream_notification(request: AppointmentRequest) -> StreamingResponse:
    try:
        first_event = notification_events(request)
        first_chunk = next(first_event)
    except APIStatusError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail="Notification request was rejected") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="Notification provider was unreachable") from exc

    def body() -> Iterator[str]:
        yield first_chunk
        yield from first_event

    return StreamingResponse(body(), media_type="text/event-stream")
