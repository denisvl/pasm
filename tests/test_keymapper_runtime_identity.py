from tools.keymapper_ui.runtime_identity import host_token_to_sdl_scancode, sdl_scancode_to_host_token


def test_host_token_to_sdl_scancode_core_keys():
    assert host_token_to_sdl_scancode("A") == 4
    assert host_token_to_sdl_scancode("G") == 10
    assert host_token_to_sdl_scancode("0") == 39
    assert host_token_to_sdl_scancode("1") == 30
    assert host_token_to_sdl_scancode("RIGHTBRACKET") == 48
    assert host_token_to_sdl_scancode("BACKSLASH") == 49
    assert host_token_to_sdl_scancode("INTERNATIONAL1") == 135
    assert host_token_to_sdl_scancode("RCTRL") == 228


def test_sdl_scancode_to_host_token_core_keys():
    assert sdl_scancode_to_host_token(4) == "A"
    assert sdl_scancode_to_host_token(10) == "G"
    assert sdl_scancode_to_host_token(39) == "0"
    assert sdl_scancode_to_host_token(30) == "1"
    assert sdl_scancode_to_host_token(48) == "RIGHTBRACKET"
    assert sdl_scancode_to_host_token(49) == "BACKSLASH"
    assert sdl_scancode_to_host_token(135) == "INTERNATIONAL1"
    assert sdl_scancode_to_host_token(228) == "RCTRL"


def test_roundtrip_for_critical_tokens():
    tokens = [
        "RIGHTBRACKET",
        "BACKSLASH",
        "SEMICOLON",
        "SLASH",
        "INTERNATIONAL1",
        "LSHIFT",
        "RSHIFT",
        "LCTRL",
        "RCTRL",
    ]
    for tok in tokens:
        sc = host_token_to_sdl_scancode(tok)
        assert sc is not None
        assert sdl_scancode_to_host_token(sc) == tok
