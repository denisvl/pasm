from __future__ import annotations

from typing import Optional


def host_token_to_sdl_scancode(host_key: str) -> Optional[int]:
    hk = str(host_key).strip().upper()
    if not hk:
        return None
    if len(hk) == 1 and "A" <= hk <= "Z":
        return 4 + (ord(hk) - ord("A"))
    if hk.isdigit():
        return 39 if hk == "0" else 29 + int(hk)
    basic = {
        "RETURN": 40,
        "ESCAPE": 41,
        "BACKSPACE": 42,
        "TAB": 43,
        "SPACE": 44,
        "MINUS": 45,
        "EQUALS": 46,
        "LEFTBRACKET": 47,
        "RIGHTBRACKET": 48,
        "BACKSLASH": 49,
        "NONUSHASH": 50,
        "SEMICOLON": 51,
        "APOSTROPHE": 52,
        "GRAVE": 53,
        "COMMA": 54,
        "PERIOD": 55,
        "SLASH": 56,
        "CAPSLOCK": 57,
        "F1": 58,
        "F2": 59,
        "F3": 60,
        "F4": 61,
        "F5": 62,
        "F6": 63,
        "F7": 64,
        "F8": 65,
        "F9": 66,
        "F10": 67,
        "F11": 68,
        "F12": 69,
        "PRINTSCREEN": 70,
        "SCROLLLOCK": 71,
        "PAUSE": 72,
        "INSERT": 73,
        "HOME": 74,
        "PAGEUP": 75,
        "DELETE": 76,
        "END": 77,
        "PAGEDOWN": 78,
        "RIGHT": 79,
        "LEFT": 80,
        "DOWN": 81,
        "UP": 82,
        "NUMLOCKCLEAR": 83,
        "NONUSBACKSLASH": 100,
        "APPLICATION": 101,
        "INTERNATIONAL1": 135,
        "INTERNATIONAL2": 136,
        "INTERNATIONAL3": 137,
        "INTERNATIONAL4": 138,
        "INTERNATIONAL5": 139,
        "INTERNATIONAL6": 140,
        "INTERNATIONAL7": 141,
        "INTERNATIONAL8": 142,
        "INTERNATIONAL9": 143,
        "LCTRL": 224,
        "LSHIFT": 225,
        "LALT": 226,
        "LGUI": 227,
        "RCTRL": 228,
        "RSHIFT": 229,
        "RALT": 230,
        "RGUI": 231,
    }
    if hk in basic:
        return basic[hk]
    if hk.startswith("KP_"):
        kp = {
            "KP_DIVIDE": 84,
            "KP_MULTIPLY": 85,
            "KP_MINUS": 86,
            "KP_PLUS": 87,
            "KP_ENTER": 88,
            "KP_1": 89,
            "KP_2": 90,
            "KP_3": 91,
            "KP_4": 92,
            "KP_5": 93,
            "KP_6": 94,
            "KP_7": 95,
            "KP_8": 96,
            "KP_9": 97,
            "KP_0": 98,
            "KP_PERIOD": 99,
        }
        return kp.get(hk)
    return None


def sdl_scancode_to_host_token(sc: int) -> Optional[str]:
    if sc < 0:
        return None
    if 4 <= sc <= 29:
        return chr(ord("A") + (sc - 4))
    if 30 <= sc <= 38:
        return str(sc - 29)
    if sc == 39:
        return "0"
    rev = {
        40: "RETURN",
        41: "ESCAPE",
        42: "BACKSPACE",
        43: "TAB",
        44: "SPACE",
        45: "MINUS",
        46: "EQUALS",
        47: "LEFTBRACKET",
        48: "RIGHTBRACKET",
        49: "BACKSLASH",
        50: "NONUSHASH",
        51: "SEMICOLON",
        52: "APOSTROPHE",
        53: "GRAVE",
        54: "COMMA",
        55: "PERIOD",
        56: "SLASH",
        57: "CAPSLOCK",
        58: "F1",
        59: "F2",
        60: "F3",
        61: "F4",
        62: "F5",
        63: "F6",
        64: "F7",
        65: "F8",
        66: "F9",
        67: "F10",
        68: "F11",
        69: "F12",
        70: "PRINTSCREEN",
        71: "SCROLLLOCK",
        72: "PAUSE",
        73: "INSERT",
        74: "HOME",
        75: "PAGEUP",
        76: "DELETE",
        77: "END",
        78: "PAGEDOWN",
        79: "RIGHT",
        80: "LEFT",
        81: "DOWN",
        82: "UP",
        83: "NUMLOCKCLEAR",
        100: "NONUSBACKSLASH",
        101: "APPLICATION",
        135: "INTERNATIONAL1",
        136: "INTERNATIONAL2",
        137: "INTERNATIONAL3",
        138: "INTERNATIONAL4",
        139: "INTERNATIONAL5",
        140: "INTERNATIONAL6",
        141: "INTERNATIONAL7",
        142: "INTERNATIONAL8",
        143: "INTERNATIONAL9",
        224: "LCTRL",
        225: "LSHIFT",
        226: "LALT",
        227: "LGUI",
        228: "RCTRL",
        229: "RSHIFT",
        230: "RALT",
        231: "RGUI",
    }
    return rev.get(sc)
