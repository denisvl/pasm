import pathlib
import uuid

from src import generator as gen_mod
from src.parser import yaml_loader
from tests.support import example_pair


BASE_DIR = pathlib.Path(__file__).resolve().parents[1]


def _make_workdir(prefix: str) -> pathlib.Path:
    root = BASE_DIR / ".tmp_test_work"
    root.mkdir(parents=True, exist_ok=True)
    workdir = root / f"{prefix}{uuid.uuid4().hex[:10]}"
    workdir.mkdir(parents=True, exist_ok=False)
    return workdir


def _apple2_interactive_paths():
    processor_path, _ = example_pair("mos6502")
    system_path = BASE_DIR / "examples" / "systems" / "apple2" / "apple2_interactive.yaml"
    ic_paths = [
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_keyboard_encoder_ay_5_3600.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_gameio_ne558.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_video_softswitches.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_speaker_toggle.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_char_generator_rom.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_slot_decoder_ttl.yaml",
        BASE_DIR / "examples" / "ics" / "apple2" / "apple2_main_ram.yaml",
    ]
    device_paths = [
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_keyboard.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_gameport.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_video.yaml",
        BASE_DIR / "examples" / "devices" / "apple2" / "apple2_speaker.yaml",
    ]
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "apple2" / "apple2_host_hal_interactive.yaml",
    ]
    return processor_path, system_path, ic_paths, device_paths, host_paths


def test_apple2_interactive_component_graph_validates():
    processor_path, system_path, ic_paths, device_paths, host_paths = _apple2_interactive_paths()
    data = yaml_loader.load_processor_system(
        str(processor_path),
        str(system_path),
        [str(path) for path in ic_paths],
        [str(path) for path in device_paths],
        [str(path) for path in host_paths],
    )
    assert data["metadata"]["name"] == "MOS6502"
    assert data["system"]["metadata"]["name"] == "Apple2InteractiveSystem"
    assert [ic["metadata"]["id"] for ic in data["ics"]] == [
        "apple2_keyboard_encoder",
        "apple2_gameio",
        "apple2_video_softswitches",
        "apple2_speaker_toggle",
        "apple2_char_rom",
        "apple2_slot_decoder",
        "apple2_main_ram",
    ]
    assert [dev["metadata"]["id"] for dev in data["devices"]] == [
        "keyboard_apple2",
        "gameport_apple2",
        "video_apple2",
        "speaker",
        "monitor",
    ]
    assert [host["metadata"]["id"] for host in data["hosts"]] == ["host_apple2"]


def test_generate_apple2_interactive_with_components():
    processor_path, system_path, ic_paths, device_paths, host_paths = _apple2_interactive_paths()
    outdir = _make_workdir("apple2_interactive_")

    gen_mod.generate(
        str(processor_path),
        str(system_path),
        str(outdir),
        ic_paths=[str(path) for path in ic_paths],
        device_paths=[str(path) for path in device_paths],
        host_paths=[str(path) for path in host_paths],
        host_backend_target="glfw",
    )

    src_dir = outdir / "src"
    assert (src_dir / "MOS6502_core.c").exists()
    assert (src_dir / "MOS6502.h").exists()
    assert (src_dir / "MOS6502_decoder.c").exists()
    impl = (src_dir / "MOS6502_core.c").read_text(encoding="utf-8")
    system_glue = (src_dir / "apple2_system_glue.c").read_text(encoding="utf-8")
    all_src = "\n".join(p.read_text(encoding="utf-8") for p in sorted(src_dir.glob("*.[ch]")))
    assert "0xC050u" in all_src and "0xC057u" in all_src
    assert "apple2_glyph" in system_glue
    assert "A2_HIRES_ADDR" in system_glue
    assert "const uint32_t text_fg = 0xFFFFFFFFu;" in system_glue
    assert "0xFFA8FF7Au" not in system_glue
    assert 'cpu_component_emit_signal(cpu, "monitor", "frame_present", args, argc);' in system_glue
    assert "void * display_shader;" in all_src
    assert "apple2_crt_green_fragment_shader" in all_src
    assert "const float CURVATURE = 6.0;" in all_src
    assert "int cpu_host_hal_gamepad_count(void);" in all_src
    assert "int cpu_host_hal_joystick_count(void);" in all_src
    assert "const vec3 PHOSPHOR_COLOR = vec3(0.12, 1.0, 0.18);" in all_src
    assert "vec2 crtUV = curve(TexCoords);" in all_src
    assert "uniform sampler2D screenTexture;" in all_src
    assert "uniform vec2 sourceResolution;" in all_src
    assert "float luma = dot(src, vec3(0.30, 0.59, 0.11));" in all_src
    assert "comp->display_shader = cpu_host_hal_shader_create(" in all_src
    assert "comp->display_shader_supported = (comp->display_shader != NULL && cpu_host_hal_renderer_supports_shaders(renderer) != 0) ? 1 : 0;" in all_src
    assert "int shader_ready = (comp->display_shader_supported != 0) ? 1 : 0;" in all_src
    assert "cpu_host_hal_render_copy_shader(renderer, texture, NULL, &dst, comp->display_shader, (int)w, (int)h, ww, wh)" in all_src
    assert "uint64_t shader_count = (uint64_t)w * (uint64_t)h;" in all_src
    assert "pixels[shader_i] = 0xFF000000u | (green << 8u);" in all_src
    assert "uint32_t luma = (r * 30u + g * 59u + b * 11u) / 100u;" in all_src
    assert "cpu_host_hal_event_key_repeat(&ev) == 0" in all_src
    assert "CPU_HOST_MOD_SHIFT" in all_src
    assert "CPU_HOST_MOD_CTRL" in all_src
    assert "CPU_HOST_SCANCODE(A)" in all_src
    assert "CPU_HOST_SCANCODE(Z)" in all_src
    assert 'snprintf(rendered, sizeof(rendered), "LDA #%s"' in all_src
    assert "int scaled_w = ww;" in all_src
    assert "int scaled_h = (int)((((int64_t)ww) * (int64_t)aspect_h) / (int64_t)aspect_w);" in all_src
    assert "int16_t next_level = (level_u != 0u) ? 9000 : -9000;" in all_src
    assert "comp->audio_last_cycle = cycle;" in all_src
    assert "comp->audio_level = next_level;" in all_src
    assert 'SDL_Init(SDL_INIT_AUDIO)' in all_src
    assert 'SDL_OpenAudioDevice(NULL, 0, &sdl_want, &sdl_have, allowed_changes);' in all_src
    assert 'cpu_host_hal_glfw_sdl_audio_dev != 0u' in all_src
    assert '"pipewire",' in all_src
    assert 'snd_pcm_writei(cpu_host_hal_glfw_alsa_pcm, ptr, (snd_pcm_uframes_t)frames)' in all_src
    assert 'if (cpu_host_hal_glfw_alsa_pcm != NULL) {\n        return 0u;' in all_src
    assert "cpu_host_hal_glfw_audio_trace" not in all_src
    assert "PASM_HOST_AUDIO_TRACE" not in all_src
    assert "PASM_APPLE2_C030_TRACE" not in all_src
    assert "aplay -q -t raw -f S16_LE" not in all_src
    assert "ch + (uint8_t)(x + y + comp->frame_count)" not in impl


def test_apple2_interactive_runner_defaults_audio_and_sdl2_backend():
    script = (BASE_DIR / "scripts" / "run_apple2_debugger.sh").read_text(encoding="utf-8")
    assert 'PASM_HOST_AUDIO="${PASM_HOST_AUDIO:-1}"' in script
    assert 'PASM_HOST_AUDIO_DEVICE="${PASM_HOST_AUDIO_DEVICE:-pipewire}"' in script
    assert 'PASM_SDL_AUDIO_DRIVER="${PASM_SDL_AUDIO_DRIVER:-}"' in script
    assert '--host-backend "${HOST_BACKEND:-glfw}"' in script
    assert 'PASM_HOST_AUDIO="${PASM_HOST_AUDIO}" \\' in script
    assert 'PASM_HOST_AUDIO_DEVICE="${PASM_HOST_AUDIO_DEVICE}" \\' in script


def test_apple2_interactive_runner_forwards_extra_args():
    script = (BASE_DIR / "scripts" / "run_apple2_debugger.sh").read_text(encoding="utf-8")
    assert 'shift' in script
    assert 'RUN_ARGS+=("$@")' in script
