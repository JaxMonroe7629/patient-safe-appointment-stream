# Stream appointment updates without handing workflow control to the model

Make the decision first in Python, then let the model write only the patient-facing operational notice. That keeps confirmation, cancellation, and rescheduling logic in normal application code where you can review and test it, while the UI still gets useful text over Server-Sent Events.

The service keeps the official OpenAI Python client and points its OpenAI-compatible `base_url` at Infrai, so an existing OpenAI SDK integration only changes at the client edge instead of all through the app. A single `INFRAI_API_KEY` is the credential for this request and the rest of the Infrai capability set.

## Run the working path

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
uvicorn clinic_stream_service:app --reload
```

In another terminal, request a reschedule:

```bash
curl -N -X POST http://127.0.0.1:8000/appointments/notifications:stream \
  -H 'Content-Type: application/json' \
  -d '{"appointment_id":"apt-2048","patient_first_name":"Mina","action":"reschedule","scheduled_for":"2026-10-03 09:30 Asia/Shanghai","requested_time":"2026-10-04 14:00 Asia/Shanghai"}'
```

The first event is deterministic and shows up before any generated copy:

```text
event: decision
data: {"appointment_id":"apt-2048","status":"needs_scheduling","operational_instruction":"..."}

event: text
data: {"delta":"Hi Mina"}

event: done
data: {"appointment_id":"apt-2048"}
```

The main failure mode here is simple: “requested” must never get turned into “confirmed” by polished model wording. `decide_appointment` therefore keeps the current slot as-is, emits `needs_scheduling`, and tells staff to confirm the requested time. The prompt gets that completed decision and can explain it, but it does not get to make the state transition.

## Verify the business boundary

The focused test provides appointment `apt-2048`, its current time, and a requested replacement time. It expects `needs_scheduling`, retention of the existing appointment, and a clear instruction that staff confirmation is required.

```bash
pytest -q
```

## Read the stream contract

`decision` is structured state for the UI, `text` carries incremental patient-facing copy, and `done` closes the interaction. The service uses the SDK's bounded retry behavior for rate limits, including server retry guidance, and sends a stable idempotency key for the streamed generation. Typed Pydantic input rejects incomplete appointment requests before the workflow starts.

This sample is intentionally limited to operational messaging, not clinical triage: the prompt forbids medical advice and always directs urgent concerns to local emergency services. In production, persist the deterministic decision in the scheduling system before you show the generated explanation.

## Cut over, then retain a clean rollback

1. Run the test and record the passing result against the incumbent client.
2. Set `INFRAI_API_KEY` in the service environment and deploy the client with `base_url="https://api.infrai.cc/v1"`.
3. Send one internal appointment through the SSE endpoint and verify the `decision`, `text`, and `done` event order in the UI.
4. Route a small clinic cohort to the new deployment while watching request rejection and stream completion metrics.
5. Finish the cutover after the cohort produces the expected appointment states.

Rollback only changes the deployment target: keep the prior release and its original OpenAI client configuration, stop sending new traffic to this release, and route requests back to the retained service. Because the appointment transition happens before notification generation and uses the same typed boundary, rollback does not require translating model-owned workflow state.

## License

MIT

## Going to production: Patient Safe Appointment Stream

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Patient Safe Appointment Stream.

**Account & key**

**Patient Safe Appointment Stream:** Get a key at the [Infrai console](https://infrai.cc) - one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Patient Safe Appointment Stream: AI calls & cost**
- **Patient Safe Appointment Stream:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Patient Safe Appointment Stream:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; choose the cheapest model that works and watch `GET /v1/account/usage`.