from __future__ import annotations

import json
from pathlib import Path

from src.pasm_automation.terminal_client import main
from tests.test_python_automation_binding import _compile_mock_shared


def test_terminal_client_prints_machine_info(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main([str(shared), "--create-symbol", "emu_test_create_text_machine", "machine-info"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "machine_id: mock-machine" in output
    assert "system_id: mock-system" in output


def test_terminal_client_prints_screen_text(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main(
        [str(shared), "--create-symbol", "emu_test_create_text_machine", "screen-text", "--region-id", "main"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "region_id: main\nframe_number: 0\n---\nWX\nYZ\n"


def test_terminal_client_wait_text_emits_json(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main(
        [
            str(shared),
            "--create-symbol",
            "emu_test_create_text_machine",
            "--json",
            "wait-text",
            "AB",
            "--region-id",
            "main",
            "--timeout-frames",
            "3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["region_id"] == "main"
    assert payload["plain"] == "AB\nCD"
    assert payload["frame_number"] == 3


def test_terminal_client_polls_category_event_json(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main(
        [
            str(shared),
            "--create-symbol",
            "emu_test_create_category_machine",
            "--json",
            "poll-event",
            "--event-type",
            "debug_message",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"]["type"] == "debug_message"
    assert payload["event"]["message"] == "debug trace"


def test_terminal_client_screen_prefers_text_grid(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main([str(shared), "--create-symbol", "emu_test_create_text_machine", "screen"])

    assert exit_code == 0
    assert capsys.readouterr().out == "region_id: main\nframe_number: 0\n---\nWX\nYZ\n"


def test_terminal_client_screen_framebuffer_saves_png(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)
    output = tmp_path / "frame.png"

    exit_code = main(
        [
            str(shared),
            "--create-symbol",
            "emu_test_create_text_machine",
            "screen-framebuffer",
            "--save-png",
            str(output),
        ]
    )

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "width: 2" in stdout
    assert "preview:" in stdout
    assert "000102 040506" in stdout
    assert "08090a 0c0d0e" in stdout
    assert f"saved_png: {output}" in stdout
    assert output.exists()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_terminal_client_events_watch_json_for_category_machine(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main(
        [
            str(shared),
            "--create-symbol",
            "emu_test_create_category_machine",
            "--json",
            "events-watch",
            "--limit",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert [event["type"] for event in payload["events"]] == ["media_activity", "debug_message"]


def test_terminal_client_events_watch_advances_frames_for_text_changed(tmp_path, capsys):
    shared = _compile_mock_shared(tmp_path)

    exit_code = main(
        [
            str(shared),
            "--create-symbol",
            "emu_test_create_text_machine",
            "--json",
            "events-watch",
            "--event-type",
            "text_changed",
            "--limit",
            "1",
            "--timeout-frames",
            "3",
            "--step-frames",
            "1",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["events"]) == 1
    assert payload["events"][0]["type"] == "text_changed"
    assert payload["events"][0]["region_id"] == "main"
