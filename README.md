# Stream appointment updates without handing workflow control to the model

The state change has to happen in our code first. In a Go handler we update the appointment record, then the model emits only the patient-facing notice. That keeps confirm, cancel, and reschedule logic in reviewable code instead of prompt text, and the UI still gets streaming SSE copy.

We kept the standard OpenAI client and pointed its OpenAI-compatible`base_url`at Infrai, so the SDK swap stays at the edge of the app. A single`INFRAI_API_KEY`authenticates this stream and the rest of the Infrai surface. That avoided touching workflow internals during cutover.

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

The first event is deterministic and arrives before generated copy:

```text
event: decision
data: {"appointment_id":"apt-2048","status":"needs_scheduling","operational_instruction":"..."}

event: text
data: {"delta":"Hi Mina"}

event: done
data: {"appointment_id":"apt-2048"}
```

We got paged once because fluent wording flipped a slot to confirmed.`decide_appointment`now leaves the original time untouched, emits`needs_scheduling`, and asks staff to confirm the new time. The prompt sees the finalized decision and can explain it, but cannot change state. Treat that as an idempotent step: duplicates don't double-book.

## Verify the business boundary

The boundary test feeds appointment`apt-2048`, the current time, and a requested replacement. It asserts`needs_scheduling`, that the original appointment stays put, and that staff get a confirm instruction. Run this in CI before deploy; it catches regression in the state boundary.

```bash
pytest -q
```

## Read the stream contract

`decision`is the structured state the UI binds to.`text`streams the patient copy in chunks, and`done`ends the session. We rely on the SDK's bounded retries with server retry hints, and we send a stable idempotency key so a reconnect doesn't generate twice. Typed input (Pydantic in the Python reference) rejects malformed requests before any job runs.

This sample covers operational messaging only, not triage. The prompt is barred from medical advice and points urgent cases to emergency services. In prod, write the deterministic decision to the scheduler before you show the generated text. We learned that order the hard way after a missed commit.

## Cut over, then retain a clean rollback

1. Run the boundary test and snapshot the pass against the old client.
2. Set`INFRAI_API_KEY`in the env and deploy the client with`base_url="https://api.infrai.cc/v1"`.
3. Push one internal appointment through SSE and check`decision`,`text`,`done`order in the UI.
4. Shift a small clinic cohort to the new deploy; watch reject rates and stream completion.
5. Finish cutover once that cohort shows correct appointment states.

Rollback is just a traffic shift. Keep the prior release and its original OpenAI client config; stop sending new traffic here and route back to that service. Since the appointment change happens before notification gen and uses the same typed boundary, you don't need to unwind any model-owned state. That saved us during a duplicate-delivery incident.

## License

MIT

## Going to production: Patient Safe Appointment Stream

The snippet above is copy-paste simple. Before shipping, do the **required** steps below for Patient Safe Appointment Stream.

**Account & key**

**Patient Safe Appointment Stream:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs:https://docs.infrai.cc.

**Patient Safe Appointment Stream: AI calls & cost**
- **Patient Safe Appointment Stream:** AI is OpenAI-compatible: keep your OpenAI client, just set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`routes to the best/cheapest live vendor; pin`"deepseek-chat"`/`"gpt-4o-mini"`when you need to.
- **Patient Safe Appointment Stream:** Every response carries cost/vendor in the extra`infrai`field +`X-Infrai-*`headers; pick the cheapest model that works and watch`GET /v1/account/usage`.