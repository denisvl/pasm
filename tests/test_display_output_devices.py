from pathlib import Path

import yaml

from src.parser import yaml_loader


BASE_DIR = Path(__file__).resolve().parents[1]
COMMON_DEVICES = BASE_DIR / "examples" / "devices" / "common"


def _load_device(name: str) -> dict:
    path = COMMON_DEVICES / name
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return yaml_loader.ProcessorSystemLoader().validate_device(data)


def _handler_names(device: dict) -> set[str]:
    return {handler["name"] for handler in device["interfaces"]["handlers"]}


def _signal_names(device: dict) -> set[str]:
    return {signal["name"] for signal in device["interfaces"]["signals"]}


def _state_names(device: dict) -> set[str]:
    return {state["name"] for state in device["state"]}


def test_common_display_output_devices_validate_against_schema():
    for path in COMMON_DEVICES.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        yaml_loader.ProcessorSystemLoader().validate_device(data)


def test_tv_models_always_have_audio_output_controls():
    tv_models = [
        _load_device("tv_crt_mono.yaml"),
        _load_device("tv_crt_stereo.yaml"),
        _load_device("tv_lcd_stereo.yaml"),
    ]

    assert {model["metadata"]["display"]["technology"] for model in tv_models} == {
        "crt",
        "lcd",
    }
    assert {model["metadata"]["audio_output"]["channels"] for model in tv_models} == {
        "mono",
        "stereo",
    }

    for device in tv_models:
        metadata = device["metadata"]
        assert metadata["id"] == "tv"
        assert metadata["display"]["kind"] == "tv"
        assert metadata["display"]["is_monitor"] is False
        assert metadata["display"]["aspect_ratio"]["width"] > 0
        assert metadata["display"]["aspect_ratio"]["height"] > 0
        assert metadata["display"]["scaling"] == {
            "mode": "stretch_to_fit_aspect",
            "integer_scale_base": 2,
            "large_screen_inches": 102,
            "resize_preserves_aspect": True,
        }
        assert "audio_output" in metadata
        assert {"set_volume", "set_mute", "on_audio_level"} <= _handler_names(device)
        assert {"gain_q8_8", "low_cut_hz", "high_cut_hz", "muted", "volume_percent", "osd_ticks"} <= _state_names(device)
        assert metadata["audio_output"]["osd"] == {
            "style": "eighties",
            "shows_mute": True,
            "shows_volume": True,
        }


def test_stereo_tv_duplicates_mono_audio_to_left_and_right():
    device = _load_device("tv_crt_stereo.yaml")
    body = device["behavior"]["handler_bodies"]["on_audio_level"]

    assert device["metadata"]["audio_output"]["channels"] == "stereo"
    assert "pcm_stereo_sample" in _signal_names(device)
    assert "uint64_t sig_args[3] = { sample, sample, args[1] };" in body


def test_monitor_models_cover_silent_and_audio_capable_crt_lcd_outputs():
    silent_crt = _load_device("monitor_crt_green.yaml")
    silent_color_crt = _load_device("monitor_crt_color.yaml")
    silent_lcd = _load_device("monitor_lcd.yaml")
    audio_lcd = _load_device("monitor_lcd_stereo.yaml")

    assert {silent_crt["metadata"]["display"]["technology"], silent_lcd["metadata"]["display"]["technology"]} == {
        "crt",
        "lcd",
    }
    assert silent_crt["metadata"]["display"]["phosphor_color"] == "green"
    assert silent_crt["metadata"]["display"]["shader_function"] == "crt_monitor_green_phosphor"
    assert silent_color_crt["metadata"]["display"]["phosphor_color"] == "color"

    for device in (silent_crt, silent_color_crt, silent_lcd, audio_lcd):
        assert device["metadata"]["id"] == "monitor"
        assert device["metadata"]["display"]["kind"] == "monitor"
        assert device["metadata"]["display"]["is_monitor"] is True
        assert device["metadata"]["display"]["scaling"]["resize_preserves_aspect"] is True
        assert "on_frame_present" in _handler_names(device)
        assert "on_frame_present5" in _handler_names(device)

    for device in (silent_crt, silent_color_crt, silent_lcd):
        assert "audio_output" not in device["metadata"]
        assert {"set_volume", "set_mute", "on_audio_level"}.isdisjoint(_handler_names(device))

    assert audio_lcd["metadata"]["audio_output"]["channels"] == "stereo"
    assert {"set_volume", "set_mute", "on_audio_level", "on_stereo_audio_level"} <= _handler_names(audio_lcd)
    assert {"gain_q8_8", "low_cut_hz", "high_cut_hz", "muted", "volume_percent", "osd_ticks"} <= _state_names(audio_lcd)


def test_display_models_share_literal_ids_for_runtime_replacement():
    tv_ids = {
        _load_device("tv_crt_mono.yaml")["metadata"]["id"],
        _load_device("tv_crt_stereo.yaml")["metadata"]["id"],
        _load_device("tv_lcd_stereo.yaml")["metadata"]["id"],
    }
    monitor_ids = {
        _load_device("monitor_crt_green.yaml")["metadata"]["id"],
        _load_device("monitor_crt_color.yaml")["metadata"]["id"],
        _load_device("monitor_lcd.yaml")["metadata"]["id"],
        _load_device("monitor_lcd_stereo.yaml")["metadata"]["id"],
    }

    assert tv_ids == {"tv"}
    assert monitor_ids == {"monitor"}


def test_crt_display_models_define_glsl_shader():
    for path in COMMON_DEVICES.glob("*.yaml"):
        device = _load_device(path.name)
        display = device["metadata"]["display"]
        if display["technology"] != "crt":
            continue

        shader = display["shader"]
        assert shader["language"] == "glsl"
        assert "#version 330 core" in shader["vertex_source"]
        if device["metadata"]["model"] in {"generic_crt_monitor_color", "generic_crt_monitor_green"}:
            expected_name = (
                "crt_monitor_green_phosphor"
                if device["metadata"]["model"] == "generic_crt_monitor_green"
                else "crt_monitor"
            )
            assert shader["name"] == expected_name
            assert shader["uniforms"] == ["screenTexture", "sourceResolution"]
            assert "layout (location = 0) in vec3 aPos;" in shader["vertex_source"]
            assert "uniform sampler2D screenTexture;" in shader["fragment_source"]
            assert "uniform vec2 sourceResolution;" in shader["fragment_source"]
            assert "const float CURVATURE = 8.0;" in shader["fragment_source"]
            if device["metadata"]["model"] == "generic_crt_monitor_green":
                assert "const vec3 PHOSPHOR_COLOR = vec3(0.12, 1.0, 0.18);" in shader["fragment_source"]
                assert "vec3 baseColor = luma * PHOSPHOR_COLOR;" in shader["fragment_source"]
                assert "baseColor *= 1.25;" in shader["fragment_source"]
            else:
                assert "float maskMod = mod(pixelCoordX, 3.0);" in shader["fragment_source"]
                assert "baseColor.rgb *= 1.25;" in shader["fragment_source"]
        else:
            assert display["kind"] == "tv"
            assert shader["name"] == "crt_tv"
            assert shader["uniforms"] == ["screenTexture", "sourceResolution"]
            assert "layout (location = 0) in vec3 aPos;" in shader["vertex_source"]
            assert "uniform sampler2D screenTexture;" in shader["fragment_source"]
            assert "uniform vec2 sourceResolution;" in shader["fragment_source"]
            assert "const float CURVATURE = 8.0;" in shader["fragment_source"]
            assert "const float SCANLINE_WEIGHT = 0.10;" in shader["fragment_source"]
            assert "const float MASK_DARKNESS = 0.08;" in shader["fragment_source"]
            assert "const float GLOW_FACTOR = 0.05;" in shader["fragment_source"]
            assert "baseColor = mix(baseColor, blurColor, GLOW_FACTOR);" in shader["fragment_source"]
            assert "float maskPhase = mod(gl_FragCoord.x + floor(gl_FragCoord.y * 0.5), 3.0);" in shader["fragment_source"]
            assert "baseColor *= 1.08;" in shader["fragment_source"]


def test_system_display_selection_metadata_supports_startup_and_runtime_models():
    if yaml_loader.Draft7Validator is None:
        return

    schema = yaml_loader.load_schema("system")
    validator = yaml_loader.Draft7Validator(schema)
    system = {
        "metadata": {"name": "DisplaySelection"},
        "clock_hz": 1000000,
        "memory": {"default_size": 65536},
        "components": {"ics": [], "devices": [], "hosts": []},
        "connections": [],
        "display": {
            "default_component": "tv",
            "default_model": "generic_crt_tv_mono",
            "runtime_switchable": True,
            "available_models": [
                {"component": "tv", "model": "generic_crt_tv_mono"},
                {"component": "tv", "model": "generic_lcd_tv_stereo"},
                {"component": "monitor", "model": "generic_lcd_monitor"},
            ],
        },
    }

    assert list(validator.iter_errors(system)) == []
    assert {
        (entry["component"], entry["model"])
        for entry in system["display"]["available_models"]
    } >= {("tv", system["display"]["default_model"])}


def test_video_systems_are_wired_through_a_display_sink():
    for path in (BASE_DIR / "examples" / "systems").rglob("*.yaml"):
        system = yaml.safe_load(path.read_text(encoding="utf-8"))
        connections = system.get("connections", [])
        has_video_to_host = any(
            connection.get("to", {}).get("name") == "video_frame"
            for connection in connections
        )
        if not has_video_to_host:
            continue

        display = system.get("display", {})
        component = display.get("default_component")
        devices = set(system.get("components", {}).get("devices", []))

        assert component in {"tv", "monitor"}, path
        assert component in devices, path
        assert any(
            connection.get("to", {}).get("component") == component
            and connection.get("to", {}).get("name") in {"on_frame_present", "on_frame_present5"}
            for connection in connections
        ), path
        assert any(
            connection.get("from", {}).get("component") == component
            and connection.get("to", {}).get("name") == "video_frame"
            for connection in connections
        ), path


def test_tv_system_audio_is_routed_through_tv_output():
    for path in (BASE_DIR / "examples" / "systems").rglob("*.yaml"):
        system = yaml.safe_load(path.read_text(encoding="utf-8"))
        if system.get("display", {}).get("default_component") != "tv":
            continue
        connections = system.get("connections", [])
        if not any(connection.get("to", {}).get("name") == "audio_pcm" for connection in connections):
            continue

        assert any(
            connection.get("to", {}).get("component") == "tv"
            and connection.get("to", {}).get("name") == "on_audio_level"
            for connection in connections
        ), path
        assert any(
            connection.get("from", {}).get("component") == "tv"
            and connection.get("from", {}).get("name") == "pcm_sample"
            and connection.get("to", {}).get("name") == "audio_pcm"
            for connection in connections
        ), path


def test_interactive_video_hosts_preserve_aspect_ratio_on_resize():
    for path in (BASE_DIR / "examples" / "hosts").rglob("*_host_hal_interactive.yaml"):
        host = yaml.safe_load(path.read_text(encoding="utf-8"))
        body = host.get("behavior", {}).get("handler_bodies", {}).get("video_frame", "")
        if not body:
            continue

        assert "cpu_host_hal_renderer_output_size" in body, path
        assert "scaled_w" in body, path
        assert "scaled_h" in body, path
        assert "dst.x = (ww - dst.w) / 2;" in body, path
        assert "dst.y = (wh - dst.h) / 2;" in body, path
        assert "cpu_host_hal_render_copy" in body and "&dst" in body, path


def test_atari2600_tv_output_uses_tv_aspect_not_raw_framebuffer_size():
    path = BASE_DIR / "examples" / "hosts" / "atari2600" / "atari2600_host_hal_interactive.yaml"
    host = yaml.safe_load(path.read_text(encoding="utf-8"))
    body = host["behavior"]["handler_bodies"]["video_frame"]
    init = host["behavior"]["snippets"]["init"]
    destroy = host["behavior"]["snippets"]["destroy"]
    states = {entry["name"]: entry for entry in host.get("state", [])}

    assert "display_shader" in states
    assert "display_shader_supported" in states
    assert "atari2600_crt_tv_fragment_shader" in init
    assert "const float CURVATURE = 8.0;" in init
    assert "const float GLOW_FACTOR = 0.05;" in init
    assert "baseColor *= 1.08;" in init
    assert "cpu_host_hal_shader_create" in init
    assert "cpu_host_hal_shader_destroy(comp->display_shader);" in destroy
    assert "cpu_host_hal_set_window_size(comp->window, (int)w, (int)h)" not in body
    assert "uint32_t aspect_w = cpu->comp_tv.aspect_width;" in body
    assert "uint32_t aspect_h = cpu->comp_tv.aspect_height;" in body
    assert "* 3) / 4" not in body
    assert "* 4) / 3" not in body
    assert "scaled_h = (int)((((int64_t)ww) * (int64_t)aspect_h) / (int64_t)aspect_w);" in body
    assert "scaled_w = (int)((((int64_t)wh) * (int64_t)aspect_w) / (int64_t)aspect_h);" in body
    assert "cpu_host_hal_render_copy_shader(renderer, texture, NULL, &dst, comp->display_shader, (int)w, (int)h, ww, wh)" in body


def test_monitor_hosts_use_monitor_aspect_not_raw_framebuffer_size():
    host_paths = [
        BASE_DIR / "examples" / "hosts" / "apple2" / "apple2_host_hal_interactive.yaml",
        BASE_DIR / "examples" / "hosts" / "bbcmicro" / "bbc_micro_host_hal_interactive.yaml",
        BASE_DIR / "examples" / "hosts" / "cpc464" / "cpc_host_hal_interactive.yaml",
        BASE_DIR / "examples" / "hosts" / "trs80_model4" / "trs80_host_hal_interactive.yaml",
    ]

    for path in host_paths:
        host = yaml.safe_load(path.read_text(encoding="utf-8"))
        body = host["behavior"]["handler_bodies"]["video_frame"]

        assert "uint32_t aspect_w = cpu->comp_monitor.aspect_width;" in body, path
        assert "uint32_t aspect_h = cpu->comp_monitor.aspect_height;" in body, path
        assert "scaled_h = (int)((((int64_t)ww) * (int64_t)aspect_h) / (int64_t)aspect_w);" in body, path
        assert "scaled_w = (int)((((int64_t)wh) * (int64_t)aspect_w) / (int64_t)aspect_h);" in body, path
        assert "cpu_host_hal_set_window_size(comp->window, (int)w, (int)h)" not in body, path


def test_common_display_runtime_aspect_state_matches_display_metadata():
    for path in (BASE_DIR / "examples" / "devices" / "common").glob("*.yaml"):
        device = yaml.safe_load(path.read_text(encoding="utf-8"))
        display = device.get("metadata", {}).get("display", {})
        if not display:
            continue
        aspect = display["aspect_ratio"]
        states = {entry["name"]: entry for entry in device.get("state", [])}

        assert states["aspect_width"]["initial"] == str(aspect["width"]), path
        assert states["aspect_height"]["initial"] == str(aspect["height"]), path


def test_speaker_and_beeper_are_only_physical_system_components():
    for path in (BASE_DIR / "examples" / "systems").rglob("*.yaml"):
        system = yaml.safe_load(path.read_text(encoding="utf-8"))
        devices = set(system.get("components", {}).get("devices", []))
        connection_components = {
            endpoint.get("component")
            for connection in system.get("connections", [])
            for endpoint in (connection.get("from", {}), connection.get("to", {}))
        }

        if "speaker" in devices:
            assert "speaker" in connection_components, f"{path} declares speaker without wiring"
        if "beeper" in devices:
            assert "beeper" in connection_components, f"{path} declares beeper without wiring"
        assert not ("speaker" in devices and "beeper" in devices), path


def test_zx_spectrum_uses_beeper_not_speaker():
    for path in (
        BASE_DIR / "examples" / "systems" / "zx_spectrum48k" / "spectrum48k_default.yaml",
        BASE_DIR / "examples" / "systems" / "zx_spectrum48k" / "spectrum48k_interactive.yaml",
    ):
        system = yaml.safe_load(path.read_text(encoding="utf-8"))
        devices = set(system["components"]["devices"])
        assert "beeper" in devices
        assert "speaker" not in devices


def test_zx_spectrum_beeper_device_is_not_named_speaker():
    beeper_path = BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_beeper.yaml"
    stale_speaker_path = BASE_DIR / "examples" / "devices" / "zx_spectrum48k" / "zx48_speaker.yaml"
    device = yaml.safe_load(beeper_path.read_text(encoding="utf-8"))

    assert device["metadata"]["id"] == "beeper"
    assert device["metadata"]["model"] == "zx48_beeper_pcm"
    assert not stale_speaker_path.exists()
