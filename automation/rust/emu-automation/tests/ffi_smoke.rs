use emu_automation::{sys, InputSequence, Library, Machine, Timing, WaitError, WaitTimeoutError};
use std::path::{Path, PathBuf};
use std::process::Command;


unsafe extern "C" {
    fn emu_test_create_text_machine(
        out_machine: *mut *mut sys::emu_automation_machine_t,
    ) -> sys::emu_automation_result_t;
    fn emu_test_create_category_machine(
        out_machine: *mut *mut sys::emu_automation_machine_t,
    ) -> sys::emu_automation_result_t;
}

#[test]
fn rust_wrapper_drives_mock_machine_over_c_abi() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let descriptor = machine.describe().expect("describe");
    assert_eq!(descriptor.machine_id, "mock-rust-machine");
    assert_eq!(descriptor.system_id, "mock-system");
    assert_eq!(
        machine.character_mappings().expect("character mappings"),
        vec![
            emu_automation::CharacterMappingDescriptor {
                device_id: "keyboard".to_string(),
                unicode_codepoint: 65,
                native_code: 65,
                key_id: "K_A".to_string(),
                required_modifier_bits: sys::EMU_AUTOMATION_KEY_MODIFIER_SHIFT,
                shift_key_id: "K_SHIFT".to_string(),
                ctrl_key_id: "".to_string(),
                alt_key_id: "".to_string(),
                meta_key_id: "".to_string(),
            },
            emu_automation::CharacterMappingDescriptor {
                device_id: "keyboard".to_string(),
                unicode_codepoint: 13,
                native_code: 13,
                key_id: "K_RETURN".to_string(),
                required_modifier_bits: 0,
                shift_key_id: "K_SHIFT".to_string(),
                ctrl_key_id: "".to_string(),
                alt_key_id: "".to_string(),
                meta_key_id: "".to_string(),
            },
        ]
    );

    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.resume().expect("resume");
    machine.run().frame().expect("step frame");
    machine.run().frames(41).expect("run frames");
    machine.pause().expect("pause");
    machine
        .keyboard()
        .tap("RETURN", None, None)
        .expect("tap key");
    machine
        .controller()
        .press("fire_1", Some("joystick_port_1"))
        .expect("controller button");

    let framebuffer = machine.screen().framebuffer().expect("framebuffer");
    assert_eq!(framebuffer.width, 2);
    assert_eq!(framebuffer.height, 2);
    assert_eq!(framebuffer.frame.frame_number, 42);
    assert_eq!(framebuffer.pixels[0], 42);

    let views = machine.screen().text_views().expect("text views");
    assert_eq!(views.len(), 1);
    assert_eq!(views[0].region_id, "main");

    let text = machine
        .screen()
        .wait_for_text("AB", Some("main"), 1, 1)
        .expect("text grid");
    assert_eq!(text.plain, "AB\nCD");
    assert_eq!(text.frame.frame_number, 42);
    assert_eq!(text.cells[0].text, "A");
    assert_eq!(text.cells[3].source_address, 0x0403);
}

#[test]
fn rust_keyboard_type_text_uses_character_mappings() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .keyboard()
        .type_text("A\r", None, None)
        .expect("type text");

    let mut seen = Vec::new();
    let mut after_sequence = 0u64;
    while let Some(event) = machine.poll_event(after_sequence).expect("poll event") {
        after_sequence = event.sequence_number;
        if event.event_type == sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED
        {
            seen.push((event.control_id, event.input_action));
        }
    }

    assert_eq!(
        seen,
        vec![
            (
                "K_SHIFT".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_A".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_A".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
            (
                "K_SHIFT".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
            (
                "K_RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
        ]
    );
}

#[test]
fn rust_input_sequence_type_text_uses_character_mappings() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let mut sequence = InputSequence::new();
    sequence
        .type_text(&machine, "A\r", None, emu_automation::TapTimingPreset::immediate())
        .expect("sequence type text");
    sequence.play(&machine).expect("play sequence");

    let mut seen = Vec::new();
    let mut after_sequence = 0u64;
    while let Some(event) = machine.poll_event(after_sequence).expect("poll event") {
        after_sequence = event.sequence_number;
        if event.event_type == sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED
        {
            seen.push((event.control_id, event.input_action));
        }
    }

    assert_eq!(
        seen,
        vec![
            (
                "K_SHIFT".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_A".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_A".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
            (
                "K_SHIFT".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
            (
                "K_RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
            ),
            (
                "K_RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
            ),
        ]
    );
}

#[test]
fn rust_wrapper_times_out_waiting_for_missing_text() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    let error = machine
        .screen()
        .wait_for_text("NEVER", Some("main"), 2, 1)
        .expect_err("wait should time out");
    assert_eq!(
        error,
        WaitError::Timeout(WaitTimeoutError {
            description: "text \"NEVER\"".to_string(),
            frames_elapsed: 2,
            last_observation: Some("text frame=2 plain=\"WX\\nYZ\"".to_string()),
        })
    );
}

#[test]
fn rust_waits_for_text_disappearance() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    let snapshot = machine
        .screen()
        .wait_for_text_disappearance("WX", Some("main"), 3, 1)
        .expect("text disappearance");
    assert_eq!(snapshot.plain, "AB\nCD");
    assert_eq!(snapshot.frame.frame_number, 3);
}

#[test]
fn rust_reads_memory_and_waits_for_memory_value() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    assert_eq!(machine.read_memory(0x0200, 2).expect("read memory"), vec![0x00, 0x99]);

    let current = machine
        .wait_for_memory_value(0x0200, &[0x42, 0x99], 3, 1)
        .expect("wait for memory");
    assert_eq!(current, vec![0x42, 0x99]);

    let error = machine
        .wait_for_memory_value(0x0200, &[0x43], 2, 1)
        .expect_err("wait should time out");
    assert_eq!(
        error,
        WaitError::Timeout(WaitTimeoutError {
            description: "memory 0x200 == 43".to_string(),
            frames_elapsed: 2,
            last_observation: Some("42".to_string()),
        })
    );

    machine.write_memory(0x0200, &[0x55, 0x66]).expect("write memory");
    assert_eq!(machine.read_memory(0x0200, 2).expect("read memory"), vec![0x55, 0x66]);
    assert_eq!(machine.read_program_counter().expect("pc"), 0x0205);
    assert_eq!(machine.read_frame_metadata().expect("metadata").frame_number, 5);
    let instruction = machine.read_current_instruction().expect("instruction");
    assert_eq!(instruction.address, 0x0205);
    assert_eq!(instruction.text, "NOP");
    let registers = machine.read_registers().expect("registers");
    assert_eq!(registers[0].name, "PC");
    assert_eq!(registers[0].hex_value, "0x0205");
    machine.write_register("PC", 0x0333).expect("write register");
    assert_eq!(machine.read_program_counter().expect("pc"), 0x0333);
}

#[test]
fn rust_wrapper_propagates_wait_predicate_automation_error() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let error = machine
        .screen()
        .wait_for_text("AB", Some("missing"), 1, 1)
        .expect_err("wait should fail");
    match error {
        WaitError::Automation(error) => {
            assert_eq!(
                error.code,
                sys::emu_automation_result_t::EMU_AUTOMATION_UNSUPPORTED
            );
            assert_eq!(error.operation, "emu_automation_screen_text_grid");
        }
        WaitError::Timeout(error) => panic!("unexpected timeout: {error}"),
    }
}

#[test]
fn rust_input_sequence_replays_steps_over_machine_api() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    let mut sequence = InputSequence::new();
    sequence
        .key_down("RETURN", None, Timing::Immediate)
        .wait_frames(5)
        .key_up("RETURN", None, Timing::DelayFrames(1))
        .controller_down("fire_1", Some("joystick_port_1"), Timing::Frame(12));
    sequence.play(&machine).expect("play sequence");

    let framebuffer = machine.screen().framebuffer().expect("framebuffer");
    assert_eq!(framebuffer.frame.frame_number, 5);
}

#[test]
fn rust_tap_timing_preset_replays_press_and_release_timing() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let mut sequence = InputSequence::new();
    sequence.tap_key_with_preset("RETURN", None, emu_automation::TapTimingPreset::hold_frames(2));
    sequence.play(&machine).expect("play sequence");

    assert_eq!(machine.keyboard().release_all(None).expect("release keys"), 0);
}

#[test]
fn rust_controller_tap_timing_preset_replays_press_and_release_timing() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let mut sequence = InputSequence::new();
    sequence.tap_controller_with_preset(
        "fire_1",
        Some("joystick_port_1"),
        emu_automation::TapTimingPreset::hold_frames(2),
    );
    sequence.play(&machine).expect("play sequence");

    assert_eq!(
        machine
            .controller()
            .release_all(Some("joystick_port_1"))
            .expect("release buttons"),
        0
    );
}

#[test]
fn rust_releases_tracked_inputs() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .keyboard()
        .press("RETURN", None)
        .expect("press key");
    machine
        .controller()
        .press("fire_1", Some("joystick_port_1"))
        .expect("press button");

    assert_eq!(machine.keyboard().release_all(None).expect("release keys"), 1);
    assert_eq!(
        machine
            .controller()
            .release_all(Some("joystick_port_1"))
            .expect("release buttons"),
        1
    );
    assert_eq!(machine.keyboard().release_all(None).expect("release keys again"), 0);
    assert_eq!(
        machine
            .controller()
            .release_all(Some("joystick_port_1"))
            .expect("release buttons again"),
        0
    );
}

#[test]
fn rust_input_sequence_replays_release_all_steps() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let mut sequence = InputSequence::new();
    sequence
        .key_down("RETURN", None, Timing::Immediate)
        .release_all_keys(None)
        .controller_down("fire_1", Some("joystick_port_1"), Timing::Immediate)
        .release_all_controller_buttons(Some("joystick_port_1"));
    sequence.play(&machine).expect("play sequence");

    assert_eq!(machine.keyboard().release_all(None).expect("post-release keys"), 0);
    assert_eq!(
        machine
            .controller()
            .release_all(Some("joystick_port_1"))
            .expect("post-release buttons"),
        0
    );
}

#[test]
fn rust_input_sequence_jsonl_round_trips_and_replays() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let mut sequence = InputSequence::new();
    sequence
        .key_down("RETURN", None, Timing::Frame(12))
        .wait_frames(3)
        .key_up("RETURN", None, Timing::DelayFrames(1))
        .controller_down("fire_1", Some("joystick_port_1"), Timing::Cycle(99))
        .release_all_controller_buttons(Some("joystick_port_1"));

    let jsonl = sequence.to_jsonl();
    let replayed = InputSequence::from_jsonl(&jsonl).expect("decode jsonl");
    assert_eq!(replayed.steps(), sequence.steps());

    replayed.play(&machine).expect("play sequence");
    assert_eq!(
        machine
            .controller()
            .release_all(Some("joystick_port_1"))
            .expect("post-release buttons"),
        0
    );
}

#[test]
fn rust_input_sequence_jsonl_replay_is_deterministic() {
    fn capture_schedule() -> Vec<(u64, u64, String, sys::emu_automation_input_action_t, Timing)> {
        let mut raw = std::ptr::null_mut();
        let result = unsafe { emu_test_create_text_machine(&mut raw) };
        assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);
        let machine = Machine::from_raw_owned(raw).expect("null machine");

        let mut sequence = InputSequence::new();
        sequence
            .key_down("RETURN", None, Timing::Frame(12))
            .wait_frames(3)
            .key_up("RETURN", None, Timing::DelayFrames(1))
            .controller_down("fire_1", Some("joystick_port_1"), Timing::Cycle(99));
        let replayed = InputSequence::from_jsonl(&sequence.to_jsonl()).expect("decode jsonl");
        replayed.play(&machine).expect("play sequence");

        let mut schedule = Vec::new();
        let mut after_sequence = 0u64;
        while let Some(event) = machine.screen().poll_event(after_sequence).expect("poll event") {
            after_sequence = event.sequence_number;
            if event.event_type == sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED
            {
                schedule.push((
                    event.sequence_number,
                    event.frame.frame_number,
                    event.control_id,
                    event.input_action,
                    event.input_timing,
                ));
            }
        }
        schedule
    }

    let schedule_a = capture_schedule();
    let schedule_b = capture_schedule();
    assert_eq!(schedule_a, schedule_b);
    assert_eq!(
        schedule_a,
        vec![
            (
                1,
                0,
                "RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                Timing::Frame(12),
            ),
            (
                7,
                3,
                "RETURN".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_RELEASE,
                Timing::DelayFrames(1),
            ),
            (
                8,
                3,
                "fire_1".to_string(),
                sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS,
                Timing::Cycle(99),
            ),
        ]
    );
}

#[test]
fn rust_wrapper_waits_for_stable_text_and_framebuffer() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.run().frames(3).expect("advance to stable text");

    let text = machine
        .screen()
        .wait_for_stable_text(Some("main"), 2, 4, 1)
        .expect("stable text");
    assert_eq!(text.plain, "AB\nCD");
    assert_eq!(text.frame.frame_number, 5);

    let framebuffer = machine
        .screen()
        .wait_for_stable_framebuffer(0, 2, 1)
        .expect("immediate framebuffer");
    assert_eq!(framebuffer.frame.frame_number, 5);

    let framebuffer_error = machine
        .screen()
        .wait_for_stable_framebuffer(2, 2, 1)
        .expect_err("framebuffer should keep changing");
    assert_eq!(
        framebuffer_error,
        WaitError::Timeout(WaitTimeoutError {
            description: "stable framebuffer".to_string(),
            frames_elapsed: 2,
            last_observation: Some(
                "framebuffer frame=7 size=2x2 format=EMU_AUTOMATION_PIXEL_FORMAT_RGBA8888"
                    .to_string(),
            ),
        })
    );

    let error = machine
        .screen()
        .wait_for_stable_text(Some("main"), 3, 2, 1)
        .expect_err("stable text should time out");
    assert_eq!(
        error,
        WaitError::Timeout(WaitTimeoutError {
            description: "stable text in main".to_string(),
            frames_elapsed: 2,
            last_observation: Some("text frame=9 plain=\"AB\\nCD\"".to_string()),
        })
    );
}

#[test]
fn rust_condition_layer_composes_waits() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    let text = machine
        .wait()
        .until(
            machine
                .conditions()
                .screen_contains("READY", Some("main"))
                .or(machine.conditions().screen_contains("AB", Some("main"))),
            3,
            1,
        )
        .expect("any condition");
    assert_eq!(text.plain, "AB\nCD");
    assert_eq!(text.frame.frame_number, 3);

    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    let (stable_text, memory) = machine
        .wait()
        .until(
            machine
                .conditions()
                .stable_text(Some("main"), 2)
                .and(machine.conditions().memory_value(0x0200, [0x42, 0x99])),
            5,
            1,
        )
        .expect("all conditions");
    assert_eq!(stable_text.plain, "AB\nCD");
    assert_eq!(stable_text.frame.frame_number, 5);
    assert_eq!(memory, vec![0x42, 0x99]);
}

#[test]
fn rust_wrapper_polls_frame_events() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    let reset = machine.screen().poll_event(0).expect("poll").expect("event");
    assert_eq!(reset.sequence_number, 1);
    assert_eq!(
        reset.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET
    );
    assert_eq!(reset.frame.frame_number, 0);

    machine.run().frames(2).expect("run frames");
    let first = machine.screen().poll_event(1).expect("poll").expect("event");
    assert_eq!(first.sequence_number, 2);
    assert_eq!(
        first.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED
    );
    assert_eq!(first.frame.frame_number, 1);
    assert_eq!(
        first.frame.execution_state,
        sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_PAUSED
    );

    let second = machine.screen().poll_event(2).expect("poll").expect("event");
    assert_eq!(second.sequence_number, 3);
    assert_eq!(second.frame.frame_number, 2);

    machine.resume().expect("resume");
    let resumed = machine.screen().poll_event(3).expect("poll").expect("event");
    assert_eq!(resumed.sequence_number, 4);
    assert_eq!(
        resumed.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED
    );
    assert_eq!(
        resumed.frame.execution_state,
        sys::emu_automation_execution_state_t::EMU_AUTOMATION_EXECUTION_RUNNING
    );

    machine
        .keyboard()
        .press("RETURN", None)
        .expect("input event");
    let input = machine.screen().poll_event(4).expect("poll").expect("event");
    assert_eq!(input.sequence_number, 5);
    assert_eq!(
        input.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED
    );
    assert_eq!(input.control_id, "RETURN");
    assert_eq!(
        input.input_action,
        sys::emu_automation_input_action_t::EMU_AUTOMATION_INPUT_PRESS
    );
    assert_eq!(input.input_timing, Timing::Immediate);
    assert_eq!(input.input_accepted.frame_number, 2);
    assert_eq!(input.input_applied.frame_number, 2);
    assert_eq!(machine.screen().poll_event(5).expect("poll"), None);
}

#[test]
fn rust_event_poller_drains_available_events() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.run().frames(2).expect("run frames");

    let mut poller = machine.screen().events(0);
    let events = poller.collect_available().expect("collect");
    assert_eq!(
        events.iter().map(|event| event.sequence_number).collect::<Vec<_>>(),
        vec![1, 2, 3]
    );
    assert_eq!(
        events.iter().map(|event| event.event_type).collect::<Vec<_>>(),
        vec![
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET,
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
        ]
    );
    assert_eq!(poller.after_sequence(), 3);
    assert_eq!(poller.poll_next().expect("poll"), None);

    machine.resume().expect("resume");
    machine
        .keyboard()
        .press("RETURN", None)
        .expect("press key");
    let follow_up = poller.collect_available().expect("collect");
    assert_eq!(
        follow_up
            .iter()
            .map(|event| event.sequence_number)
            .collect::<Vec<_>>(),
        vec![4, 5]
    );
    assert_eq!(
        follow_up.iter().map(|event| event.event_type).collect::<Vec<_>>(),
        vec![
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_EXECUTION_STATE_CHANGED,
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_INPUT_SUBMITTED,
        ]
    );
}

#[test]
fn rust_event_poller_dispatches_callbacks() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.run().frames(2).expect("run frames");

    let mut poller = machine.screen().events(0);
    let mut seen = Vec::new();
    let count = poller
        .dispatch_available(|event| seen.push((event.sequence_number, event.event_type)))
        .expect("dispatch");
    assert_eq!(count, 3);
    assert_eq!(
        seen,
        vec![
            (
                1,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET,
            ),
            (
                2,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
            (
                3,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
        ]
    );
    assert_eq!(poller.after_sequence(), 3);
}

#[test]
fn rust_event_poller_dispatches_matching_callbacks() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.run().frames(2).expect("run frames");

    let mut poller = machine.screen().events(0);
    let mut seen = Vec::new();
    let count = poller
        .dispatch_matching(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            0,
            |event| seen.push((event.sequence_number, event.event_type)),
        )
        .expect("dispatch matching");
    assert_eq!(count, 2);
    assert_eq!(
        seen,
        vec![
            (
                2,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
            (
                3,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
        ]
    );
    assert_eq!(poller.after_sequence(), 3);
}

#[test]
fn rust_subscription_dispatches_matching_events() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    machine.run().frames(2).expect("run frames");

    let mut seen = Vec::new();
    {
        let mut subscription = machine
            .screen()
            .subscribe(
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
                0,
                |event| seen.push((event.sequence_number, event.event_type)),
            )
            .expect("subscribe");
        assert_eq!(subscription.after_sequence(), 0);
        let count = subscription.dispatch_available(0).expect("dispatch");
        assert_eq!(count, 2);
        assert_eq!(subscription.after_sequence(), 3);
        subscription.set_after_sequence(1).expect("set cursor");
        assert_eq!(subscription.after_sequence(), 1);
        let count = subscription.dispatch_available(1).expect("dispatch one");
        assert_eq!(count, 1);
        assert_eq!(subscription.after_sequence(), 2);
    }
    assert_eq!(
        seen,
        vec![
            (
                2,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
            (
                3,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
            (
                2,
                sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED,
            ),
        ]
    );
}

#[test]
fn rust_event_receiver_receives_events_with_frame_advancement() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");

    let mut receiver = machine.screen().events(0).into_receiver(1);
    let first = receiver.recv(0).expect("first event");
    assert_eq!(
        first.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET
    );

    let second = receiver.recv(2).expect("second event");
    assert_eq!(
        second.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_FRAME_COMPLETED
    );
    assert_eq!(second.frame.frame_number, 1);
}

#[test]
fn rust_waits_for_screen_changed_event() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    let event = machine
        .screen()
        .wait_for_screen_changed(0, 3, 1)
        .expect("screen changed");
    assert_eq!(event.sequence_number, 5);
    assert!(event.is_screen_changed());
    assert_eq!(event.frame.frame_number, 3);
    assert_eq!(event.region_id, "main");
    assert_eq!(
        (event.change_x, event.change_y, event.change_width, event.change_height),
        (0, 0, 2, 2)
    );
    assert_eq!(event.change_cell_count, 4);

    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    let mut after_sequence = event.sequence_number;
    let reset_event = loop {
        let next = machine
            .screen()
            .poll_event(after_sequence)
            .expect("poll")
            .expect("queued event");
        after_sequence = next.sequence_number;
        if next.event_type
            == sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET
        {
            break next;
        }
    };
    assert_eq!(
        reset_event.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MACHINE_RESET
    );
    let error = machine
        .screen()
        .wait_for_event(
            sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_SCREEN_CHANGED,
            reset_event.sequence_number,
            2,
            1,
        )
        .expect_err("wait should time out");
    assert_eq!(
        error,
        WaitError::Timeout(WaitTimeoutError {
            description: "event type EMU_AUTOMATION_EVENT_SCREEN_CHANGED".to_string(),
            frames_elapsed: 2,
            last_observation: Some(
                "event sequence=9 type=EMU_AUTOMATION_EVENT_FRAME_COMPLETED frame=2".to_string(),
            ),
        })
    );
}

#[test]
fn rust_waits_for_text_changed_event() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_text_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    machine
        .reset(sys::emu_automation_reset_kind_t::EMU_AUTOMATION_RESET_COLD)
        .expect("reset");
    let event = machine
        .screen()
        .wait_for_text_changed(0, 3, 1)
        .expect("text changed");
    assert!(event.is_text_changed());
    assert_eq!(event.frame.frame_number, 3);
    assert_eq!(event.region_id, "main");
    assert_eq!(
        (event.change_x, event.change_y, event.change_width, event.change_height),
        (0, 0, 2, 2)
    );
    assert_eq!(event.change_cell_count, 4);
    assert_eq!(event.text_deltas.len(), 4);
    assert_eq!(
        event
            .text_deltas
            .iter()
            .map(|delta| (delta.x, delta.y, delta.before.text.as_str(), delta.after.text.as_str()))
            .collect::<Vec<_>>(),
        vec![(0, 0, "W", "A"), (1, 0, "X", "B"), (0, 1, "Y", "C"), (1, 1, "Z", "D")]
    );
}

#[test]
fn rust_polls_media_debug_and_error_events() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_category_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");

    let media = machine.screen().poll_event(0).expect("poll").expect("media");
    assert_eq!(
        media.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY
    );
    assert_eq!(media.message, "disk activity");

    let debug = machine
        .screen()
        .poll_event(media.sequence_number)
        .expect("poll")
        .expect("debug");
    assert_eq!(
        debug.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_DEBUG_MESSAGE
    );
    assert_eq!(debug.message, "debug trace");

    let error = machine
        .screen()
        .poll_event(debug.sequence_number)
        .expect("poll")
        .expect("error");
    assert_eq!(
        error.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_ERROR
    );
    assert_eq!(error.message, "adapter error");
    assert_eq!(machine.screen().poll_event(error.sequence_number).expect("poll"), None);
}

#[test]
fn rust_waits_for_media_activity_event() {
    let mut raw = std::ptr::null_mut();
    let result = unsafe { emu_test_create_category_machine(&mut raw) };
    assert_eq!(result, sys::emu_automation_result_t::EMU_AUTOMATION_OK);

    let machine = Machine::from_raw_owned(raw).expect("null machine");
    let media = machine
        .screen()
        .wait_for_media_activity(0, 0, 1)
        .expect("media activity");
    assert_eq!(
        media.event_type,
        sys::emu_automation_event_type_t::EMU_AUTOMATION_EVENT_MEDIA_ACTIVITY
    );
    assert_eq!(media.message, "disk activity");
}

#[cfg(unix)]
#[test]
fn rust_library_opens_shared_object_and_creates_machine() {
    let shared = build_mock_shared_library();
    let library = Library::open(&shared).expect("open shared library");
    let machine = library
        .create_machine("emu_test_create_text_machine")
        .expect("create machine from shared library");
    let descriptor = machine.describe().expect("describe");
    assert_eq!(descriptor.machine_id, "mock-rust-machine");
    assert_eq!(machine.screen().text(Some("main")).expect("text").plain, "WX\nYZ");
}

#[cfg(unix)]
fn build_mock_shared_library() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = manifest_dir
        .ancestors()
        .nth(3)
        .expect("repo root")
        .to_path_buf();
    let out_dir = PathBuf::from(std::env::var("OUT_DIR").expect("OUT_DIR"));
    let shared = out_dir.join("libmock_automation_loader.so");
    let status = Command::new("cc")
        .arg("-shared")
        .arg("-fPIC")
        .arg("-std=c11")
        .arg("-Wall")
        .arg("-Wextra")
        .arg("-I")
        .arg(repo_root.join("automation/include"))
        .arg(repo_root.join("automation/core/emu_automation.c"))
        .arg(manifest_dir.join("tests/support/mock_automation.c"))
        .arg("-o")
        .arg(&shared)
        .status()
        .expect("invoke cc");
    assert!(status.success(), "cc failed building {}", display_path(&shared));
    shared
}

#[cfg(unix)]
fn display_path(path: &Path) -> String {
    path.display().to_string()
}
