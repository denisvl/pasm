from src.pasm_automation import (
    AutomationEvent,
    EventType,
    FrameMetadata,
    InputTiming,
    ProtocolError,
    ProtocolEventEnvelope,
    ProtocolRequest,
    ProtocolResponse,
    TextCell,
    TextDelta,
    event_envelope_to_payload,
    event_to_jsonl,
    event_to_payload,
    parse_event_envelope,
    parse_event_payload,
    parse_jsonl_line,
    request_to_jsonl,
    request_to_payload,
    response_to_jsonl,
    response_to_payload,
)


def _sample_event() -> AutomationEvent:
    before = TextCell(
        native_code=0,
        unicode_codepoint=0xFFFD,
        text="\ufffd",
        glyph_id="ascii",
        foreground_color=-1,
        background_color=-1,
        attribute_flags=0,
        charset_id="ascii",
        source_address=0x0400,
        confidence=64,
    )
    after = TextCell(
        native_code=66,
        unicode_codepoint=66,
        text="B",
        glyph_id="ascii",
        foreground_color=-1,
        background_color=-1,
        attribute_flags=0,
        charset_id="ascii",
        source_address=0x0400,
        confidence=255,
    )
    return AutomationEvent(
        sequence_number=21,
        event_type=EventType.TEXT_CHANGED,
        frame=FrameMetadata(201, 45678, 0, 2),
        device_id="",
        control_id="",
        region_id="main",
        change_x=0,
        change_y=0,
        change_width=2,
        change_height=1,
        change_cell_count=1,
        input_action=0,
        input_timing=InputTiming.delay_frames(2),
        message="",
        text_deltas=(TextDelta(x=0, y=0, before=before, after=after),),
    )


def test_protocol_request_payload_and_jsonl():
    request = ProtocolRequest(
        id="req-1",
        method="machine.describe",
        params={"verbose": True},
        submitted_at="2026-07-28T12:00:00Z",
    )
    payload = request_to_payload(request)
    assert payload == {
        "id": "req-1",
        "protocol_version": 1,
        "method": "machine.describe",
        "params": {"verbose": True},
        "submitted_at": "2026-07-28T12:00:00Z",
    }
    encoded = request_to_jsonl(request)
    assert encoded.endswith("\n")
    assert parse_jsonl_line(encoded) == payload


def test_protocol_response_payload_and_jsonl():
    ok_response = ProtocolResponse(id=7, ok=True, result={"accepted": True})
    assert response_to_payload(ok_response) == {
        "id": 7,
        "ok": True,
        "result": {"accepted": True},
    }
    assert parse_jsonl_line(response_to_jsonl(ok_response)) == response_to_payload(ok_response)

    error_response = ProtocolResponse(
        id=8,
        ok=False,
        error=ProtocolError(
            code="unsupported",
            message="not supported",
            details={"method": "execution.pause"},
        ),
    )
    assert response_to_payload(error_response) == {
        "id": 8,
        "ok": False,
        "error": {
            "code": "unsupported",
            "message": "not supported",
            "details": {"method": "execution.pause"},
        },
    }
    assert parse_jsonl_line(response_to_jsonl(error_response)) == response_to_payload(error_response)


def test_protocol_event_payload_and_round_trip():
    event = _sample_event()
    payload = event_to_payload(event)
    assert payload["type"] == "text_changed"
    assert payload["frame"]["execution_state"] == "paused"
    assert payload["change"] == {
        "x": 0,
        "y": 0,
        "width": 2,
        "height": 1,
        "cell_count": 1,
    }
    assert payload["text_deltas"][0]["after"]["unicode_codepoint"] == 66
    assert payload["input_timing"] == {"kind": 3, "value": 2}

    parsed = parse_event_payload(payload)
    assert parsed == event


def test_protocol_execution_state_change_payload_and_round_trip():
    event = AutomationEvent(
        sequence_number=9,
        event_type=EventType.EXECUTION_STATE_CHANGED,
        frame=FrameMetadata(17, 900, 1200, 2),
        device_id="",
        control_id="",
        region_id="",
        change_x=0,
        change_y=0,
        change_width=0,
        change_height=0,
        change_cell_count=0,
        input_action=0,
        previous_execution_state=1,
        current_execution_state=2,
        input_timing=InputTiming.immediate(),
    )

    payload = event_to_payload(event)
    assert payload["type"] == "execution_state_changed"
    assert payload["execution_state_change"] == {"previous": 1, "current": 2}

    parsed = parse_event_payload(payload)
    assert parsed == event


def test_protocol_event_envelope_payload_and_round_trip():
    event = _sample_event()
    envelope = ProtocolEventEnvelope(
        event=event,
        stream="machine",
        timestamp="2026-07-28T12:01:00Z",
    )
    payload = event_envelope_to_payload(envelope)
    assert payload["kind"] == "event"
    assert payload["protocol_version"] == 1
    assert payload["timestamp"] == "2026-07-28T12:01:00Z"

    encoded = event_to_jsonl(event, timestamp="2026-07-28T12:01:00Z")
    parsed = parse_event_envelope(parse_jsonl_line(encoded))
    assert parsed.protocol_version == 1
    assert parsed.stream == "machine"
    assert parsed.timestamp == "2026-07-28T12:01:00Z"
    assert parsed.event == event


def test_protocol_parse_rejects_non_event_envelope():
    try:
        parse_event_envelope({"kind": "response", "event": {}})
    except ValueError as exc:
        assert "not an event envelope" in str(exc)
    else:
        raise AssertionError("expected ValueError")
