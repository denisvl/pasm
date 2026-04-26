#include <SDL.h>
#include <SDL_image.h>

#include "imgui.h"
#include "backends/imgui_impl_sdl2.h"
#include "backends/imgui_impl_sdlrenderer2.h"

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fstream>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

struct MapperBox {
    std::string id;
    int x = 0;
    int y = 0;
    int w = 1;
    int h = 1;
    bool has_overlay = false;
    int r = 80;
    int g = 160;
    int b = 255;
};

struct Binding {
    int scancode = -1;
    std::string host_token;
    std::string mapper_key_id;
    bool has_press = false;
    int row = 0;
    int bit = 0;
    bool has_ascii = false;
    bool has_ascii_shift = false;
    bool has_ascii_ctrl = false;
    int ascii = 0;
    int ascii_shift = 0;
    int ascii_ctrl = 0;
    std::string emulator_key_id;
    std::string system_key_id;
};

struct SystemKeyDef {
    std::string id;
    bool visual_feedback = false;
};

struct Snapshot {
    std::vector<MapperBox> boxes;
    std::vector<Binding> bindings;
    std::vector<SystemKeyDef> system_keys;
    std::unordered_set<size_t> selected;
    int primary = -1;
    int selected_binding_global_index = -1;
    int selected_system_key_index = -1;
    int selected_emulator_key_index = -1;
    int alias_capture_target_kind = 0;
    std::string alias_capture_target_id;
    int edit_target_kind = 0;
    std::string edit_target_id;
    int system_edit_sync_index = -2;
    std::string system_edit_id;
    bool system_edit_vf = false;
    int binding_edit_sync_index = -2;
    bool binding_use_press = false;
    int binding_row = 0;
    int binding_bit = 0;
    bool binding_has_ascii = false;
    bool binding_has_ascii_shift = false;
    bool binding_has_ascii_ctrl = false;
    int binding_ascii = 0;
    int binding_ascii_shift = 0;
    int binding_ascii_ctrl = 0;
    bool capture_new_binding_mode = false;
};

struct AppState {
    std::string mapper_path;
    std::string host_map_path;
    std::string system_name;
    std::string keyboard_kind = "ascii";
    bool has_focus_required = false;
    bool focus_required = false;
    std::string image_file;
    std::string image_path;
    std::vector<MapperBox> boxes;
    std::vector<Binding> bindings;
    std::vector<SystemKeyDef> system_keys;
    std::unordered_map<std::string, size_t> box_index_by_id;

    std::unordered_set<size_t> selected;
    int primary = -1;
    bool dragging = false;
    bool resizing = false;
    ImVec2 drag_start_img{0, 0};
    std::unordered_map<size_t, ImVec2> drag_origin;

    float zoom = 1.0f;
    ImVec2 pan{0.0f, 0.0f};
    bool auto_fit_pending = true;
    bool manual_view = false;
    ImVec2 last_canvas_avail{0.0f, 0.0f};

    int last_scancode = -1;
    int32_t last_keycode = 0;
    std::string last_key_name;
    std::string last_text_input;
    bool last_down = false;
    int last_repeat = 0;
    bool sdl_text_input_active = false;
    bool want_text_input_prev = false;

    bool dirty_mapper = false;
    bool dirty_map = false;

    std::vector<Snapshot> undo_stack;
    std::vector<Snapshot> redo_stack;
    bool drag_snapshot_taken = false;

    int selected_binding_global_index = -1;
    bool scroll_to_selected_binding = false;
    int binding_edit_sync_index = -2;
    bool binding_use_press = false;
    int binding_row = 0;
    int binding_bit = 0;
    bool binding_has_ascii = false;
    bool binding_has_ascii_shift = false;
    bool binding_has_ascii_ctrl = false;
    int binding_ascii = 0;
    int binding_ascii_shift = 0;
    int binding_ascii_ctrl = 0;
    int selected_system_key_index = -1;
    int selected_emulator_key_index = -1;
    int system_edit_sync_index = -2;
    std::string system_edit_id;
    bool system_edit_vf = false;
    int edit_target_kind = 0; // 0 mapper, 1 system, 2 emulator
    std::string edit_target_id;
    bool alias_capture_mode = false;
    int alias_capture_target_kind = 0; // 0 mapper, 1 system, 2 emulator
    std::string alias_capture_target_id;
    bool capture_new_binding_mode = false;
    bool quit_requested = false;
    int quit_stage = 0; // 0 none, 1 mapper save, 2 map save, 3 final confirm
    bool pick_color_mode = false;
    bool edit_mode = false;
    int resize_start_w = 1;
    int resize_start_h = 1;
    bool marquee_active = false;
    bool marquee_add = false;
    bool marquee_toggle = false;
    ImVec2 marquee_start{0, 0};
    ImVec2 marquee_curr{0, 0};
    bool rename_popup_open = false;
    std::string rename_text;
    bool validation_popup_open = false;
    std::string validation_popup_title;
    std::vector<std::string> validation_errors;

    // State-based input capture (matches emulator semantics and survives dead-key/IME filtering).
    std::vector<uint8_t> prev_key_state;
    int key_state_count = 0;
};

static std::string trim(std::string s) {
    auto not_space = [](unsigned char c) { return !std::isspace(c); };
    s.erase(s.begin(), std::find_if(s.begin(), s.end(), not_space));
    s.erase(std::find_if(s.rbegin(), s.rend(), not_space).base(), s.end());
    return s;
}

static std::string unquote(std::string s) {
    s = trim(std::move(s));
    if (s.size() >= 2) {
        char a = s.front();
        char b = s.back();
        if ((a == '"' && b == '"') || (a == '\'' && b == '\'')) {
            return s.substr(1, s.size() - 2);
        }
    }
    return s;
}

static std::optional<int> parse_int(const std::string& s) {
    try {
        size_t idx = 0;
        int v = std::stoi(s, &idx, 0);
        if (idx == s.size()) return v;
    } catch (...) {
    }
    return std::nullopt;
}

static bool starts_with(const std::string& s, const char* p) {
    const size_t n = std::strlen(p);
    return s.size() >= n && std::equal(p, p + n, s.begin());
}

static std::string dir_of(const std::string& p) {
    auto pos = p.find_last_of('/');
    if (pos == std::string::npos) return ".";
    return p.substr(0, pos);
}

static std::string path_join(const std::string& a, const std::string& b) {
    if (b.empty()) return a;
    if (!b.empty() && b[0] == '/') return b;
    if (a.empty() || a == ".") return b;
    return a + "/" + b;
}

static int parse_scancode_token(std::string tok) {
    tok = unquote(tok);
    if (tok.empty()) return -1;

    if (starts_with(tok, "KEY_")) {
        auto n = parse_int(tok.substr(4));
        if (n.has_value()) return *n;
    }
    // Heuristic: YAML often uses single-character digit tokens like "1" to mean the key named "1",
    // not scancode 1. Numeric scancodes should be written as KEY_### or multi-digit numbers.
    if (tok.size() == 1 && tok[0] >= '0' && tok[0] <= '9') {
        SDL_Scancode sc = SDL_GetScancodeFromName(tok.c_str());
        return sc == SDL_SCANCODE_UNKNOWN ? -1 : (int)sc;
    }
    if (auto n = parse_int(tok); n.has_value()) return *n;

    std::string up;
    up.reserve(tok.size());
    for (char c : tok) up.push_back((char)std::toupper((unsigned char)c));

    static const std::unordered_map<std::string, SDL_Scancode> kMap = {
        {"SPACE", SDL_SCANCODE_SPACE},
        {"RETURN", SDL_SCANCODE_RETURN},
        {"KP_ENTER", SDL_SCANCODE_KP_ENTER},
        {"BACKSPACE", SDL_SCANCODE_BACKSPACE},
        {"ESCAPE", SDL_SCANCODE_ESCAPE},
        {"TAB", SDL_SCANCODE_TAB},
        {"MINUS", SDL_SCANCODE_MINUS},
        {"EQUALS", SDL_SCANCODE_EQUALS},
        {"LEFTBRACKET", SDL_SCANCODE_LEFTBRACKET},
        {"RIGHTBRACKET", SDL_SCANCODE_RIGHTBRACKET},
        {"BACKSLASH", SDL_SCANCODE_BACKSLASH},
        {"SEMICOLON", SDL_SCANCODE_SEMICOLON},
        {"APOSTROPHE", SDL_SCANCODE_APOSTROPHE},
        {"COMMA", SDL_SCANCODE_COMMA},
        {"PERIOD", SDL_SCANCODE_PERIOD},
        {"SLASH", SDL_SCANCODE_SLASH},
        {"GRAVE", SDL_SCANCODE_GRAVE},
        {"UP", SDL_SCANCODE_UP},
        {"DOWN", SDL_SCANCODE_DOWN},
        {"LEFT", SDL_SCANCODE_LEFT},
        {"RIGHT", SDL_SCANCODE_RIGHT},
        {"HOME", SDL_SCANCODE_HOME},
        {"END", SDL_SCANCODE_END},
        {"DELETE", SDL_SCANCODE_DELETE},
        {"INSERT", SDL_SCANCODE_INSERT},
        {"CAPSLOCK", SDL_SCANCODE_CAPSLOCK},
        {"LSHIFT", SDL_SCANCODE_LSHIFT},
        {"RSHIFT", SDL_SCANCODE_RSHIFT},
        {"LCTRL", SDL_SCANCODE_LCTRL},
        {"RCTRL", SDL_SCANCODE_RCTRL},
        {"LALT", SDL_SCANCODE_LALT},
        {"RALT", SDL_SCANCODE_RALT},
        {"F1", SDL_SCANCODE_F1},
        {"F2", SDL_SCANCODE_F2},
        {"F3", SDL_SCANCODE_F3},
        {"F4", SDL_SCANCODE_F4},
        {"F5", SDL_SCANCODE_F5},
        {"F6", SDL_SCANCODE_F6},
        {"F7", SDL_SCANCODE_F7},
        {"F8", SDL_SCANCODE_F8},
        {"F9", SDL_SCANCODE_F9},
        {"F10", SDL_SCANCODE_F10},
        {"F11", SDL_SCANCODE_F11},
        {"F12", SDL_SCANCODE_F12},
        {"INTERNATIONAL1", SDL_SCANCODE_INTERNATIONAL1},
    };

    auto it = kMap.find(up);
    if (it != kMap.end()) return (int)it->second;

    if (up.size() == 1 && up[0] >= 'A' && up[0] <= 'Z') {
        std::string name(1, up[0]);
        return (int)SDL_GetScancodeFromName(name.c_str());
    }
    if (up.size() == 1 && up[0] >= '0' && up[0] <= '9') {
        std::string name(1, up[0]);
        return (int)SDL_GetScancodeFromName(name.c_str());
    }

    for (char& c : tok) {
        if (c == '_') c = ' ';
    }
    SDL_Scancode sc = SDL_GetScancodeFromName(tok.c_str());
    return sc == SDL_SCANCODE_UNKNOWN ? -1 : (int)sc;
}

static bool load_mapper(const std::string& path, AppState& st) {
    std::ifstream in(path);
    if (!in.good()) return false;

    st.boxes.clear();
    st.box_index_by_id.clear();
    st.image_file.clear();
    st.system_name.clear();

    MapperBox cur;
    bool have_cur = false;
    bool in_bbox = false;
    bool in_overlay = false;
    int overlay_idx = 0;

    auto flush = [&]() {
        if (!have_cur || cur.id.empty()) return;
        if (cur.w < 1) cur.w = 1;
        if (cur.h < 1) cur.h = 1;
        st.box_index_by_id[cur.id] = st.boxes.size();
        st.boxes.push_back(cur);
        have_cur = false;
        in_bbox = false;
        in_overlay = false;
        overlay_idx = 0;
    };

    std::string line;
    while (std::getline(in, line)) {
        auto s = trim(line);
        if (s.empty() || s[0] == '#') continue;

        if (starts_with(s, "system_name:") && st.system_name.empty()) {
            st.system_name = unquote(trim(s.substr(std::strlen("system_name:"))));
            continue;
        }
        if (starts_with(s, "- id:") || starts_with(s, "id:")) {
            flush();
            have_cur = true;
            cur = MapperBox{};
            auto pos = s.find(':');
            if (pos != std::string::npos) cur.id = unquote(s.substr(pos + 1));
            continue;
        }

        if (starts_with(s, "file:") && st.image_file.empty()) {
            st.image_file = unquote(s.substr(5));
            continue;
        }

        if (!have_cur) continue;

        if (starts_with(s, "bbox:")) {
            in_bbox = true;
            in_overlay = false;
            continue;
        }
        if (starts_with(s, "overlay_color:")) {
            in_overlay = true;
            in_bbox = false;
            overlay_idx = 0;
            cur.has_overlay = true;
            continue;
        }

        if (in_bbox) {
            auto c = s.find(':');
            if (c != std::string::npos) {
                auto k = trim(s.substr(0, c));
                auto v = parse_int(trim(s.substr(c + 1)));
                if (!v.has_value()) continue;
                if (k == "x") cur.x = *v;
                else if (k == "y") cur.y = *v;
                else if (k == "width") cur.w = *v;
                else if (k == "height") cur.h = *v;
            }
            continue;
        }

        if (in_overlay && starts_with(s, "-")) {
            auto v = parse_int(trim(s.substr(1)));
            if (!v.has_value()) continue;
            if (overlay_idx == 0) cur.r = std::clamp(*v, 0, 255);
            if (overlay_idx == 1) cur.g = std::clamp(*v, 0, 255);
            if (overlay_idx == 2) cur.b = std::clamp(*v, 0, 255);
            overlay_idx++;
            continue;
        }
    }
    flush();

    std::string dir = dir_of(path);
    st.image_path = path_join(dir, st.image_file);
    return true;
}

static bool load_host_map(const std::string& path, AppState& st) {
    std::ifstream in(path);
    if (!in.good()) return false;
    st.bindings.clear();
    st.system_keys.clear();
    st.keyboard_kind = "ascii";
    st.has_focus_required = false;
    st.focus_required = false;

    Binding cur;
    bool have = false;
    bool in_presses = false;
    bool press_row_set = false;
    bool press_bit_set = false;
    bool in_system_keys = false;
    bool in_sys_obj = false;
    SystemKeyDef sys_cur;

    auto flush = [&]() {
        if (!have) return;
        st.bindings.push_back(cur);
        cur = Binding{};
        have = false;
        in_presses = false;
        press_row_set = false;
        press_bit_set = false;
    };
    auto flush_sys = [&]() {
        if (!in_sys_obj) return;
        if (!sys_cur.id.empty()) st.system_keys.push_back(sys_cur);
        sys_cur = SystemKeyDef{};
        in_sys_obj = false;
    };

    std::string line;
    while (std::getline(in, line)) {
        auto s = trim(line);
        if (s.empty() || s[0] == '#') continue;

        if (starts_with(s, "system_keys:")) {
            flush();
            flush_sys();
            in_system_keys = true;
            continue;
        }
        if (in_system_keys && starts_with(s, "bindings:")) {
            flush_sys();
            in_system_keys = false;
            continue;
        }
        if (starts_with(s, "kind:")) {
            st.keyboard_kind = trim(s.substr(std::strlen("kind:")));
            st.keyboard_kind = unquote(st.keyboard_kind);
            continue;
        }
        if (starts_with(s, "focus_required:")) {
            std::string v = trim(s.substr(std::strlen("focus_required:")));
            st.has_focus_required = true;
            st.focus_required = (v == "true" || v == "True" || v == "1");
            continue;
        }
        if (in_system_keys) {
            if (starts_with(s, "-")) {
                flush_sys();
                std::string rest = trim(s.substr(1));
                if (starts_with(rest, "id:")) {
                    in_sys_obj = true;
                    sys_cur.id = unquote(trim(rest.substr(3)));
                } else if (!rest.empty()) {
                    st.system_keys.push_back(SystemKeyDef{unquote(rest), false});
                }
                continue;
            }
            if (in_sys_obj && starts_with(s, "id:")) {
                sys_cur.id = unquote(trim(s.substr(3)));
                continue;
            }
            if (in_sys_obj && starts_with(s, "visual_feedback:")) {
                std::string v = trim(s.substr(std::strlen("visual_feedback:")));
                sys_cur.visual_feedback = (v == "true" || v == "True" || v == "1");
                continue;
            }
            continue;
        }

        if (starts_with(s, "- host_scancode:")) {
            flush();
            have = true;
            cur = Binding{};
            cur.host_token = trim(s.substr(std::strlen("- host_scancode:")));
            cur.scancode = parse_scancode_token(cur.host_token);
            continue;
        }
        if (starts_with(s, "- host_key:")) {
            flush();
            have = true;
            cur = Binding{};
            cur.host_token = trim(s.substr(std::strlen("- host_key:")));
            cur.scancode = parse_scancode_token(cur.host_token);
            continue;
        }
        if (!have) continue;

        if (starts_with(s, "host_scancode:")) {
            cur.host_token = trim(s.substr(std::strlen("host_scancode:")));
            cur.scancode = parse_scancode_token(cur.host_token);
            continue;
        }
        if (starts_with(s, "host_key:")) {
            cur.host_token = trim(s.substr(std::strlen("host_key:")));
            cur.scancode = parse_scancode_token(cur.host_token);
            continue;
        }

        if (starts_with(s, "mapper_key_id:")) {
            cur.mapper_key_id = unquote(s.substr(std::strlen("mapper_key_id:")));
            continue;
        }
        if (starts_with(s, "emulator_key_id:")) {
            cur.emulator_key_id = unquote(s.substr(std::strlen("emulator_key_id:")));
            continue;
        }
        if (starts_with(s, "system_key_id:")) {
            cur.system_key_id = unquote(s.substr(std::strlen("system_key_id:")));
            continue;
        }
        if (starts_with(s, "presses:")) {
            in_presses = true;
            continue;
        }
        if (in_presses) {
            // YAML list item: "- row: N" on the first line, then "bit: N" on the next.
            // Older/handwritten files may also use "row:" without the list prefix.
            if (starts_with(s, "-")) {
                s = trim(s.substr(1));
            }
            if (!press_row_set && starts_with(s, "row:")) {
                if (auto v = parse_int(trim(s.substr(4))); v.has_value()) {
                    cur.row = *v;
                    cur.has_press = true;
                    press_row_set = true;
                }
                continue;
            }
            if (!press_bit_set && starts_with(s, "bit:")) {
                if (auto v = parse_int(trim(s.substr(4))); v.has_value()) {
                    cur.bit = *v;
                    cur.has_press = true;
                    press_bit_set = true;
                }
                continue;
            }
        }
        if (starts_with(s, "ascii:")) {
            if (auto v = parse_int(trim(s.substr(6))); v.has_value()) {
                cur.has_ascii = true;
                cur.ascii = *v;
            }
            continue;
        }
        if (starts_with(s, "ascii_shift:")) {
            if (auto v = parse_int(trim(s.substr(12))); v.has_value()) {
                cur.has_ascii_shift = true;
                cur.ascii_shift = *v;
            }
            continue;
        }
        if (starts_with(s, "ascii_ctrl:")) {
            if (auto v = parse_int(trim(s.substr(11))); v.has_value()) {
                cur.has_ascii_ctrl = true;
                cur.ascii_ctrl = *v;
            }
            continue;
        }
    }
    flush();
    flush_sys();
    return true;
}

static std::vector<const Binding*> bindings_for(const AppState& st, const std::string& id) {
    std::vector<const Binding*> out;
    for (const auto& b : st.bindings) {
        if (b.mapper_key_id == id) out.push_back(&b);
    }
    return out;
}

static int find_binding_index_for_target(const AppState& st, int target_kind, const std::string& target_id) {
    if (target_id.empty()) return -1;
    for (size_t i = 0; i < st.bindings.size(); ++i) {
        const auto& b = st.bindings[i];
        if (target_kind == 0 && b.mapper_key_id == target_id) return (int)i;
        if (target_kind == 1 && b.system_key_id == target_id) return (int)i;
        if (target_kind == 2 && b.emulator_key_id == target_id) return (int)i;
    }
    return -1;
}

static void sync_binding_selection_for_target(AppState& st, int target_kind, const std::string& target_id) {
    int bi = find_binding_index_for_target(st, target_kind, target_id);
    st.selected_binding_global_index = bi;
    st.scroll_to_selected_binding = true;
    st.binding_edit_sync_index = -2;  // force resync of the binding editor view
    if (bi >= 0 && (size_t)bi < st.bindings.size()) {
        const auto& b = st.bindings[(size_t)bi];
        if (!b.mapper_key_id.empty()) {
            st.edit_target_kind = 0;
            st.edit_target_id = b.mapper_key_id;
        } else if (!b.system_key_id.empty()) {
            st.edit_target_kind = 1;
            st.edit_target_id = b.system_key_id;
        } else if (!b.emulator_key_id.empty()) {
            st.edit_target_kind = 2;
            st.edit_target_id = b.emulator_key_id;
        }
    }
}

static int find_box_at(const AppState& st, float ix, float iy) {
    for (int i = (int)st.boxes.size() - 1; i >= 0; --i) {
        const auto& b = st.boxes[(size_t)i];
        if (ix >= b.x && ix <= (b.x + b.w) && iy >= b.y && iy <= (b.y + b.h)) return i;
    }
    return -1;
}

static void rebuild_box_index(AppState& st) {
    st.box_index_by_id.clear();
    for (size_t i = 0; i < st.boxes.size(); ++i) {
        st.box_index_by_id[st.boxes[i].id] = i;
    }
}

static std::string unique_box_id(const AppState& st, const std::string& base) {
    if (base.empty()) return "KEY_NEW";
    if (st.box_index_by_id.find(base) == st.box_index_by_id.end()) return base;
    for (int i = 1; i < 10000; ++i) {
        std::string c = base + "_" + std::to_string(i);
        if (st.box_index_by_id.find(c) == st.box_index_by_id.end()) return c;
    }
    return base + "_X";
}

static std::vector<size_t> selected_ids_in_order(const AppState& st) {
    std::vector<size_t> out;
    if (st.primary >= 0 && (size_t)st.primary < st.boxes.size() && st.selected.count((size_t)st.primary)) {
        out.push_back((size_t)st.primary);
    }
    for (size_t i : st.selected) {
        if (!out.empty() && i == out[0]) continue;
        out.push_back(i);
    }
    std::sort(out.begin() + (out.empty() ? 0 : 1), out.end());
    return out;
}

static Snapshot make_snapshot(const AppState& st) {
    Snapshot s;
    s.boxes = st.boxes;
    s.bindings = st.bindings;
    s.system_keys = st.system_keys;
    s.selected = st.selected;
    s.primary = st.primary;
    s.selected_binding_global_index = st.selected_binding_global_index;
    s.selected_system_key_index = st.selected_system_key_index;
    s.selected_emulator_key_index = st.selected_emulator_key_index;
    s.alias_capture_target_kind = st.alias_capture_target_kind;
    s.alias_capture_target_id = st.alias_capture_target_id;
    s.edit_target_kind = st.edit_target_kind;
    s.edit_target_id = st.edit_target_id;
    s.system_edit_sync_index = st.system_edit_sync_index;
    s.system_edit_id = st.system_edit_id;
    s.system_edit_vf = st.system_edit_vf;
    s.binding_edit_sync_index = st.binding_edit_sync_index;
    s.binding_use_press = st.binding_use_press;
    s.binding_row = st.binding_row;
    s.binding_bit = st.binding_bit;
    s.binding_has_ascii = st.binding_has_ascii;
    s.binding_has_ascii_shift = st.binding_has_ascii_shift;
    s.binding_has_ascii_ctrl = st.binding_has_ascii_ctrl;
    s.binding_ascii = st.binding_ascii;
    s.binding_ascii_shift = st.binding_ascii_shift;
    s.binding_ascii_ctrl = st.binding_ascii_ctrl;
    s.capture_new_binding_mode = st.capture_new_binding_mode;
    return s;
}

static void apply_snapshot(AppState& st, const Snapshot& s) {
    st.boxes = s.boxes;
    st.bindings = s.bindings;
    st.system_keys = s.system_keys;
    st.selected = s.selected;
    st.primary = s.primary;
    st.selected_binding_global_index = s.selected_binding_global_index;
    st.selected_system_key_index = s.selected_system_key_index;
    st.selected_emulator_key_index = s.selected_emulator_key_index;
    st.alias_capture_target_kind = s.alias_capture_target_kind;
    st.alias_capture_target_id = s.alias_capture_target_id;
    st.edit_target_kind = s.edit_target_kind;
    st.edit_target_id = s.edit_target_id;
    st.system_edit_sync_index = s.system_edit_sync_index;
    st.system_edit_id = s.system_edit_id;
    st.system_edit_vf = s.system_edit_vf;
    st.binding_edit_sync_index = s.binding_edit_sync_index;
    st.binding_use_press = s.binding_use_press;
    st.binding_row = s.binding_row;
    st.binding_bit = s.binding_bit;
    st.binding_has_ascii = s.binding_has_ascii;
    st.binding_has_ascii_shift = s.binding_has_ascii_shift;
    st.binding_has_ascii_ctrl = s.binding_has_ascii_ctrl;
    st.binding_ascii = s.binding_ascii;
    st.binding_ascii_shift = s.binding_ascii_shift;
    st.binding_ascii_ctrl = s.binding_ascii_ctrl;
    st.capture_new_binding_mode = s.capture_new_binding_mode;
    st.box_index_by_id.clear();
    for (size_t i = 0; i < st.boxes.size(); ++i) {
        st.box_index_by_id[st.boxes[i].id] = i;
    }
}

static void push_undo(AppState& st) {
    st.undo_stack.push_back(make_snapshot(st));
    if (st.undo_stack.size() > 128) {
        st.undo_stack.erase(st.undo_stack.begin());
    }
    st.redo_stack.clear();
}

static bool undo_once(AppState& st) {
    if (st.undo_stack.empty()) return false;
    st.redo_stack.push_back(make_snapshot(st));
    Snapshot s = std::move(st.undo_stack.back());
    st.undo_stack.pop_back();
    apply_snapshot(st, s);
    return true;
}

static bool redo_once(AppState& st) {
    if (st.redo_stack.empty()) return false;
    st.undo_stack.push_back(make_snapshot(st));
    Snapshot s = std::move(st.redo_stack.back());
    st.redo_stack.pop_back();
    apply_snapshot(st, s);
    return true;
}

static std::string host_token_for_scancode(int sc) {
    if (sc < 0) return "";
    // Write numeric scancodes as plain numbers to keep runtime keyboard-map
    // compatibility across generated emulators (some older loaders do not accept
    // KEY_### prefixed tokens).
    return std::to_string(sc);
}

static bool scancode_from_textinput_deadkey(const std::string& text, int& out_scancode) {
    // Best-effort normalization for environments where X11/IME dead-key composition
    // prevents SDL from delivering KEYDOWN events (only SDL_TEXTINPUT arrives).
    //
    // Identity remains scancode-centric. When we have no scancode, map a few
    // common dead-key outputs back to typical physical keys.
    if (text.empty()) return false;
    // UTF-8 literals:
    // diaeresis U+00A8: C2 A8  (often Shift+6 on ABNT2)
    // acute U+00B4:     C2 B4
    if (text == "^" || text == "\xC2\xA8") {
        out_scancode = (int)SDL_SCANCODE_6;
        return true;
    }
    if (text == "'" || text == "\"" || text == "\xC2\xB4") {
        out_scancode = (int)SDL_SCANCODE_APOSTROPHE;
        return true;
    }
    if (text == "`" || text == "~") {
        out_scancode = (int)SDL_SCANCODE_GRAVE;
        return true;
    }
    return false;
}

static const char* kEmuKeys[] = {
    "EMU_POWER_TOGGLE",
    "EMU_RESET",
    "EMU_PAUSE_TOGGLE",
    "EMU_SAVE_SNAPSHOT",
    "EMU_LOAD_SNAPSHOT",
    "EMU_MUTE_TOGGLE",
    "EMU_VOLUME_UP",
    "EMU_VOLUME_DOWN",
    "EMU_CART_PICKER",
};

static bool is_system_key_id(const AppState& st, const std::string& id) {
    if (id.empty()) return false;
    for (const auto& sk : st.system_keys) {
        if (sk.id == id) return true;
    }
    return false;
}

static bool is_emulator_key_id(const std::string& id) {
    if (id.empty()) return false;
    for (const char* k : kEmuKeys) {
        if (id == k) return true;
    }
    return false;
}

// Some systems keep "system keys" as normal mapper ids (for runtime compatibility),
// while others use dedicated `system_key_id` bindings. Prefer `system_key_id` only
// if we actually have at least one binding using it.
static int preferred_target_kind_for_id(const AppState& st, const std::string& id) {
    if (is_emulator_key_id(id)) return 2; // emulator
    if (is_system_key_id(st, id)) {
        if (find_binding_index_for_target(st, 1, id) >= 0) return 1; // system
    }
    return 0; // mapper
}

static void align_selected(AppState& st, const char* mode) {
    auto ids = selected_ids_in_order(st);
    if (ids.size() < 2) return;
    const auto& a = st.boxes[ids[0]];
    int ax = a.x, ay = a.y, aw = a.w, ah = a.h;
    for (size_t k = 1; k < ids.size(); ++k) {
        auto& b = st.boxes[ids[k]];
        if (std::strcmp(mode, "left") == 0) b.x = ax;
        else if (std::strcmp(mode, "right") == 0) b.x = ax + aw - b.w;
        else if (std::strcmp(mode, "top") == 0) b.y = ay;
        else if (std::strcmp(mode, "bottom") == 0) b.y = ay + ah - b.h;
        else if (std::strcmp(mode, "hcenter") == 0) b.x = ax + (aw - b.w) / 2;
        else if (std::strcmp(mode, "vcenter") == 0) b.y = ay + (ah - b.h) / 2;
    }
    st.dirty_mapper = true;
}

static void size_selected(AppState& st, const char* mode) {
    auto ids = selected_ids_in_order(st);
    if (ids.size() < 2) return;
    const auto& a = st.boxes[ids[0]];
    for (size_t k = 1; k < ids.size(); ++k) {
        auto& b = st.boxes[ids[k]];
        if (std::strcmp(mode, "width") == 0 || std::strcmp(mode, "both") == 0) b.w = std::max(1, a.w);
        if (std::strcmp(mode, "height") == 0 || std::strcmp(mode, "both") == 0) b.h = std::max(1, a.h);
    }
    st.dirty_mapper = true;
}

static void distribute_selected(AppState& st, const char* mode) {
    auto ids = selected_ids_in_order(st);
    if (ids.size() < 3) return;
    std::vector<size_t> order = ids;
    if (std::strcmp(mode, "horizontal") == 0) {
        std::sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return st.boxes[a].x + st.boxes[a].w * 0.5f < st.boxes[b].x + st.boxes[b].w * 0.5f;
        });
        float start = st.boxes[order.front()].x + st.boxes[order.front()].w * 0.5f;
        float end = st.boxes[order.back()].x + st.boxes[order.back()].w * 0.5f;
        float step = (end - start) / (float)(order.size() - 1);
        for (size_t i = 1; i + 1 < order.size(); ++i) {
            auto& b = st.boxes[order[i]];
            float c = start + step * (float)i;
            b.x = (int)std::lround(c - b.w * 0.5f);
        }
    } else if (std::strcmp(mode, "vertical") == 0) {
        std::sort(order.begin(), order.end(), [&](size_t a, size_t b) {
            return st.boxes[a].y + st.boxes[a].h * 0.5f < st.boxes[b].y + st.boxes[b].h * 0.5f;
        });
        float start = st.boxes[order.front()].y + st.boxes[order.front()].h * 0.5f;
        float end = st.boxes[order.back()].y + st.boxes[order.back()].h * 0.5f;
        float step = (end - start) / (float)(order.size() - 1);
        for (size_t i = 1; i + 1 < order.size(); ++i) {
            auto& b = st.boxes[order[i]];
            float c = start + step * (float)i;
            b.y = (int)std::lround(c - b.h * 0.5f);
        }
    }
    st.dirty_mapper = true;
}

static std::string leading_ws(const std::string& s) {
    size_t i = 0;
    while (i < s.size() && std::isspace((unsigned char)s[i])) i++;
    return s.substr(0, i);
}

static bool save_mapper_boxes(const AppState& st, std::string& err) {
    std::ifstream in(st.mapper_path);
    if (!in.good()) {
        err = "cannot open mapper for read: " + st.mapper_path;
        return false;
    }
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line)) lines.push_back(line);

    std::unordered_map<std::string, const MapperBox*> by_id;
    by_id.reserve(st.boxes.size());
    for (const auto& b : st.boxes) by_id[b.id] = &b;
    std::unordered_set<std::string> seen_ids;

    std::vector<std::string> out;
    out.reserve(lines.size() + 64);

    std::string current_id;
    const MapperBox* current_box = nullptr;
    bool in_key = false;
    bool key_keep = true;
    bool saw_overlay = false;
    std::string key_ws = "  ";
    bool in_image = false;
    std::string image_ws;
    bool image_seen = false;
    bool image_file_seen = false;

    auto append_overlay_if_missing = [&]() {
        if (!in_key || !key_keep || current_box == nullptr || !current_box->has_overlay || saw_overlay) return;
        out.push_back(key_ws + "  overlay_color:");
        out.push_back(key_ws + "  - " + std::to_string(current_box->r));
        out.push_back(key_ws + "  - " + std::to_string(current_box->g));
        out.push_back(key_ws + "  - " + std::to_string(current_box->b));
    };

    for (size_t i = 0; i < lines.size(); ++i) {
        const std::string& raw = lines[i];
        const std::string s = trim(raw);
        const std::string ws = leading_ws(raw);

        if (!in_key && starts_with(s, "image:")) {
            if (in_image && image_seen && !image_file_seen && !st.image_file.empty()) {
                out.push_back(image_ws + "  file: " + st.image_file);
            }
            in_image = true;
            image_seen = true;
            image_file_seen = false;
            image_ws = ws;
            out.push_back(raw);
            continue;
        }
        if (in_image) {
            if (!s.empty() && ws.size() <= image_ws.size()) {
                if (!image_file_seen && !st.image_file.empty()) {
                    out.push_back(image_ws + "  file: " + st.image_file);
                }
                in_image = false;
            } else if (starts_with(s, "file:")) {
                out.push_back(ws + "file: " + st.image_file);
                image_file_seen = true;
                continue;
            }
        }

        if (starts_with(s, "- id:") || starts_with(s, "id:")) {
            if (in_key) append_overlay_if_missing();
            in_key = true;
            saw_overlay = false;
            key_ws = ws;
            auto pos = s.find(':');
            current_id = (pos == std::string::npos) ? "" : unquote(s.substr(pos + 1));
            auto it = by_id.find(current_id);
            current_box = (it == by_id.end()) ? nullptr : it->second;
            key_keep = (current_box != nullptr);
            if (current_box != nullptr) {
                seen_ids.insert(current_id);
                out.push_back(raw);
            }
            continue;
        }

        if (in_key && !key_keep) {
            // Entire key was removed in UI; skip every line in this block.
            continue;
        }

        if (in_key && starts_with(s, "bbox:") && current_box != nullptr) {
            out.push_back(ws + "bbox:");
            out.push_back(ws + "  x: " + std::to_string(current_box->x));
            out.push_back(ws + "  y: " + std::to_string(current_box->y));
            out.push_back(ws + "  width: " + std::to_string(std::max(1, current_box->w)));
            out.push_back(ws + "  height: " + std::to_string(std::max(1, current_box->h)));
            size_t j = i + 1;
            while (j < lines.size()) {
                std::string sj = trim(lines[j]);
                std::string wj = leading_ws(lines[j]);
                if (wj.size() <= ws.size()) break;
                if (starts_with(sj, "x:") || starts_with(sj, "y:") || starts_with(sj, "width:") || starts_with(sj, "height:")) {
                    ++j;
                    continue;
                }
                break;
            }
            i = j - 1;
            continue;
        }

        if (in_key && starts_with(s, "overlay_color:") && current_box != nullptr) {
            saw_overlay = true;
            if (current_box->has_overlay) {
                out.push_back(ws + "overlay_color:");
                out.push_back(ws + "- " + std::to_string(current_box->r));
                out.push_back(ws + "- " + std::to_string(current_box->g));
                out.push_back(ws + "- " + std::to_string(current_box->b));
            }
            size_t j = i + 1;
            while (j < lines.size()) {
                std::string sj = trim(lines[j]);
                std::string wj = leading_ws(lines[j]);
                if (wj.size() <= ws.size()) break;
                if (starts_with(sj, "-")) {
                    ++j;
                    continue;
                }
                break;
            }
            i = j - 1;
            continue;
        }

        out.push_back(raw);
    }

    if (in_image && image_seen && !image_file_seen && !st.image_file.empty()) {
        out.push_back(image_ws + "  file: " + st.image_file);
    }
    if (in_key) append_overlay_if_missing();
    if (!image_seen && !st.image_file.empty()) {
        out.push_back("image:");
        out.push_back("  file: " + st.image_file);
    }

    for (const auto& b : st.boxes) {
        if (seen_ids.count(b.id) != 0) continue;
        out.push_back("  - id: " + b.id);
        out.push_back("    section: system");
        out.push_back("    row: 1");
        out.push_back("    column: 1");
        out.push_back("    multi_legend: false");
        out.push_back("    legend:");
        out.push_back("    - " + b.id);
        out.push_back("    legend_combos:");
        out.push_back("      " + b.id + ":");
        out.push_back("      - " + b.id);
        out.push_back("    bbox:");
        out.push_back("      x: " + std::to_string(std::max(0, b.x)));
        out.push_back("      y: " + std::to_string(std::max(0, b.y)));
        out.push_back("      width: " + std::to_string(std::max(1, b.w)));
        out.push_back("      height: " + std::to_string(std::max(1, b.h)));
        if (b.has_overlay) {
            out.push_back("    overlay_color:");
            out.push_back("    - " + std::to_string(std::clamp(b.r, 0, 255)));
            out.push_back("    - " + std::to_string(std::clamp(b.g, 0, 255)));
            out.push_back("    - " + std::to_string(std::clamp(b.b, 0, 255)));
        }
    }

    std::ofstream o(st.mapper_path, std::ios::trunc);
    if (!o.good()) {
        err = "cannot open mapper for write: " + st.mapper_path;
        return false;
    }
    for (const auto& l : out) o << l << "\n";
    return true;
}

static bool save_host_map(const AppState& st, std::string& err) {
    std::ofstream o(st.host_map_path, std::ios::trunc);
    if (!o.good()) {
        err = "cannot open host map for write: " + st.host_map_path;
        return false;
    }

    o << "keyboard:\n";
    o << "  kind: " << (st.keyboard_kind.empty() ? "ascii" : st.keyboard_kind) << "\n";
    if (st.has_focus_required) {
        o << "  focus_required: " << (st.focus_required ? "true" : "false") << "\n";
    }
    if (!st.system_keys.empty()) {
        o << "  system_keys:\n";
        for (const auto& sk : st.system_keys) {
            o << "  - id: " << sk.id << "\n";
            o << "    visual_feedback: " << (sk.visual_feedback ? "true" : "false") << "\n";
        }
    }
    o << "  bindings:\n";
    for (const auto& b : st.bindings) {
        if (b.scancode >= 0) {
            const std::string tok = !b.host_token.empty() ? b.host_token : host_token_for_scancode(b.scancode);
            o << "  - host_scancode: " << tok << "\n";
        } else if (!b.host_token.empty()) {
            o << "  - host_key: " << b.host_token << "\n";
        } else {
            continue;
        }
        if (!b.mapper_key_id.empty()) {
            o << "    mapper_key_id: " << b.mapper_key_id << "\n";
        }
        if (!b.emulator_key_id.empty()) {
            o << "    emulator_key_id: " << b.emulator_key_id << "\n";
        }
        if (!b.system_key_id.empty()) {
            o << "    system_key_id: " << b.system_key_id << "\n";
        }
        if (b.has_press) {
            o << "    presses:\n";
            o << "    - row: " << b.row << "\n";
            o << "      bit: " << b.bit << "\n";
        }
        if (b.has_ascii) o << "    ascii: " << b.ascii << "\n";
        if (b.has_ascii_shift) o << "    ascii_shift: " << b.ascii_shift << "\n";
        if (b.has_ascii_ctrl) o << "    ascii_ctrl: " << b.ascii_ctrl << "\n";
    }
    return true;
}

static std::vector<std::string> validate_host_map_links(const AppState& st) {
    std::vector<std::string> errs;
    std::unordered_set<int> seen_scancodes;
    std::unordered_set<std::string> system_ids;
    for (const auto& sk : st.system_keys) system_ids.insert(sk.id);

    for (const auto& b : st.bindings) {
        if (b.scancode < 0 && b.host_token.empty()) {
            errs.push_back("binding missing host_scancode/host_key");
            continue;
        }
        if (b.scancode >= 0) {
            if (seen_scancodes.count(b.scancode) != 0) {
                errs.push_back("duplicate host_scancode: " + std::to_string(b.scancode));
            } else {
                seen_scancodes.insert(b.scancode);
            }
        }

        int target_count = 0;
        if (!b.mapper_key_id.empty()) target_count++;
        if (!b.system_key_id.empty()) target_count++;
        if (!b.emulator_key_id.empty()) target_count++;
        if (target_count != 1) {
            errs.push_back("host_scancode " + std::to_string(b.scancode) +
                           ": expected exactly one target (mapper/system/emulator)");
            continue;
        }

        if (!b.mapper_key_id.empty()) {
            if (st.box_index_by_id.find(b.mapper_key_id) == st.box_index_by_id.end()) {
                errs.push_back("host_scancode " + std::to_string(b.scancode) +
                               ": mapper_key_id not found: " + b.mapper_key_id);
            }
            if (st.keyboard_kind == "ascii" || st.keyboard_kind == "ASCII") {
                if (!b.has_ascii && !b.has_ascii_shift && !b.has_ascii_ctrl) {
                    errs.push_back("host_scancode " + std::to_string(b.scancode) +
                                   ": missing payload for kind=ascii (need ascii/ascii_shift/ascii_ctrl)");
                }
            } else if (st.keyboard_kind == "matrix" || st.keyboard_kind == "MATRIX") {
                if (!b.has_press) {
                    errs.push_back("host_scancode " + std::to_string(b.scancode) +
                                   ": missing presses payload for kind=matrix");
                }
            }
        }
        if (!b.system_key_id.empty() && system_ids.count(b.system_key_id) == 0) {
            errs.push_back("host_scancode " + std::to_string(b.scancode) +
                           ": system_key_id not found: " + b.system_key_id);
        }
        if (b.has_press) {
            if (b.row < 0 || b.row > 63) {
                errs.push_back("host_scancode " + std::to_string(b.scancode) +
                               ": row out of range [0..63]");
            }
            if (b.bit < 0 || b.bit > 7) {
                errs.push_back("host_scancode " + std::to_string(b.scancode) +
                               ": bit out of range [0..7]");
            }
        }
        auto check_ascii = [&](bool hasv, int v, const char* name) {
            if (hasv && (v < 0 || v > 255)) {
                errs.push_back("host_scancode " + std::to_string(b.scancode) +
                               ": " + std::string(name) + " out of range [0..255]");
            }
        };
        check_ascii(b.has_ascii, b.ascii, "ascii");
        check_ascii(b.has_ascii_shift, b.ascii_shift, "ascii_shift");
        check_ascii(b.has_ascii_ctrl, b.ascii_ctrl, "ascii_ctrl");
    }
    return errs;
}

static bool load_image_texture(SDL_Renderer* ren, const std::string& path, SDL_Texture** out_tex, SDL_Surface** out_surface, int* out_w, int* out_h) {
    if (out_tex) *out_tex = nullptr;
    if (out_surface) *out_surface = nullptr;
    if (out_w) *out_w = 0;
    if (out_h) *out_h = 0;
    if (path.empty()) return false;

    SDL_Surface* src = IMG_Load(path.c_str());
    if (!src) return false;
    SDL_Surface* conv = SDL_ConvertSurfaceFormat(src, SDL_PIXELFORMAT_ARGB8888, 0);
    SDL_FreeSurface(src);
    if (!conv) return false;

    SDL_Texture* tex = SDL_CreateTextureFromSurface(ren, conv);
    if (!tex) {
        SDL_FreeSurface(conv);
        return false;
    }
    if (out_tex) *out_tex = tex;
    if (out_surface) *out_surface = conv;
    if (out_w) *out_w = conv->w;
    if (out_h) *out_h = conv->h;
    return true;
}

int main(int argc, char** argv) {
    AppState st;
    st.mapper_path = std::getenv("MAPPER") ? std::getenv("MAPPER") : "examples/hosts/cpc464/cpc_keyboard_mapper.yaml";
    st.host_map_path = std::getenv("HOST_MAP") ? std::getenv("HOST_MAP") : "examples/hosts/cpc464/host_keyboard_cpc.yaml";

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--help" || a == "-h") {
            std::printf("Usage: keymapper_native [--mapper <path>] [--host-map <path>]\n");
            return 0;
        }
    if (a == "--mapper" && i + 1 < argc) st.mapper_path = argv[++i];
    else if (a == "--host-map" && i + 1 < argc) st.host_map_path = argv[++i];
    }

    {
        const char *disable_dead = std::getenv("PASM_DISABLE_DEADKEYS");
        if (disable_dead == NULL || disable_dead[0] != '0') {
            #if defined(__linux__)
            // Keep scancode flow deterministic by disabling XIM dead-key composition for this process.
            setenv("XMODIFIERS", "@im=none", 1);
            setenv("GTK_IM_MODULE", "xim", 0);
            setenv("QT_IM_MODULE", "xim", 0);
            #endif
        }
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS) != 0) {
        std::fprintf(stderr, "SDL init failed: %s\n", SDL_GetError());
        return 1;
    }
    IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG);

    SDL_Window* win = SDL_CreateWindow("PASM Keymapper Native", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1600, 920, SDL_WINDOW_RESIZABLE);
    SDL_Renderer* ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!ren) ren = SDL_CreateRenderer(win, -1, 0);
    if (!win || !ren) {
        std::fprintf(stderr, "SDL window/renderer failed: %s\n", SDL_GetError());
        return 1;
    }

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    ImGui::StyleColorsDark();
    ImGui_ImplSDL2_InitForSDLRenderer(win, ren);
    ImGui_ImplSDLRenderer2_Init(ren);

    if (!load_mapper(st.mapper_path, st)) {
        std::fprintf(stderr, "Failed loading mapper: %s\n", st.mapper_path.c_str());
    }
    if (!load_host_map(st.host_map_path, st)) {
        std::fprintf(stderr, "Failed loading host map: %s\n", st.host_map_path.c_str());
    }

    SDL_Texture* image_tex = nullptr;
    SDL_Surface* image_surface = nullptr;
    int img_w = 0;
    int img_h = 0;
    (void)load_image_texture(ren, st.image_path, &image_tex, &image_surface, &img_w, &img_h);
    st.auto_fit_pending = true;

    SDL_Cursor* cursor_arrow = SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_ARROW);
    SDL_Cursor* cursor_cross = SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_CROSSHAIR);
    SDL_Cursor* cursor_size_nwse = SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_SIZENWSE);
    SDL_Cursor* cursor_size_all = SDL_CreateSystemCursor(SDL_SYSTEM_CURSOR_SIZEALL);
    if (cursor_arrow) SDL_SetCursor(cursor_arrow);

    bool running = true;
    std::string status_msg;
    uint32_t status_until_ms = 0;
    while (running) {
        // IMPORTANT: Text input (IME/dead-key composition) can cause X11 to filter KeyPress events
        // before SDL sees them (dead keys show up only as TEXTINPUT). We therefore keep SDL text
        // input enabled only while the UI is actively editing text, and we switch it *before*
        // polling events (so it affects the current frame's event stream).
        // Keep SDL text input enabled during capture/edit modes too, so we can
        // recover dead-key presses that do not produce KEYDOWN events.
        const bool desired_text_input =
            st.want_text_input_prev || st.alias_capture_mode || st.capture_new_binding_mode || st.edit_mode;
        if (desired_text_input && !st.sdl_text_input_active) {
            SDL_StartTextInput();
            st.sdl_text_input_active = true;
        } else if (!desired_text_input && st.sdl_text_input_active) {
            SDL_StopTextInput();
            st.sdl_text_input_active = false;
        }

        std::unordered_set<int> down_scancodes_this_frame;

        auto handle_scancode_press = [&](int sc, int32_t key_sym, const char* key_name, bool ui_typing) -> bool {
            if (sc < 0) return false;

            // Mirror KEYDOWN bookkeeping for inspector/debug.
            st.last_scancode = sc;
            st.last_down = true;
            st.last_repeat = 0;
            st.last_keycode = key_sym;
            st.last_key_name = key_name ? std::string(key_name) : std::string();

            // If the user is actively typing into an ImGui text widget (blinking caret),
            // do not trigger any app/canvas actions (delete, undo, selection changes, etc).
            // We still record last key info and allow the renderer to show key down/up state.
            if (ui_typing) {
                return false;
            }

            const bool ctrl = ((SDL_GetModState() & KMOD_CTRL) != 0);

            // 1) Alias capture modes (highest priority).
            if (st.alias_capture_mode) {
                if (sc == (int)SDL_SCANCODE_ESCAPE) {
                    st.alias_capture_mode = false;
                    st.alias_capture_target_id.clear();
                    status_msg = "Alias capture canceled";
                    status_until_ms = SDL_GetTicks() + 2500u;
                    return true;
                }
                if (!st.alias_capture_target_id.empty()) {
                    const std::string target_id = st.alias_capture_target_id;
                    push_undo(st);
                    Binding nb;
                    nb.scancode = sc;
                    nb.host_token = host_token_for_scancode(sc);
                    if (st.alias_capture_target_kind == 0) nb.mapper_key_id = target_id;
                    else if (st.alias_capture_target_kind == 1) nb.system_key_id = target_id;
                    else if (st.alias_capture_target_kind == 2) nb.emulator_key_id = target_id;

                    if (st.alias_capture_target_kind == 0) {
                        auto binds = bindings_for(st, target_id);
                        if (!binds.empty()) {
                            const Binding* src = binds[0];
                            nb.has_press = src->has_press;
                            nb.row = src->row;
                            nb.bit = src->bit;
                            nb.has_ascii = src->has_ascii;
                            nb.has_ascii_shift = src->has_ascii_shift;
                            nb.has_ascii_ctrl = src->has_ascii_ctrl;
                            nb.ascii = src->ascii;
                            nb.ascii_shift = src->ascii_shift;
                            nb.ascii_ctrl = src->ascii_ctrl;
                        }
                    }

                    bool replaced = false;
                    for (auto& b : st.bindings) {
                        if (b.scancode == sc) {
                            b = nb;
                            replaced = true;
                            break;
                        }
                    }
                    if (!replaced) st.bindings.push_back(nb);
                    st.alias_capture_mode = false;
                    st.alias_capture_target_id.clear();
                    st.dirty_map = true;
                    status_msg = "Alias mapped: scancode " + std::to_string(sc) + " -> " + target_id;
                    status_until_ms = SDL_GetTicks() + 3000u;
                }
                return true;
            }

            // 2) Add-host-binding capture mode.
            if (st.capture_new_binding_mode) {
                if (sc == (int)SDL_SCANCODE_ESCAPE) {
                    st.capture_new_binding_mode = false;
                    status_msg = "Add host binding canceled";
                    status_until_ms = SDL_GetTicks() + 2500u;
                    return true;
                }
                int existing = -1;
                for (size_t i = 0; i < st.bindings.size(); ++i) {
                    if (st.bindings[i].scancode == sc) { existing = (int)i; break; }
                }
                if (existing >= 0) {
                    st.selected_binding_global_index = existing;
                    st.scroll_to_selected_binding = true;
                    st.binding_edit_sync_index = -2;
                    status_msg = "Host binding already exists for scancode " + std::to_string(sc);
                    status_until_ms = SDL_GetTicks() + 2500u;
                } else {
                    push_undo(st);
                    Binding nb;
                    nb.scancode = sc;
                    nb.host_token = host_token_for_scancode(sc);
                    st.bindings.push_back(nb);
                    st.selected_binding_global_index = (int)st.bindings.size() - 1;
                    st.scroll_to_selected_binding = true;
                    st.binding_edit_sync_index = -2;
                    st.dirty_map = true;
                    status_msg = "Added host binding for scancode " + std::to_string(sc);
                    status_until_ms = SDL_GetTicks() + 2500u;
                }
                st.capture_new_binding_mode = false;
                return true;
            }

            // 3) Edit mode mapping: key presses are mapping commands.
            if (st.edit_mode && !ctrl && !ui_typing) {
                std::string target_mapper_id;
                std::string target_system_id;
                if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                    const std::string pid = st.boxes[(size_t)st.primary].id;
                    int kind = preferred_target_kind_for_id(st, pid);
                    if (kind == 1) target_system_id = pid;
                    else if (kind == 2) {
                        // Editing emulator mapping uses the emulator-key panel selection instead.
                    } else target_mapper_id = pid;
                } else if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
                    target_system_id = st.system_keys[(size_t)st.selected_system_key_index].id;
                }

                if (!target_mapper_id.empty() || !target_system_id.empty()) {
                    push_undo(st);
                    Binding nb;
                    nb.scancode = sc;
                    nb.host_token = host_token_for_scancode(sc);
                    nb.mapper_key_id = target_mapper_id;
                    nb.system_key_id = target_system_id;

                    bool replaced = false;
                    for (auto& b : st.bindings) {
                        if (b.scancode == sc) {
                            b = nb;
                            replaced = true;
                            break;
                        }
                    }
                    if (!replaced) st.bindings.push_back(nb);
                    st.dirty_map = true;
                    status_msg = "Assigned scancode " + std::to_string(sc) + " via Edit Mode";
                    status_until_ms = SDL_GetTicks() + 2500u;
                    return true;
                }
            }

            // 4) Normal key press: select the binding in the list.
            if (!ui_typing && !ctrl) {
                int idx = -1;
                for (size_t i = 0; i < st.bindings.size(); ++i) {
                    if (st.bindings[i].scancode == sc) { idx = (int)i; break; }
                }
                if (idx >= 0 && (size_t)idx < st.bindings.size()) {
                    const Binding& b = st.bindings[(size_t)idx];
                    st.selected_binding_global_index = idx;
                    st.scroll_to_selected_binding = true;
                    st.binding_edit_sync_index = -2;

                    if (!b.mapper_key_id.empty()) {
                        st.edit_target_kind = 0;
                        st.edit_target_id = b.mapper_key_id;
                    } else if (!b.system_key_id.empty()) {
                        st.edit_target_kind = 1;
                        st.edit_target_id = b.system_key_id;
                    } else if (!b.emulator_key_id.empty()) {
                        st.edit_target_kind = 2;
                        st.edit_target_id = b.emulator_key_id;
                    } else {
                        st.edit_target_kind = 0;
                        st.edit_target_id.clear();
                    }

                    st.selected_system_key_index = -1;
                    st.selected_emulator_key_index = -1;
                    if (!b.system_key_id.empty()) {
                        for (size_t si = 0; si < st.system_keys.size(); ++si) {
                            if (st.system_keys[si].id == b.system_key_id) { st.selected_system_key_index = (int)si; break; }
                        }
                        st.system_edit_sync_index = -2;
                    } else if (!b.emulator_key_id.empty()) {
                        const int emu_key_count = (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0]));
                        for (int ei = 0; ei < emu_key_count; ++ei) {
                            if (b.emulator_key_id == kEmuKeys[ei]) { st.selected_emulator_key_index = ei; break; }
                        }
                    } else if (!b.mapper_key_id.empty()) {
                        if (is_system_key_id(st, b.mapper_key_id)) {
                            for (size_t si = 0; si < st.system_keys.size(); ++si) {
                                if (st.system_keys[si].id == b.mapper_key_id) { st.selected_system_key_index = (int)si; break; }
                            }
                            st.system_edit_sync_index = -2;
                        } else if (is_emulator_key_id(b.mapper_key_id)) {
                            const int emu_key_count = (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0]));
                            for (int ei = 0; ei < emu_key_count; ++ei) {
                                if (b.mapper_key_id == kEmuKeys[ei]) { st.selected_emulator_key_index = ei; break; }
                            }
                        }
                    }
                } else {
                    st.selected_binding_global_index = -1;
                    st.scroll_to_selected_binding = false;
                    st.binding_edit_sync_index = -2;
                    st.edit_target_kind = 0;
                    st.edit_target_id.clear();
                    st.selected_system_key_index = -1;
                    st.selected_emulator_key_index = -1;
                    st.system_edit_sync_index = -2;

                    status_msg =
                        "No host binding for scancode " + std::to_string(sc) + " (" +
                        std::string(SDL_GetScancodeName((SDL_Scancode)sc)) + ")";
                    status_until_ms = SDL_GetTicks() + 2500u;
                }
                return true;
            }

            return false;
        };

        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            ImGui_ImplSDL2_ProcessEvent(&e);
            if (e.type == SDL_QUIT) {
                st.quit_requested = true;
                if (st.dirty_mapper) st.quit_stage = 1;
                else if (st.dirty_map) st.quit_stage = 2;
                else st.quit_stage = 3;
            }
            if (e.type == SDL_TEXTINPUT) {
                st.last_text_input = e.text.text ? std::string(e.text.text) : std::string();
                const bool ui_typing = st.want_text_input_prev;
                if (!ui_typing && (st.alias_capture_mode || st.capture_new_binding_mode || st.edit_mode)) {
                    int sc = -1;
                    if (scancode_from_textinput_deadkey(st.last_text_input, sc)) {
                        if (down_scancodes_this_frame.count(sc) == 0) {
                            (void)handle_scancode_press(sc, 0, "TEXTINPUT", ui_typing);
                        }
                    }
                }
            }
            if (e.type == SDL_KEYDOWN || e.type == SDL_KEYUP) {
                st.last_scancode = (int)e.key.keysym.scancode;
                st.last_keycode = (int32_t)e.key.keysym.sym;
                st.last_key_name = SDL_GetKeyName(e.key.keysym.sym);
                st.last_down = e.type == SDL_KEYDOWN;
                st.last_repeat = e.key.repeat;

                if (e.type == SDL_KEYDOWN && e.key.repeat == 0) {
                    down_scancodes_this_frame.insert((int)e.key.keysym.scancode);
                    // Only suppress while the user is actively typing/editing a widget.
                    const bool ui_typing = st.want_text_input_prev;
                    if (handle_scancode_press((int)e.key.keysym.scancode, (int32_t)e.key.keysym.sym, SDL_GetKeyName(e.key.keysym.sym), ui_typing)) {
                        continue;
                    }

                    // While typing in a text widget, don't run global shortcuts or canvas actions.
                    if (ui_typing) {
                        continue;
                    }

                    if (e.key.keysym.scancode == SDL_SCANCODE_ESCAPE) {
                        bool handled_escape = false;
                        if (st.pick_color_mode) {
                            st.pick_color_mode = false;
                            status_msg = "Color pick canceled";
                            status_until_ms = SDL_GetTicks() + 1800u;
                            handled_escape = true;
                        }
                        if (st.marquee_active) {
                            st.marquee_active = false;
                            handled_escape = true;
                        }
                        if (st.dragging || st.resizing) {
                            st.dragging = false;
                            st.resizing = false;
                            st.drag_snapshot_taken = false;
                            handled_escape = true;
                        }
                        if (handled_escape) continue;
                    }

                    const bool ctrl = (e.key.keysym.mod & KMOD_CTRL) != 0;
                    const bool shift = (e.key.keysym.mod & KMOD_SHIFT) != 0;
                    if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_Z) {
                        if (undo_once(st)) {
                            st.dirty_mapper = true;
                            st.dirty_map = true;
                        }
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_Y) {
                        if (redo_once(st)) {
                            st.dirty_mapper = true;
                            st.dirty_map = true;
                        }
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_Q) {
                        st.quit_requested = true;
                        if (st.dirty_mapper) st.quit_stage = 1;
                        else if (st.dirty_map) st.quit_stage = 2;
                        else st.quit_stage = 3;
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_S) {
                        std::string err;
                        bool ok_mapper = true;
                        bool ok_map = true;
                        if (st.dirty_mapper) ok_mapper = save_mapper_boxes(st, err);
                        if (ok_mapper && st.dirty_map) {
                            auto val_errs = validate_host_map_links(st);
                            if (!val_errs.empty()) {
                                st.validation_errors = std::move(val_errs);
                                st.validation_popup_title = "Invalid Host Map Links";
                                st.validation_popup_open = true;
                                ok_map = false;
                                err = "host map validation failed";
                            } else {
                                ok_map = save_host_map(st, err);
                            }
                        }
                        if (ok_mapper && ok_map) {
                            st.dirty_mapper = false;
                            st.dirty_map = false;
                            st.validation_errors.clear();
                            status_msg = "Saved mapper + host map";
                        } else {
                            status_msg = "Save failed: " + err;
                        }
                        status_until_ms = SDL_GetTicks() + 3000u;
                    } else if (!ctrl && e.key.keysym.scancode == SDL_SCANCODE_F2) {
                        if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                            st.rename_popup_open = true;
                            st.rename_text = st.boxes[(size_t)st.primary].id;
                            ImGui::OpenPopup("rename_key_popup");
                        }
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_0) {
                        st.zoom = 1.0f;
                        st.pan = ImVec2(0.0f, 0.0f);
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_N) {
                        push_undo(st);
                        MapperBox nb;
                        nb.id = unique_box_id(st, "KEY_NEW");
                        nb.x = (int)std::max(0.0f, (-st.pan.x / st.zoom) + 100.0f);
                        nb.y = (int)std::max(0.0f, (-st.pan.y / st.zoom) + 100.0f);
                        nb.w = 88;
                        nb.h = 34;
                        st.boxes.push_back(nb);
                        rebuild_box_index(st);
                        size_t ni = st.boxes.size() - 1;
                        st.selected.clear();
                        st.selected.insert(ni);
                        st.primary = (int)ni;
                        st.dirty_mapper = true;
                    } else if (ctrl && e.key.keysym.scancode == SDL_SCANCODE_D) {
                        if (!st.selected.empty()) {
                            push_undo(st);
                            auto ids = selected_ids_in_order(st);
                            std::vector<size_t> new_ids;
                            for (size_t i : ids) {
                                const auto& src = st.boxes[i];
                                MapperBox nb = src;
                                nb.id = unique_box_id(st, src.id + "_copy");
                                nb.x += 12;
                                nb.y += 12;
                                st.boxes.push_back(nb);
                                new_ids.push_back(st.boxes.size() - 1);
                                rebuild_box_index(st);
                            }
                            st.selected.clear();
                            for (size_t ni : new_ids) st.selected.insert(ni);
                            st.primary = new_ids.empty() ? -1 : (int)new_ids.front();
                            st.dirty_mapper = true;
                        }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_L) {
                        if (st.selected.size() >= 2) { push_undo(st); align_selected(st, "left"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_R) {
                        if (st.selected.size() >= 2) { push_undo(st); align_selected(st, "right"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_T) {
                        if (st.selected.size() >= 2) { push_undo(st); align_selected(st, "top"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_B) {
                        if (st.selected.size() >= 2) { push_undo(st); align_selected(st, "bottom"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_W) {
                        if (st.selected.size() >= 2) { push_undo(st); size_selected(st, "width"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_H) {
                        if (st.selected.size() >= 2) { push_undo(st); size_selected(st, "height"); }
                    } else if (ctrl && !shift && e.key.keysym.scancode == SDL_SCANCODE_E) {
                        if (st.selected.size() >= 2) { push_undo(st); size_selected(st, "both"); }
                    } else if (ctrl && shift && e.key.keysym.scancode == SDL_SCANCODE_H) {
                        if (st.selected.size() >= 3) { push_undo(st); distribute_selected(st, "horizontal"); }
                    } else if (ctrl && shift && e.key.keysym.scancode == SDL_SCANCODE_V) {
                        if (st.selected.size() >= 3) { push_undo(st); distribute_selected(st, "vertical"); }
                    } else if (!ctrl && (e.key.keysym.scancode == SDL_SCANCODE_DELETE || e.key.keysym.scancode == SDL_SCANCODE_BACKSPACE)) {
                        if (!st.selected.empty()) {
                            push_undo(st);
                            std::vector<MapperBox> kept;
                            kept.reserve(st.boxes.size());
                            for (size_t i = 0; i < st.boxes.size(); ++i) {
                                if (st.selected.count(i) == 0) kept.push_back(st.boxes[i]);
                            }
                            st.boxes.swap(kept);
                            st.box_index_by_id.clear();
                            for (size_t i = 0; i < st.boxes.size(); ++i) st.box_index_by_id[st.boxes[i].id] = i;
                            st.selected.clear();
                            st.primary = -1;
                            st.dirty_mapper = true;
                        }
                    }

                    if (st.edit_mode && !ctrl && !st.alias_capture_mode && !ui_typing) {
                        std::string target_mapper_id;
                        std::string target_system_id;
                        if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                            const std::string pid = st.boxes[(size_t)st.primary].id;
                            bool is_system = false;
                            for (const auto& sk : st.system_keys) {
                                if (sk.id == pid) { is_system = true; break; }
                            }
                            if (is_system) target_system_id = pid;
                            else target_mapper_id = pid;
                        } else if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
                            target_system_id = st.system_keys[(size_t)st.selected_system_key_index].id;
                        }

                        if (!target_mapper_id.empty() || !target_system_id.empty()) {
                            const int sc = (int)e.key.keysym.scancode;
                            push_undo(st);
                            Binding nb;
                            nb.scancode = sc;
                            nb.host_token = host_token_for_scancode(sc);
                            nb.mapper_key_id = target_mapper_id;
                            nb.system_key_id = target_system_id;
                            if (!target_mapper_id.empty()) {
                                auto binds = bindings_for(st, target_mapper_id);
                                if (!binds.empty()) {
                                    const Binding* src = binds[0];
                                    nb.has_press = src->has_press;
                                    nb.row = src->row;
                                    nb.bit = src->bit;
                                    nb.has_ascii = src->has_ascii;
                                    nb.has_ascii_shift = src->has_ascii_shift;
                                    nb.has_ascii_ctrl = src->has_ascii_ctrl;
                                    nb.ascii = src->ascii;
                                    nb.ascii_shift = src->ascii_shift;
                                    nb.ascii_ctrl = src->ascii_ctrl;
                                }
                            }

                            bool replaced = false;
                            for (auto& b : st.bindings) {
                                if (b.scancode == sc) {
                                    b = nb;
                                    replaced = true;
                                    break;
                                }
                            }
                            if (!replaced) st.bindings.push_back(nb);
                            st.dirty_map = true;
                            status_msg = "Assigned scancode " + std::to_string(sc) + " via Edit Mode";
                            status_until_ms = SDL_GetTicks() + 2500u;
                        }
                    }
                }

            }
        }

        // State-based key press detection (fallback for dead keys / IME-filtered KEYDOWN events).
        // This matches the emulator's use of SDL_GetKeyboardState().
        {
            int count = 0;
            const Uint8* ks = SDL_GetKeyboardState(&count);
            if (ks != NULL && count > 0) {
                if ((int)st.prev_key_state.size() != count) {
                    st.prev_key_state.assign(ks, ks + count);
                    st.key_state_count = count;
                } else {
                    const bool ui_typing = st.want_text_input_prev;
                    for (int sc = 0; sc < count; ++sc) {
                        if (ks[sc] == 0) continue;
                        if (st.prev_key_state[(size_t)sc] != 0) continue;
                        if (down_scancodes_this_frame.count(sc) != 0) continue; // already handled via KEYDOWN
                        (void)handle_scancode_press(sc, 0, SDL_GetScancodeName((SDL_Scancode)sc), ui_typing);
                    }
                    st.prev_key_state.assign(ks, ks + count);
                }
            }
        }

        ImGui_ImplSDLRenderer2_NewFrame();
        ImGui_ImplSDL2_NewFrame();
        ImGui::NewFrame();
        // Record for next frame's event polling.
        st.want_text_input_prev = ImGui::GetIO().WantTextInput;

        auto do_save_mapper = [&]() {
            std::string err;
            if (save_mapper_boxes(st, err)) {
                st.dirty_mapper = false;
                status_msg = "Mapper saved";
            } else {
                status_msg = "Save failed: " + err;
            }
            status_until_ms = SDL_GetTicks() + 4000u;
        };
        auto do_save_host_map = [&]() {
            auto val_errs = validate_host_map_links(st);
            if (!val_errs.empty()) {
                st.validation_errors = std::move(val_errs);
                st.validation_popup_title = "Invalid Host Map Links";
                st.validation_popup_open = true;
                status_msg = "Host map validation failed";
                status_until_ms = SDL_GetTicks() + 4000u;
                return;
            }
            std::string err;
            if (save_host_map(st, err)) {
                st.dirty_map = false;
                st.validation_errors.clear();
                status_msg = "Host map saved";
            } else {
                status_msg = "Host map save failed: " + err;
            }
            status_until_ms = SDL_GetTicks() + 4000u;
        };

        ImGuiViewport* vp = ImGui::GetMainViewport();
        ImVec2 vp_size = vp->Size;
        float inspector_w = std::max(380.0f, vp_size.x * 0.28f);
        float canvas_w = std::max(320.0f, vp_size.x - inspector_w);

        ImGui::SetNextWindowPos(vp->Pos);
        ImGui::SetNextWindowSize(ImVec2(canvas_w, vp_size.y));
        ImGuiWindowFlags panel_flags = ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_MenuBar;
        ImGui::Begin("Canvas", nullptr, panel_flags);
        if (ImGui::BeginMenuBar()) {
            if (ImGui::BeginMenu("File")) {
                if (ImGui::MenuItem("Save Mapper", "Ctrl+S", false, st.dirty_mapper)) do_save_mapper();
                if (ImGui::MenuItem("Save Host Map", nullptr, false, st.dirty_map)) do_save_host_map();
                if (ImGui::MenuItem("Reload")) {
                    std::unordered_set<std::string> prev_ids;
                    for (size_t i : st.selected) {
                        if (i < st.boxes.size()) prev_ids.insert(st.boxes[i].id);
                    }
                    load_mapper(st.mapper_path, st);
                    load_host_map(st.host_map_path, st);
                    if (image_tex) { SDL_DestroyTexture(image_tex); image_tex = nullptr; }
                    if (image_surface) { SDL_FreeSurface(image_surface); image_surface = nullptr; }
                    img_w = 0;
                    img_h = 0;
                    (void)load_image_texture(ren, st.image_path, &image_tex, &image_surface, &img_w, &img_h);
                    st.auto_fit_pending = true;
                    st.selected.clear();
                    st.primary = -1;
                    for (size_t i = 0; i < st.boxes.size(); ++i) {
                        if (prev_ids.count(st.boxes[i].id)) {
                            st.selected.insert(i);
                            st.primary = (int)i;
                        }
                    }
                    st.dirty_mapper = false;
                    st.dirty_map = false;
                    status_msg = "Reloaded mapper + host map";
                    status_until_ms = SDL_GetTicks() + 3000u;
                }
                ImGui::Separator();
                if (ImGui::MenuItem("Quit", "Ctrl+Q")) {
                    st.quit_requested = true;
                    if (st.dirty_mapper) st.quit_stage = 1;
                    else if (st.dirty_map) st.quit_stage = 2;
                    else st.quit_stage = 3;
                }
                ImGui::EndMenu();
            }
            if (ImGui::BeginMenu("Edit")) {
                if (ImGui::MenuItem("Undo", "Ctrl+Z")) {
                    if (undo_once(st)) {
                        st.dirty_mapper = true;
                        st.dirty_map = true;
                    }
                }
                if (ImGui::MenuItem("Redo", "Ctrl+Y")) {
                    if (redo_once(st)) {
                        st.dirty_mapper = true;
                        st.dirty_map = true;
                    }
                }
                ImGui::Separator();
                if (ImGui::MenuItem("Create New Box", "Ctrl+N")) {
                    push_undo(st);
                    MapperBox nb;
                    nb.id = unique_box_id(st, "KEY_NEW");
                    nb.x = (int)std::max(0.0f, (-st.pan.x / st.zoom) + 100.0f);
                    nb.y = (int)std::max(0.0f, (-st.pan.y / st.zoom) + 100.0f);
                    nb.w = 88;
                    nb.h = 34;
                    st.boxes.push_back(nb);
                    rebuild_box_index(st);
                    size_t ni = st.boxes.size() - 1;
                    st.selected.clear();
                    st.selected.insert(ni);
                    st.primary = (int)ni;
                    st.dirty_mapper = true;
                }
                if (ImGui::MenuItem("Duplicate Selected", "Ctrl+D", false, !st.selected.empty())) {
                    push_undo(st);
                    auto ids = selected_ids_in_order(st);
                    std::vector<size_t> new_ids;
                    for (size_t i : ids) {
                        const auto& src = st.boxes[i];
                        MapperBox nb = src;
                        nb.id = unique_box_id(st, src.id + "_copy");
                        nb.x += 12;
                        nb.y += 12;
                        st.boxes.push_back(nb);
                        new_ids.push_back(st.boxes.size() - 1);
                        rebuild_box_index(st);
                    }
                    st.selected.clear();
                    for (size_t ni : new_ids) st.selected.insert(ni);
                    st.primary = new_ids.empty() ? -1 : (int)new_ids.front();
                    st.dirty_mapper = true;
                }
                if (ImGui::MenuItem("Delete Selected", "Del", false, !st.selected.empty())) {
                    push_undo(st);
                    std::vector<MapperBox> kept;
                    kept.reserve(st.boxes.size());
                    for (size_t i = 0; i < st.boxes.size(); ++i) {
                        if (st.selected.count(i) == 0) kept.push_back(st.boxes[i]);
                    }
                    st.boxes.swap(kept);
                    rebuild_box_index(st);
                    st.selected.clear();
                    st.primary = -1;
                    st.dirty_mapper = true;
                }
                ImGui::EndMenu();
            }
            ImGui::EndMenuBar();
        }
        if (ImGui::Button("Fit")) {
            st.auto_fit_pending = true;
            st.manual_view = false;
        }
        ImGui::SameLine();
        if (ImGui::Button("-")) {
            st.zoom = std::max(0.10f, st.zoom - 0.10f);
            st.manual_view = true;
        }
        ImGui::SameLine();
        if (ImGui::Button("+")) {
            st.zoom = std::min(10.0f, st.zoom + 0.10f);
            st.manual_view = true;
        }
        ImGui::SameLine();
        ImGui::SetNextItemWidth(220.0f);
        if (ImGui::SliderFloat("##zoom", &st.zoom, 0.10f, 10.0f, "%.2fx")) {
            st.manual_view = true;
        }
        ImGui::SameLine();
        ImGui::Text("Zoom %.0f%%", st.zoom * 100.0f);
        ImVec2 origin = ImGui::GetCursorScreenPos();
        ImVec2 avail_full = ImGui::GetContentRegionAvail();

        // If the user hasn't manually adjusted the view, keep the content fit+centered on resize.
        if (!st.manual_view) {
            if (std::fabs(avail_full.x - st.last_canvas_avail.x) > 1.0f || std::fabs(avail_full.y - st.last_canvas_avail.y) > 1.0f) {
                st.auto_fit_pending = true;
            }
        }
        st.last_canvas_avail = avail_full;

        float content_w_units = (float)std::max(1, img_w);
        float content_h_units = (float)std::max(1, img_h);
        for (const auto& b : st.boxes) {
            content_w_units = std::max(content_w_units, (float)(b.x + b.w));
            content_h_units = std::max(content_h_units, (float)(b.y + b.h));
        }
        if (st.auto_fit_pending) {
            float zx = (avail_full.x > 1.0f) ? (avail_full.x / content_w_units) : 1.0f;
            float zy = (avail_full.y > 1.0f) ? (avail_full.y / content_h_units) : 1.0f;
            st.zoom = std::clamp(std::min(zx, zy), 0.10f, 10.0f);
            float cw = content_w_units * st.zoom;
            float ch = content_h_units * st.zoom;
            st.pan.x = (avail_full.x - cw) * 0.5f;
            st.pan.y = (avail_full.y - ch) * 0.5f;
            st.auto_fit_pending = false;
        }

        float content_w_px = content_w_units * st.zoom;
        float content_h_px = content_h_units * st.zoom;

        const float sb = 16.0f;
        bool need_hbar = content_w_px > avail_full.x;
        bool need_vbar = content_h_px > avail_full.y;
        if (need_hbar && !need_vbar && content_h_px > (avail_full.y - sb)) need_vbar = true;
        if (need_vbar && !need_hbar && content_w_px > (avail_full.x - sb)) need_hbar = true;

        ImVec2 avail = avail_full;
        if (need_hbar) avail.y = std::max(40.0f, avail.y - sb - 2.0f);
        if (need_vbar) avail.x = std::max(40.0f, avail.x - sb - 2.0f);

        auto clamp_pan = [&]() {
            float min_pan_x = (content_w_px <= avail.x) ? 0.0f : (avail.x - content_w_px);
            float max_pan_x = (content_w_px <= avail.x) ? (avail.x - content_w_px) : 0.0f;
            float min_pan_y = (content_h_px <= avail.y) ? 0.0f : (avail.y - content_h_px);
            float max_pan_y = (content_h_px <= avail.y) ? (avail.y - content_h_px) : 0.0f;
            st.pan.x = std::clamp(st.pan.x, min_pan_x, max_pan_x);
            st.pan.y = std::clamp(st.pan.y, min_pan_y, max_pan_y);
        };
        clamp_pan();

        ImGui::InvisibleButton("canvas_btn", avail, ImGuiButtonFlags_MouseButtonLeft | ImGuiButtonFlags_MouseButtonRight | ImGuiButtonFlags_MouseButtonMiddle);
        bool hovered = ImGui::IsItemHovered();
        bool active = ImGui::IsItemActive();
        ImDrawList* dl = ImGui::GetWindowDrawList();

        if (hovered) {
            float wheel = io.MouseWheel;
            if (wheel != 0.0f) {
                float old = st.zoom;
                st.zoom = std::clamp(st.zoom + wheel * 0.10f, 0.10f, 10.0f);
                st.manual_view = true;
                ImVec2 mouse = io.MousePos;
                float ix = (mouse.x - origin.x - st.pan.x) / old;
                float iy = (mouse.y - origin.y - st.pan.y) / old;
                st.pan.x = (mouse.x - origin.x) - ix * st.zoom;
                st.pan.y = (mouse.y - origin.y) - iy * st.zoom;
                clamp_pan();
            }
        }

        if (active && ImGui::IsMouseDragging(ImGuiMouseButton_Middle)) {
            st.pan.x += io.MouseDelta.x;
            st.pan.y += io.MouseDelta.y;
            st.manual_view = true;
            clamp_pan();
        }

        if (image_tex) {
            ImVec2 p0(origin.x + st.pan.x, origin.y + st.pan.y);
            ImVec2 p1(p0.x + img_w * st.zoom, p0.y + img_h * st.zoom);
            dl->AddImage((ImTextureID)image_tex, p0, p1);
        }

        std::unordered_set<size_t> pressed_boxes;
        std::unordered_map<std::string, bool> system_vf;
        for (const auto& sk : st.system_keys) system_vf[sk.id] = sk.visual_feedback;
        const Uint8* key_state = SDL_GetKeyboardState(nullptr);
        for (const auto& b : st.bindings) {
            if (b.scancode < 0 || b.scancode >= SDL_NUM_SCANCODES) continue;
            if (!key_state[b.scancode]) continue;
            if (!b.mapper_key_id.empty()) {
                auto it = st.box_index_by_id.find(b.mapper_key_id);
                if (it != st.box_index_by_id.end()) pressed_boxes.insert(it->second);
            } else if (!b.system_key_id.empty()) {
                auto vf_it = system_vf.find(b.system_key_id);
                if (vf_it != system_vf.end() && vf_it->second) {
                    auto it = st.box_index_by_id.find(b.system_key_id);
                    if (it != st.box_index_by_id.end()) pressed_boxes.insert(it->second);
                }
            }
        }

        int hovered_idx = -1;
        if (hovered) {
            float ix = (io.MousePos.x - origin.x - st.pan.x) / st.zoom;
            float iy = (io.MousePos.y - origin.y - st.pan.y) / st.zoom;
            hovered_idx = find_box_at(st, ix, iy);
        }
        bool left_clicked = hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Left);
        bool handled_left_click = false;
        bool over_resize_handle = false;
        if (st.primary >= 0 && (size_t)st.primary < st.boxes.size() && st.selected.count((size_t)st.primary) != 0) {
            const auto& pb = st.boxes[(size_t)st.primary];
            ImVec2 hp0(origin.x + st.pan.x + (pb.x + pb.w) * st.zoom - 10.0f, origin.y + st.pan.y + (pb.y + pb.h) * st.zoom - 10.0f);
            ImVec2 hp1(hp0.x + 10.0f, hp0.y + 10.0f);
            if (io.MousePos.x >= hp0.x && io.MousePos.x <= hp1.x && io.MousePos.y >= hp0.y && io.MousePos.y <= hp1.y) {
                over_resize_handle = true;
            }
        }

        if (st.pick_color_mode) {
            if (cursor_cross) SDL_SetCursor(cursor_cross);
            if (left_clicked) {
                float ix = (io.MousePos.x - origin.x - st.pan.x) / st.zoom;
                float iy = (io.MousePos.y - origin.y - st.pan.y) / st.zoom;
                int px = (int)std::floor(ix);
                int py = (int)std::floor(iy);
                if (image_surface && px >= 0 && py >= 0 && px < image_surface->w && py < image_surface->h) {
                    push_undo(st);
                    uint8_t* p = (uint8_t*)image_surface->pixels + py * image_surface->pitch + px * 4;
                    int b = p[0];
                    int g = p[1];
                    int r = p[2];
                    if (st.selected.empty() && st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                        st.selected.insert((size_t)st.primary);
                    }
                    for (size_t si : st.selected) {
                        st.boxes[si].has_overlay = true;
                        st.boxes[si].r = r;
                        st.boxes[si].g = g;
                        st.boxes[si].b = b;
                    }
                    st.dirty_mapper = true;
                    status_msg = "Picked image color";
                    status_until_ms = SDL_GetTicks() + 2000u;
                } else {
                    status_msg = "No image pixel at cursor";
                    status_until_ms = SDL_GetTicks() + 2000u;
                }
                st.pick_color_mode = false;
                handled_left_click = true;
            }
        } else {
            if (over_resize_handle && cursor_size_nwse) {
                SDL_SetCursor(cursor_size_nwse);
            } else if (hovered_idx >= 0 && cursor_size_all) {
                SDL_SetCursor(cursor_size_all);
            } else if (cursor_arrow) {
                SDL_SetCursor(cursor_arrow);
            }
        }

        if (left_clicked && !handled_left_click && over_resize_handle) {
            if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                st.dragging = false;
                st.resizing = true;
                st.drag_snapshot_taken = false;
                st.drag_start_img = ImVec2((io.MousePos.x - origin.x - st.pan.x) / st.zoom, (io.MousePos.y - origin.y - st.pan.y) / st.zoom);
                st.resize_start_w = st.boxes[(size_t)st.primary].w;
                st.resize_start_h = st.boxes[(size_t)st.primary].h;
                handled_left_click = true;
            }
        }

        if (left_clicked && !handled_left_click && hovered_idx >= 0) {
            bool toggle = io.KeyCtrl || io.KeyShift;
            size_t idx = (size_t)hovered_idx;
            if (toggle) {
                if (st.selected.count(idx)) st.selected.erase(idx);
                else st.selected.insert(idx);
                if (st.selected.empty()) st.primary = -1;
                else st.primary = hovered_idx;
            } else {
                bool clicked_selected = st.selected.count(idx) != 0;
                if (!clicked_selected) {
                    st.selected.clear();
                    st.selected.insert(idx);
                    st.primary = hovered_idx;
                } else if (st.primary < 0) {
                    st.primary = hovered_idx;
                }
                st.dragging = true;
                st.drag_snapshot_taken = false;
                st.drag_start_img = ImVec2((io.MousePos.x - origin.x - st.pan.x) / st.zoom, (io.MousePos.y - origin.y - st.pan.y) / st.zoom);
                st.drag_origin.clear();
                for (size_t i : st.selected) {
                    st.drag_origin[i] = ImVec2((float)st.boxes[i].x, (float)st.boxes[i].y);
                }
            }
            // When a bbox is selected, auto-select the corresponding host binding in the list.
            // This mirrors the legacy UI behavior and keeps mapping edits focused on the relevant binding.
            if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                const std::string pid = st.boxes[(size_t)st.primary].id;
                // Determine whether this bbox represents a mapper key, a system key, or an emulator key.
                int kind = preferred_target_kind_for_id(st, pid); // 0 mapper, 1 system, 2 emulator

                // Keep side-panels coherent with canvas selection.
                if (kind == 1) {
                    st.selected_emulator_key_index = -1;
                    st.selected_system_key_index = -1;
                    for (size_t si = 0; si < st.system_keys.size(); ++si) {
                        if (st.system_keys[si].id == pid) { st.selected_system_key_index = (int)si; break; }
                    }
                    st.system_edit_sync_index = -2;
                } else if (kind == 2) {
                    st.selected_system_key_index = -1;
                    st.selected_emulator_key_index = -1;
                    const int emu_key_count = (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0]));
                    for (int ei = 0; ei < emu_key_count; ++ei) {
                        if (pid == kEmuKeys[ei]) { st.selected_emulator_key_index = ei; break; }
                    }
                } else {
                    // Mapper key selection clears system/emulator side-panel selections.
                    st.selected_system_key_index = -1;
                    st.selected_emulator_key_index = -1;
                }

                sync_binding_selection_for_target(st, kind, pid);
            }
            handled_left_click = true;
        }

        if (hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Right) && hovered_idx >= 0) {
            size_t idx = (size_t)hovered_idx;
            // Source key rule:
            // - If right-clicked key is already selected, make it the source (primary).
            // - Otherwise keep current source/selection unchanged.
            if (st.selected.count(idx) != 0) {
                st.primary = hovered_idx;
            }
            ImGui::OpenPopup("canvas_ctx");
        } else if (hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
            ImGui::OpenPopup("canvas_ctx");
        }

        if (left_clicked && !handled_left_click && hovered_idx < 0) {
            st.marquee_active = true;
            st.marquee_add = io.KeyShift;
            st.marquee_toggle = io.KeyCtrl;
            st.marquee_start = io.MousePos;
            st.marquee_curr = io.MousePos;
            handled_left_click = true;
        }
        if (st.marquee_active && ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
            st.marquee_curr = io.MousePos;
        }
        if (st.resizing && ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
            if (!st.drag_snapshot_taken) {
                push_undo(st);
                st.drag_snapshot_taken = true;
            }
            float cx = (io.MousePos.x - origin.x - st.pan.x) / st.zoom;
            float cy = (io.MousePos.y - origin.y - st.pan.y) / st.zoom;
            int dx = (int)std::lround(cx - st.drag_start_img.x);
            int dy = (int)std::lround(cy - st.drag_start_img.y);
            if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                auto& b = st.boxes[(size_t)st.primary];
                b.w = std::max(1, st.resize_start_w + dx);
                b.h = std::max(1, st.resize_start_h + dy);
                st.dirty_mapper = true;
            }
        }
        if (st.dragging && ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
            if (!st.drag_snapshot_taken) {
                push_undo(st);
                st.drag_snapshot_taken = true;
            }
            float cx = (io.MousePos.x - origin.x - st.pan.x) / st.zoom;
            float cy = (io.MousePos.y - origin.y - st.pan.y) / st.zoom;
            int dx = (int)std::lround(cx - st.drag_start_img.x);
            int dy = (int)std::lround(cy - st.drag_start_img.y);
            for (auto& kv : st.drag_origin) {
                auto& b = st.boxes[kv.first];
                b.x = std::max(0, (int)kv.second.x + dx);
                b.y = std::max(0, (int)kv.second.y + dy);
            }
            st.dirty_mapper = true;
        }

        if ((st.dragging || st.resizing) && ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
            const float edge = 20.0f;
            const float step = 12.0f;
            if (io.MousePos.x < origin.x + edge) st.pan.x += step;
            else if (io.MousePos.x > origin.x + avail.x - edge) st.pan.x -= step;
            if (io.MousePos.y < origin.y + edge) st.pan.y += step;
            else if (io.MousePos.y > origin.y + avail.y - edge) st.pan.y -= step;
            st.manual_view = true;
            clamp_pan();
        }

        if (st.dragging && ImGui::IsMouseReleased(ImGuiMouseButton_Left)) {
            st.dragging = false;
            st.drag_snapshot_taken = false;
        }
        if (st.resizing && ImGui::IsMouseReleased(ImGuiMouseButton_Left)) {
            st.resizing = false;
            st.drag_snapshot_taken = false;
        }
        if (st.marquee_active && ImGui::IsMouseReleased(ImGuiMouseButton_Left)) {
            float x0 = std::min(st.marquee_start.x, st.marquee_curr.x);
            float y0 = std::min(st.marquee_start.y, st.marquee_curr.y);
            float x1 = std::max(st.marquee_start.x, st.marquee_curr.x);
            float y1 = std::max(st.marquee_start.y, st.marquee_curr.y);

            std::unordered_set<size_t> hit;
            for (size_t i = 0; i < st.boxes.size(); ++i) {
                const auto& b = st.boxes[i];
                ImVec2 p0(origin.x + st.pan.x + b.x * st.zoom, origin.y + st.pan.y + b.y * st.zoom);
                ImVec2 p1(p0.x + b.w * st.zoom, p0.y + b.h * st.zoom);
                bool overlap = !(p1.x < x0 || p0.x > x1 || p1.y < y0 || p0.y > y1);
                if (overlap) hit.insert(i);
            }

            if (st.marquee_toggle) {
                for (size_t i : hit) {
                    if (st.selected.count(i)) st.selected.erase(i);
                    else st.selected.insert(i);
                }
            } else if (st.marquee_add) {
                for (size_t i : hit) st.selected.insert(i);
            } else {
                st.selected = hit;
            }

            if (st.selected.empty()) {
                st.primary = -1;
            } else {
                bool primary_valid = st.primary >= 0 && st.selected.count((size_t)st.primary) != 0;
                if (!primary_valid) {
                    if (!hit.empty()) st.primary = (int)*hit.begin();
                    else st.primary = (int)*st.selected.begin();
                }
            }
            st.marquee_active = false;
        }

        if (ImGui::BeginPopup("canvas_ctx")) {
            bool multi = st.selected.size() >= 2;
            bool dist = st.selected.size() >= 3;
            if (ImGui::BeginMenu("Align")) {
                if (ImGui::MenuItem("Left", nullptr, false, multi)) { push_undo(st); align_selected(st, "left"); }
                if (ImGui::MenuItem("Right", nullptr, false, multi)) { push_undo(st); align_selected(st, "right"); }
                if (ImGui::MenuItem("Top", nullptr, false, multi)) { push_undo(st); align_selected(st, "top"); }
                if (ImGui::MenuItem("Bottom", nullptr, false, multi)) { push_undo(st); align_selected(st, "bottom"); }
                if (ImGui::MenuItem("Horizontal Center", nullptr, false, multi)) { push_undo(st); align_selected(st, "hcenter"); }
                if (ImGui::MenuItem("Vertical Center", nullptr, false, multi)) { push_undo(st); align_selected(st, "vcenter"); }
                ImGui::EndMenu();
            }
            if (ImGui::BeginMenu("Size")) {
                if (ImGui::MenuItem("Match Width", nullptr, false, multi)) { push_undo(st); size_selected(st, "width"); }
                if (ImGui::MenuItem("Match Height", nullptr, false, multi)) { push_undo(st); size_selected(st, "height"); }
                if (ImGui::MenuItem("Match Size", nullptr, false, multi)) { push_undo(st); size_selected(st, "both"); }
                ImGui::EndMenu();
            }
            if (ImGui::BeginMenu("Distribute")) {
                if (ImGui::MenuItem("Horizontal", nullptr, false, dist)) { push_undo(st); distribute_selected(st, "horizontal"); }
                if (ImGui::MenuItem("Vertical", nullptr, false, dist)) { push_undo(st); distribute_selected(st, "vertical"); }
                ImGui::EndMenu();
            }
            if (ImGui::BeginMenu("Color")) {
                bool multi_color = st.selected.size() >= 2 && st.primary >= 0 && (size_t)st.primary < st.boxes.size();
                bool has_sel = !st.selected.empty() && st.primary >= 0 && (size_t)st.primary < st.boxes.size();
                if (ImGui::MenuItem(st.pick_color_mode ? "Cancel Pick Color" : "Pick Color From Image", nullptr, false, has_sel)) {
                    st.pick_color_mode = !st.pick_color_mode;
                }
                if (ImGui::MenuItem("Apply Primary RGB To Selected", nullptr, false, has_sel)) {
                    push_undo(st);
                    const auto& src = st.boxes[(size_t)st.primary];
                    int r = src.has_overlay ? src.r : 80;
                    int g = src.has_overlay ? src.g : 160;
                    int b = src.has_overlay ? src.b : 255;
                    for (size_t i : st.selected) {
                        st.boxes[i].has_overlay = true;
                        st.boxes[i].r = std::clamp(r, 0, 255);
                        st.boxes[i].g = std::clamp(g, 0, 255);
                        st.boxes[i].b = std::clamp(b, 0, 255);
                    }
                    st.dirty_mapper = true;
                }
                if (ImGui::MenuItem("Make Same Color", nullptr, false, multi_color)) {
                    push_undo(st);
                    const auto& src = st.boxes[(size_t)st.primary];
                    int r = src.has_overlay ? src.r : 80;
                    int g = src.has_overlay ? src.g : 160;
                    int b = src.has_overlay ? src.b : 255;
                    for (size_t i : st.selected) {
                        if ((int)i == st.primary) continue;
                        st.boxes[i].has_overlay = true;
                        st.boxes[i].r = std::clamp(r, 0, 255);
                        st.boxes[i].g = std::clamp(g, 0, 255);
                        st.boxes[i].b = std::clamp(b, 0, 255);
                    }
                    st.dirty_mapper = true;
                }
                if (ImGui::MenuItem("Clear Overlay From Selected", nullptr, false, has_sel)) {
                    push_undo(st);
                    for (size_t i : st.selected) st.boxes[i].has_overlay = false;
                    st.dirty_mapper = true;
                }
                ImGui::EndMenu();
            }
            ImGui::Separator();
            if (ImGui::MenuItem("Create New Box")) {
                push_undo(st);
                MapperBox nb;
                nb.id = unique_box_id(st, "KEY_NEW");
                nb.x = (int)std::max(0.0f, (-st.pan.x / st.zoom) + 120.0f);
                nb.y = (int)std::max(0.0f, (-st.pan.y / st.zoom) + 120.0f);
                nb.w = 88;
                nb.h = 34;
                st.boxes.push_back(nb);
                rebuild_box_index(st);
                size_t ni = st.boxes.size() - 1;
                st.selected.clear();
                st.selected.insert(ni);
                st.primary = (int)ni;
                st.dirty_mapper = true;
            }
            if (ImGui::MenuItem("Duplicate Selected", nullptr, false, !st.selected.empty())) {
                push_undo(st);
                auto ids = selected_ids_in_order(st);
                std::vector<size_t> new_ids;
                for (size_t i : ids) {
                    const auto& src = st.boxes[i];
                    MapperBox nb = src;
                    nb.id = unique_box_id(st, src.id + "_copy");
                    nb.x += 12;
                    nb.y += 12;
                    st.boxes.push_back(nb);
                    new_ids.push_back(st.boxes.size() - 1);
                    rebuild_box_index(st);
                }
                st.selected.clear();
                for (size_t ni : new_ids) st.selected.insert(ni);
                st.primary = new_ids.empty() ? -1 : (int)new_ids.front();
                st.dirty_mapper = true;
            }
            if (ImGui::MenuItem("Delete Selected", nullptr, false, !st.selected.empty())) {
                push_undo(st);
                std::vector<MapperBox> kept;
                kept.reserve(st.boxes.size());
                for (size_t i = 0; i < st.boxes.size(); ++i) {
                    if (st.selected.count(i) == 0) kept.push_back(st.boxes[i]);
                }
                st.boxes.swap(kept);
                rebuild_box_index(st);
                st.selected.clear();
                st.primary = -1;
                st.dirty_mapper = true;
            }
            if (ImGui::MenuItem("Clear Selection")) {
                st.selected.clear();
                st.primary = -1;
            }
            ImGui::EndPopup();
        }

        for (size_t i = 0; i < st.boxes.size(); ++i) {
            const auto& b = st.boxes[i];
            ImVec2 p0(origin.x + st.pan.x + b.x * st.zoom, origin.y + st.pan.y + b.y * st.zoom);
            ImVec2 p1(p0.x + b.w * st.zoom, p0.y + b.h * st.zoom);
            bool sel = st.selected.count(i) > 0;
            bool prs = pressed_boxes.count(i) > 0;
            ImU32 fill;
            if (prs) fill = IM_COL32(255, 90, 90, 120);
            else if (sel) fill = IM_COL32(255, 220, 90, 110);
            else if (b.has_overlay) fill = IM_COL32(b.r, b.g, b.b, 90);
            else fill = IM_COL32(80, 160, 255, 70);
            ImU32 stroke = prs ? IM_COL32(255, 120, 120, 255) : (sel ? IM_COL32(255, 180, 20, 255) : IM_COL32(20, 20, 20, 220));
            dl->AddRectFilled(p0, p1, fill);
            dl->AddRect(p0, p1, stroke, 0.0f, 0, sel ? 2.0f : 1.0f);
            if (sel && st.primary == (int)i) {
                ImVec2 hp0(p1.x - 10.0f, p1.y - 10.0f);
                ImVec2 hp1(p1.x, p1.y);
                dl->AddRectFilled(hp0, hp1, IM_COL32(245, 245, 245, 220));
                dl->AddRect(hp0, hp1, IM_COL32(20, 20, 20, 240), 0.0f, 0, 1.0f);
            }
        }
        if (st.marquee_active) {
            ImVec2 a(std::min(st.marquee_start.x, st.marquee_curr.x), std::min(st.marquee_start.y, st.marquee_curr.y));
            ImVec2 b(std::max(st.marquee_start.x, st.marquee_curr.x), std::max(st.marquee_start.y, st.marquee_curr.y));
            dl->AddRectFilled(a, b, IM_COL32(80, 160, 255, 40));
            dl->AddRect(a, b, IM_COL32(120, 190, 255, 220), 0.0f, 0, 1.5f);
        }

        if (need_hbar) {
            float max_off_x = std::max(0.0f, content_w_px - avail.x);
            float off_x = std::clamp(-st.pan.x, 0.0f, max_off_x);
            ImGui::SetCursorScreenPos(ImVec2(origin.x, origin.y + avail.y + 2.0f));
            ImGui::SetNextItemWidth(avail.x);
            if (ImGui::SliderFloat("##hscroll", &off_x, 0.0f, max_off_x, "", ImGuiSliderFlags_NoInput)) {
                st.pan.x = -off_x;
                st.manual_view = true;
                clamp_pan();
            }
        }
        if (need_vbar) {
            float max_off_y = std::max(0.0f, content_h_px - avail.y);
            float off_y = std::clamp(-st.pan.y, 0.0f, max_off_y);
            ImGui::SetCursorScreenPos(ImVec2(origin.x + avail.x + 2.0f, origin.y));
            if (ImGui::VSliderFloat("##vscroll", ImVec2(sb, avail.y), &off_y, 0.0f, max_off_y, "", ImGuiSliderFlags_NoInput)) {
                st.pan.y = -off_y;
                st.manual_view = true;
                clamp_pan();
            }
        }

        ImGui::End();

        ImGui::SetNextWindowPos(ImVec2(vp->Pos.x + canvas_w, vp->Pos.y));
        ImGui::SetNextWindowSize(ImVec2(inspector_w, vp_size.y));
        ImGui::Begin("Inspector", nullptr, panel_flags);
        ImGui::Text("Mapper: %s", st.mapper_path.c_str());
        ImGui::Text("Host map: %s", st.host_map_path.c_str());
        {
            static char image_file_buf[512] = {0};
            static std::string image_file_sync;
            if (image_file_sync != st.image_file) {
                std::snprintf(image_file_buf, sizeof(image_file_buf), "%s", st.image_file.c_str());
                image_file_sync = st.image_file;
            }
            if (ImGui::InputText("Image file", image_file_buf, sizeof(image_file_buf))) {
                st.image_file = trim(image_file_buf);
                image_file_sync = st.image_file;
                st.image_path = path_join(dir_of(st.mapper_path), st.image_file);
                st.dirty_mapper = true;
            }
            ImGui::SameLine();
            if (ImGui::Button("Reload Image")) {
                if (image_tex) { SDL_DestroyTexture(image_tex); image_tex = nullptr; }
                if (image_surface) { SDL_FreeSurface(image_surface); image_surface = nullptr; }
                img_w = 0;
                img_h = 0;
                if (load_image_texture(ren, st.image_path, &image_tex, &image_surface, &img_w, &img_h)) {
                    st.auto_fit_pending = true;
                    status_msg = "Image reloaded";
                } else {
                    status_msg = "Image load failed: " + st.image_path;
                }
                status_until_ms = SDL_GetTicks() + 3000u;
            }
        }
        ImGui::Separator();
        ImGui::Checkbox("Edit mode (press host key to map selected target)", &st.edit_mode);
        if (st.edit_mode) {
            ImGui::TextColored(ImVec4(1.0f, 0.9f, 0.25f, 1.0f), "Edit Mode ON");
        }
        ImGui::Separator();
        ImGui::Text("Host Bindings");
        if (st.capture_new_binding_mode) {
            ImGui::TextColored(ImVec4(1.0f, 0.9f, 0.2f, 1.0f), "Waiting host key... (Esc to cancel)");
        }
        if (ImGui::Button(st.capture_new_binding_mode ? "Cancel Add Host Binding" : "Add Host Binding")) {
            st.capture_new_binding_mode = !st.capture_new_binding_mode;
        }
        ImGui::SameLine();
        bool can_remove_host_binding = st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size();
        ImGui::BeginDisabled(!can_remove_host_binding);
        if (ImGui::Button("Remove Selected Host Binding")) {
            push_undo(st);
            st.bindings.erase(st.bindings.begin() + st.selected_binding_global_index);
            st.selected_binding_global_index = -1;
            st.binding_edit_sync_index = -2;
            st.dirty_map = true;
            status_msg = "Host binding removed";
            status_until_ms = SDL_GetTicks() + 2500u;
        }
        ImGui::EndDisabled();
        ImGui::BeginChild("all_binds", ImVec2(0, 170), true);
        for (size_t bi = 0; bi < st.bindings.size(); ++bi) {
            const auto& b = st.bindings[bi];
            std::string det;
            if (b.has_press) {
                det = "r" + std::to_string(b.row) + "/b" + std::to_string(b.bit);
            } else if (b.has_ascii || b.has_ascii_shift || b.has_ascii_ctrl) {
                det = "ascii";
            } else if (!b.system_key_id.empty()) {
                bool vf = false;
                for (const auto& sk : st.system_keys) {
                    if (sk.id == b.system_key_id) { vf = sk.visual_feedback; break; }
                }
                det = std::string("system:") + b.system_key_id + (vf ? ",vf:on" : ",vf:off");
            } else if (!b.emulator_key_id.empty()) {
                det = "emulator:" + b.emulator_key_id;
            } else {
                det = "unmapped";
            }
            std::string target = !b.mapper_key_id.empty() ? b.mapper_key_id : (!b.system_key_id.empty() ? ("system:" + b.system_key_id) : (!b.emulator_key_id.empty() ? ("emu:" + b.emulator_key_id) : "-"));
            std::string lbl = b.host_token + " (sc=" + std::to_string(b.scancode) + ") -> " + target + " [" + det + "]";
            bool sel = ((int)bi == st.selected_binding_global_index);
            if (sel && st.scroll_to_selected_binding) {
                ImGui::SetScrollHereY(0.35f);
                st.scroll_to_selected_binding = false;
            }
            if (ImGui::Selectable(lbl.c_str(), sel)) {
                st.selected_binding_global_index = (int)bi;
                st.scroll_to_selected_binding = false;
                if (!b.mapper_key_id.empty()) {
                    st.edit_target_kind = 0;
                    st.edit_target_id = b.mapper_key_id;
                    st.selected_system_key_index = -1;
                    st.system_edit_sync_index = -2;
                    auto it = st.box_index_by_id.find(b.mapper_key_id);
                    if (it != st.box_index_by_id.end()) {
                        st.selected.clear();
                        st.selected.insert(it->second);
                        st.primary = (int)it->second;
                    }
                } else if (!b.system_key_id.empty()) {
                    st.edit_target_kind = 1;
                    st.edit_target_id = b.system_key_id;
                    st.selected_system_key_index = -1;
                    for (size_t si = 0; si < st.system_keys.size(); ++si) {
                        if (st.system_keys[si].id == b.system_key_id) {
                            st.selected_system_key_index = (int)si;
                            break;
                        }
                    }
                    st.system_edit_sync_index = -2;
                    auto it = st.box_index_by_id.find(b.system_key_id);
                    if (it != st.box_index_by_id.end()) {
                        st.selected.clear();
                        st.selected.insert(it->second);
                        st.primary = (int)it->second;
                    }
                } else if (!b.emulator_key_id.empty()) {
                    st.edit_target_kind = 2;
                    st.edit_target_id = b.emulator_key_id;
                    st.selected_system_key_index = -1;
                    st.system_edit_sync_index = -2;
                } else {
                    // Unmapped host key: clear selection so the "bindings for selected key" list is empty.
                    st.edit_target_kind = 0;
                    st.edit_target_id.clear();
                    st.selected_system_key_index = -1;
                    st.system_edit_sync_index = -2;
                    st.selected.clear();
                    st.primary = -1;
                }
            }
        }
        ImGui::EndChild();
        if (st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size()) {
            const char* kinds[] = {"mapper", "system", "emulator"};
            ImGui::Combo("Target kind", &st.edit_target_kind, kinds, 3);
            if (st.edit_target_kind == 2) {
                int emu_idx = 0;
                for (int i = 0; i < (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0])); ++i) {
                    if (st.edit_target_id == kEmuKeys[i]) { emu_idx = i; break; }
                }
                if (ImGui::Combo("Target id", &emu_idx, kEmuKeys, (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0])))) {
                    st.edit_target_id = kEmuKeys[emu_idx];
                }
            } else {
                char buf[256];
                std::snprintf(buf, sizeof(buf), "%s", st.edit_target_id.c_str());
                if (ImGui::InputText("Target id", buf, sizeof(buf))) {
                    st.edit_target_id = trim(buf);
                }
            }
            if (ImGui::Button("Apply Target To Selected Host")) {
                if (!st.edit_target_id.empty()) {
                    push_undo(st);
                    Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
                    b.mapper_key_id.clear();
                    b.system_key_id.clear();
                    b.emulator_key_id.clear();
                    if (st.edit_target_kind == 0) b.mapper_key_id = st.edit_target_id;
                    else if (st.edit_target_kind == 1) b.system_key_id = st.edit_target_id;
                    else b.emulator_key_id = st.edit_target_id;
                    st.dirty_map = true;
                }
            }
            bool can_map_to_primary =
                st.primary >= 0 && (size_t)st.primary < st.boxes.size();
            ImGui::SameLine();
            ImGui::BeginDisabled(!can_map_to_primary);
            if (ImGui::Button("Map Selected Host -> Primary Key")) {
                push_undo(st);
                Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
                b.mapper_key_id = st.boxes[(size_t)st.primary].id;
                b.system_key_id.clear();
                b.emulator_key_id.clear();
                st.edit_target_kind = 0;
                st.edit_target_id = b.mapper_key_id;
                st.dirty_map = true;
            }
            ImGui::EndDisabled();
        }
        if (st.binding_edit_sync_index != st.selected_binding_global_index) {
            st.binding_edit_sync_index = st.selected_binding_global_index;
            if (st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size()) {
                const Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
                st.binding_use_press = b.has_press;
                st.binding_row = b.row;
                st.binding_bit = b.bit;
                st.binding_has_ascii = b.has_ascii;
                st.binding_has_ascii_shift = b.has_ascii_shift;
                st.binding_has_ascii_ctrl = b.has_ascii_ctrl;
                st.binding_ascii = b.ascii;
                st.binding_ascii_shift = b.ascii_shift;
                st.binding_ascii_ctrl = b.ascii_ctrl;
            } else {
                st.binding_use_press = false;
                st.binding_row = 0;
                st.binding_bit = 0;
                st.binding_has_ascii = false;
                st.binding_has_ascii_shift = false;
                st.binding_has_ascii_ctrl = false;
                st.binding_ascii = 0;
                st.binding_ascii_shift = 0;
                st.binding_ascii_ctrl = 0;
            }
        }
        ImGui::Separator();
        ImGui::Text("Mapping Key Definition");
        bool has_selected_binding =
            st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size();
        ImGui::BeginDisabled(!has_selected_binding);
        ImGui::Checkbox("Use matrix press", &st.binding_use_press);
        ImGui::BeginDisabled(!st.binding_use_press);
        ImGui::InputInt("Matrix row", &st.binding_row);
        ImGui::InputInt("Matrix bit", &st.binding_bit);
        ImGui::EndDisabled();
        ImGui::Checkbox("ASCII", &st.binding_has_ascii);
        ImGui::BeginDisabled(!st.binding_has_ascii);
        ImGui::InputInt("ascii", &st.binding_ascii);
        ImGui::EndDisabled();
        ImGui::Checkbox("ASCII Shift", &st.binding_has_ascii_shift);
        ImGui::BeginDisabled(!st.binding_has_ascii_shift);
        ImGui::InputInt("ascii_shift", &st.binding_ascii_shift);
        ImGui::EndDisabled();
        ImGui::Checkbox("ASCII Ctrl", &st.binding_has_ascii_ctrl);
        ImGui::BeginDisabled(!st.binding_has_ascii_ctrl);
        ImGui::InputInt("ascii_ctrl", &st.binding_ascii_ctrl);
        ImGui::EndDisabled();
        if (ImGui::Button("Apply Mapping Definition")) {
            push_undo(st);
            Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
            b.has_press = st.binding_use_press;
            b.row = std::max(0, st.binding_row);
            b.bit = std::clamp(st.binding_bit, 0, 7);
            b.has_ascii = st.binding_has_ascii;
            b.has_ascii_shift = st.binding_has_ascii_shift;
            b.has_ascii_ctrl = st.binding_has_ascii_ctrl;
            b.ascii = std::clamp(st.binding_ascii, 0, 255);
            b.ascii_shift = std::clamp(st.binding_ascii_shift, 0, 255);
            b.ascii_ctrl = std::clamp(st.binding_ascii_ctrl, 0, 255);
            st.dirty_map = true;
            status_msg = "Mapping definition updated";
            status_until_ms = SDL_GetTicks() + 2500u;
        }
        ImGui::EndDisabled();
        ImGui::Separator();
        ImGui::Text("Last key: %s scancode=%d (%s) keycode=%d (%s) repeat=%d",
                    st.last_down ? "down" : "up",
                    st.last_scancode,
                    st.last_scancode >= 0 ? SDL_GetScancodeName((SDL_Scancode)st.last_scancode) : "-",
                    (int)st.last_keycode,
                    st.last_key_name.empty() ? "-" : st.last_key_name.c_str(),
                    st.last_repeat);
        if (!st.last_text_input.empty()) {
            ImGui::Text("Last text input: %s", st.last_text_input.c_str());
        }
        if (st.last_scancode >= 0) {
            std::string mapped = "-";
            for (const auto& b : st.bindings) {
                if (b.scancode != st.last_scancode) continue;
                if (!b.mapper_key_id.empty()) {
                    mapped = "mapper:" + b.mapper_key_id;
                    break;
                }
                if (!b.system_key_id.empty()) {
                    mapped = "system:" + b.system_key_id;
                    break;
                }
                if (!b.emulator_key_id.empty()) {
                    mapped = "emulator:" + b.emulator_key_id;
                    break;
                }
            }
            ImGui::Text("Mapped target: %s", mapped.c_str());
        }
        ImGui::Separator();

        ImGui::Text("Selected: %zu", st.selected.size());
        if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
            auto& pb = st.boxes[(size_t)st.primary];
            ImGui::Text("Primary: %s", pb.id.c_str());
            ImGui::SameLine();
            if (ImGui::Button("Rename Key ID")) {
                st.rename_popup_open = true;
                st.rename_text = pb.id;
                ImGui::OpenPopup("rename_key_popup");
            }

            int x = pb.x, y = pb.y, w = pb.w, h = pb.h;
            int r = pb.r, g = pb.g, b = pb.b;
            bool chx = ImGui::InputInt("X", &x);
            bool chy = ImGui::InputInt("Y", &y);
            bool chw = ImGui::InputInt("W", &w);
            bool chh = ImGui::InputInt("H", &h);
            bool chr = ImGui::InputInt("R", &r);
            bool chg = ImGui::InputInt("G", &g);
            bool chb = ImGui::InputInt("B", &b);

            auto apply_all = [&](auto fn) {
                for (size_t i : st.selected) fn(st.boxes[i]);
            };
            if (chx) { push_undo(st); apply_all([&](MapperBox& bx){ bx.x = std::max(0, x); }); st.dirty_mapper = true; }
            if (chy) { push_undo(st); apply_all([&](MapperBox& bx){ bx.y = std::max(0, y); }); st.dirty_mapper = true; }
            if (chw) { push_undo(st); apply_all([&](MapperBox& bx){ bx.w = std::max(1, w); }); st.dirty_mapper = true; }
            if (chh) { push_undo(st); apply_all([&](MapperBox& bx){ bx.h = std::max(1, h); }); st.dirty_mapper = true; }
            if (chr) { push_undo(st); apply_all([&](MapperBox& bx){ bx.has_overlay = true; bx.r = std::clamp(r, 0, 255); }); st.dirty_mapper = true; }
            if (chg) { push_undo(st); apply_all([&](MapperBox& bx){ bx.has_overlay = true; bx.g = std::clamp(g, 0, 255); }); st.dirty_mapper = true; }
            if (chb) { push_undo(st); apply_all([&](MapperBox& bx){ bx.has_overlay = true; bx.b = std::clamp(b, 0, 255); }); st.dirty_mapper = true; }
            if (ImGui::Button(st.pick_color_mode ? "Cancel Pick Color" : "Pick Color From Image")) {
                st.pick_color_mode = !st.pick_color_mode;
            }

            ImGui::Separator();
            ImGui::Text("Bindings for selected key");
            if (st.alias_capture_mode) {
                ImGui::TextColored(ImVec4(1.0f, 0.9f, 0.2f, 1.0f), "Waiting host key... (Esc to cancel)");
            }
            if (ImGui::Button(st.alias_capture_mode ? "Cancel Capture" : "Add Host Alias")) {
                if (st.alias_capture_mode) {
                    st.alias_capture_mode = false;
                    st.alias_capture_target_id.clear();
                } else {
                    int sel_kind = preferred_target_kind_for_id(st, pb.id);
                    st.alias_capture_mode = true;
                    st.alias_capture_target_kind = sel_kind;
                    st.alias_capture_target_id = pb.id;
                    status_msg = "Press host key to add alias for " + pb.id;
                    status_until_ms = SDL_GetTicks() + 3000u;
                }
            }
            ImGui::SameLine();
            bool can_remove_alias = false;
            if (st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size()) {
                const Binding& sb = st.bindings[(size_t)st.selected_binding_global_index];
                int sel_kind = preferred_target_kind_for_id(st, pb.id);
                if (sel_kind == 1) can_remove_alias = (sb.system_key_id == pb.id);
                else if (sel_kind == 2) can_remove_alias = (sb.emulator_key_id == pb.id);
                else can_remove_alias = (sb.mapper_key_id == pb.id);
            }
            ImGui::BeginDisabled(!can_remove_alias);
            if (ImGui::Button("Remove Selected Alias")) {
                if (can_remove_alias && st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size()) {
                    push_undo(st);
                    st.bindings.erase(st.bindings.begin() + st.selected_binding_global_index);
                    st.selected_binding_global_index = -1;
                    st.binding_edit_sync_index = -2;
                    st.dirty_map = true;
                    status_msg = "Alias removed";
                    status_until_ms = SDL_GetTicks() + 2500u;
                }
            }
            ImGui::EndDisabled();
            ImGui::BeginChild("binds", ImVec2(0, 180), true);
            int sel_kind = preferred_target_kind_for_id(st, pb.id);
            for (size_t bi_idx = 0; bi_idx < st.bindings.size(); ++bi_idx) {
                const Binding* bi = &st.bindings[bi_idx];
                if (sel_kind == 0) {
                    if (bi->mapper_key_id != pb.id) continue;
                } else if (sel_kind == 1) {
                    if (bi->system_key_id != pb.id) continue;
                } else {
                    if (bi->emulator_key_id != pb.id) continue;
                }
                std::string det;
                if (bi->has_press) {
                    det = "r" + std::to_string(bi->row) + "/b" + std::to_string(bi->bit);
                } else if (bi->has_ascii || bi->has_ascii_shift || bi->has_ascii_ctrl) {
                    det = "ascii";
                } else if (!bi->system_key_id.empty()) {
                    bool vf = false;
                    for (const auto& sk : st.system_keys) {
                        if (sk.id == bi->system_key_id) { vf = sk.visual_feedback; break; }
                    }
                    det = std::string("system:") + bi->system_key_id + (vf ? ",vf:on" : ",vf:off");
                } else if (!bi->emulator_key_id.empty()) {
                    det = "emulator:" + bi->emulator_key_id;
                } else {
                    det = "unmapped";
                }
                std::string dst;
                if (sel_kind == 1) dst = std::string("system:") + pb.id;
                else if (sel_kind == 2) dst = std::string("emulator:") + pb.id;
                else dst = pb.id;
                std::string lbl = bi->host_token + " (sc=" + std::to_string(bi->scancode) + ") -> " + dst + " [" + det + "]";
                bool selb = ((int)bi_idx == st.selected_binding_global_index);
                if (ImGui::Selectable(lbl.c_str(), selb)) {
                    st.selected_binding_global_index = (int)bi_idx;
                }
            }
            ImGui::EndChild();
        } else {
            ImGui::Text("Primary: -");
            int z = 0;
            bool bfalse = false;
            ImGui::BeginDisabled(true);
            ImGui::Button("Rename Key ID");
            ImGui::InputInt("X", &z);
            ImGui::InputInt("Y", &z);
            ImGui::InputInt("W", &z);
            ImGui::InputInt("H", &z);
            ImGui::InputInt("R", &z);
            ImGui::InputInt("G", &z);
            ImGui::InputInt("B", &z);
            ImGui::Button("Pick Color From Image");
            ImGui::Separator();
            ImGui::Text("Bindings for selected key");
            ImGui::Checkbox("Waiting host key...", &bfalse);
            ImGui::Button("Add Host Alias");
            ImGui::SameLine();
            ImGui::Button("Remove Selected Alias");
            ImGui::BeginChild("binds_disabled", ImVec2(0, 180), true);
            ImGui::EndChild();
            ImGui::EndDisabled();
        }

        if (ImGui::BeginPopupModal("rename_key_popup", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
            char rename_buf[256];
            std::snprintf(rename_buf, sizeof(rename_buf), "%s", st.rename_text.c_str());
            if (ImGui::InputText("New key id", rename_buf, sizeof(rename_buf))) {
                st.rename_text = trim(rename_buf);
            }
            if (ImGui::Button("Apply Rename")) {
                if (st.primary >= 0 && (size_t)st.primary < st.boxes.size()) {
                    std::string new_id = trim(st.rename_text);
                    std::string old_id = st.boxes[(size_t)st.primary].id;
                    bool ok = !new_id.empty();
                    if (ok && new_id != old_id) {
                        for (size_t i = 0; i < st.boxes.size(); ++i) {
                            if ((int)i == st.primary) continue;
                            if (st.boxes[i].id == new_id) { ok = false; break; }
                        }
                    }
                    if (!ok) {
                        status_msg = "Rename failed: invalid or duplicate id";
                        status_until_ms = SDL_GetTicks() + 3000u;
                    } else if (new_id != old_id) {
                        push_undo(st);
                        st.boxes[(size_t)st.primary].id = new_id;
                        for (auto& b : st.bindings) {
                            if (b.mapper_key_id == old_id) b.mapper_key_id = new_id;
                        }
                        if (st.edit_target_kind == 0 && st.edit_target_id == old_id) st.edit_target_id = new_id;
                        if (st.alias_capture_target_kind == 0 && st.alias_capture_target_id == old_id) st.alias_capture_target_id = new_id;
                        rebuild_box_index(st);
                        st.dirty_mapper = true;
                        st.dirty_map = true;
                        status_msg = "Renamed key: " + old_id + " -> " + new_id;
                        status_until_ms = SDL_GetTicks() + 3000u;
                    }
                }
                st.rename_popup_open = false;
                ImGui::CloseCurrentPopup();
            }
            ImGui::SameLine();
            if (ImGui::Button("Cancel")) {
                st.rename_popup_open = false;
                ImGui::CloseCurrentPopup();
            }
            ImGui::EndPopup();
        }

        ImGui::Separator();
        ImGui::Text("System Keys");
        ImGui::BeginChild("sys_keys", ImVec2(0, 120), true);
        for (size_t i = 0; i < st.system_keys.size(); ++i) {
            const auto& sk = st.system_keys[i];
            std::string lbl = sk.id + (sk.visual_feedback ? " [on]" : " [off]");
            bool sel = ((int)i == st.selected_system_key_index);
            if (ImGui::Selectable(lbl.c_str(), sel)) {
                st.selected_system_key_index = (int)i;
                auto it = st.box_index_by_id.find(sk.id);
                if (it != st.box_index_by_id.end()) {
                    st.selected.clear();
                    st.selected.insert(it->second);
                    st.primary = (int)it->second;
                }
                sync_binding_selection_for_target(st, preferred_target_kind_for_id(st, sk.id), sk.id);
            }
        }
        ImGui::EndChild();
        if (st.system_edit_sync_index != st.selected_system_key_index) {
            st.system_edit_sync_index = st.selected_system_key_index;
            if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
                const auto& sk = st.system_keys[(size_t)st.selected_system_key_index];
                st.system_edit_id = sk.id;
                st.system_edit_vf = sk.visual_feedback;
            } else {
                st.system_edit_id.clear();
                st.system_edit_vf = false;
            }
        }
        char sys_id_buf[256];
        std::snprintf(sys_id_buf, sizeof(sys_id_buf), "%s", st.system_edit_id.c_str());
        ImGui::InputText("System key id", sys_id_buf, sizeof(sys_id_buf));
        st.system_edit_id = trim(sys_id_buf);
        ImGui::Checkbox("Visual feedback", &st.system_edit_vf);
        ImGui::BeginDisabled(st.system_edit_id.empty());
        if (ImGui::Button("Add/Update System Key")) {
            std::string sid = st.system_edit_id;
            if (!sid.empty()) {
                push_undo(st);
                bool changed = false;
                if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
                    auto& sel = st.system_keys[(size_t)st.selected_system_key_index];
                    const std::string old_id = sel.id;
                    if (old_id != sid) {
                        bool dup = false;
                        for (size_t i = 0; i < st.system_keys.size(); ++i) {
                            if ((int)i == st.selected_system_key_index) continue;
                            if (st.system_keys[i].id == sid) { dup = true; break; }
                        }
                        if (dup) {
                            status_msg = "System key id already exists: " + sid;
                            status_until_ms = SDL_GetTicks() + 3000u;
                        } else {
                            sel.id = sid;
                            for (auto& b : st.bindings) {
                                if (b.system_key_id == old_id) b.system_key_id = sid;
                            }
                            auto it = st.box_index_by_id.find(old_id);
                            if (it != st.box_index_by_id.end()) {
                                st.boxes[it->second].id = sid;
                                rebuild_box_index(st);
                                st.dirty_mapper = true;
                            }
                            if (st.edit_target_kind == 1 && st.edit_target_id == old_id) st.edit_target_id = sid;
                            if (st.alias_capture_target_kind == 1 && st.alias_capture_target_id == old_id) st.alias_capture_target_id = sid;
                            changed = true;
                        }
                    }
                    if (sel.visual_feedback != st.system_edit_vf) {
                        sel.visual_feedback = st.system_edit_vf;
                        changed = true;
                    }
                } else {
                    bool found = false;
                    for (auto& sk : st.system_keys) {
                        if (sk.id == sid) {
                            sk.visual_feedback = st.system_edit_vf;
                            found = true;
                            changed = true;
                            break;
                        }
                    }
                    if (!found) {
                        st.system_keys.push_back(SystemKeyDef{sid, st.system_edit_vf});
                        st.selected_system_key_index = (int)st.system_keys.size() - 1;
                        st.system_edit_sync_index = -2;
                        changed = true;
                    }
                }
                if (changed) {
                    st.dirty_map = true;
                    status_msg = "System key updated";
                    status_until_ms = SDL_GetTicks() + 2500u;
                } else {
                    // Undo no-op
                    if (!st.undo_stack.empty()) st.undo_stack.pop_back();
                }
            }
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        bool can_remove_system = st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size();
        ImGui::BeginDisabled(!can_remove_system);
        if (ImGui::Button("Remove Selected System Key")) {
            if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
                push_undo(st);
                std::string sid = st.system_keys[(size_t)st.selected_system_key_index].id;
                st.system_keys.erase(st.system_keys.begin() + st.selected_system_key_index);
                st.selected_system_key_index = -1;
                st.system_edit_sync_index = -2;
                for (auto& b : st.bindings) {
                    if (b.system_key_id == sid) b.system_key_id.clear();
                }
                st.dirty_map = true;
            }
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        bool can_create_bbox = !st.system_edit_id.empty() && st.box_index_by_id.find(st.system_edit_id) == st.box_index_by_id.end();
        ImGui::BeginDisabled(!can_create_bbox);
        if (ImGui::Button("Create BBox")) {
            std::string sid = st.system_edit_id;
            if (!sid.empty() && st.box_index_by_id.find(sid) == st.box_index_by_id.end()) {
                push_undo(st);
                MapperBox nb;
                nb.id = sid;
                nb.x = (int)std::max(0.0f, (-st.pan.x / st.zoom) + 100.0f);
                nb.y = (int)std::max(0.0f, (-st.pan.y / st.zoom) + 100.0f);
                nb.w = 88;
                nb.h = 34;
                st.boxes.push_back(nb);
                rebuild_box_index(st);
                size_t bi = st.boxes.size() - 1;
                st.selected.clear();
                st.selected.insert(bi);
                st.primary = (int)bi;
                st.dirty_mapper = true;
            }
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        bool can_remove_bbox = !st.system_edit_id.empty() && st.box_index_by_id.find(st.system_edit_id) != st.box_index_by_id.end();
        ImGui::BeginDisabled(!can_remove_bbox);
        if (ImGui::Button("Remove BBox")) {
            std::string sid = st.system_edit_id;
            auto it = st.box_index_by_id.find(sid);
            if (!sid.empty() && it != st.box_index_by_id.end()) {
                push_undo(st);
                size_t idx = it->second;
                st.boxes.erase(st.boxes.begin() + (long)idx);
                rebuild_box_index(st);
                st.selected.clear();
                st.primary = -1;
                st.dirty_mapper = true;
            }
        }
        ImGui::EndDisabled();
        bool can_map_host_to_system =
            st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size() &&
            st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size();
        ImGui::BeginDisabled(!can_map_host_to_system);
        if (ImGui::Button("Map Selected Host -> Selected System Key")) {
            push_undo(st);
            Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
            b.mapper_key_id.clear();
            b.emulator_key_id.clear();
            b.system_key_id = st.system_keys[(size_t)st.selected_system_key_index].id;
            st.dirty_map = true;
        }
        ImGui::SameLine();
        if (ImGui::Button(st.alias_capture_mode ? "Cancel Sys Capture" : "Add System Alias")) {
            if (st.alias_capture_mode) {
                st.alias_capture_mode = false;
                st.alias_capture_target_id.clear();
            } else {
                st.alias_capture_mode = true;
                st.alias_capture_target_kind = 1;
                st.alias_capture_target_id = st.system_keys[(size_t)st.selected_system_key_index].id;
                status_msg = "Press host key to map to system key " + st.alias_capture_target_id;
                status_until_ms = SDL_GetTicks() + 3000u;
            }
        }
        ImGui::EndDisabled();
        if (st.selected_system_key_index >= 0 && (size_t)st.selected_system_key_index < st.system_keys.size()) {
            const std::string sid = st.system_keys[(size_t)st.selected_system_key_index].id;
            ImGui::Separator();
            ImGui::Text("Bindings for selected system key");
            ImGui::BeginChild("sys_binds", ImVec2(0, 110), true);
            for (size_t bi = 0; bi < st.bindings.size(); ++bi) {
                const auto& b = st.bindings[bi];
                if (b.system_key_id != sid) continue;
                std::string det;
                if (b.has_press) det = "r" + std::to_string(b.row) + "/b" + std::to_string(b.bit);
                else if (b.has_ascii || b.has_ascii_shift || b.has_ascii_ctrl) det = "ascii";
                else det = "unmapped";
                std::string lbl = b.host_token + " (sc=" + std::to_string(b.scancode) + ") -> system:" + sid + " [" + det + "]";
                bool selb = ((int)bi == st.selected_binding_global_index);
                if (ImGui::Selectable(lbl.c_str(), selb)) {
                    st.selected_binding_global_index = (int)bi;
                    st.edit_target_kind = 1;
                    st.edit_target_id = sid;
                    auto it = st.box_index_by_id.find(sid);
                    if (it != st.box_index_by_id.end()) {
                        st.selected.clear();
                        st.selected.insert(it->second);
                        st.primary = (int)it->second;
                    }
                }
            }
            ImGui::EndChild();
        }

        ImGui::Separator();
        ImGui::Text("Emulator Keys");
        const int emu_key_count = (int)(sizeof(kEmuKeys) / sizeof(kEmuKeys[0]));
        ImGui::BeginChild("emu_keys", ImVec2(0, 120), true);
        for (int i = 0; i < emu_key_count; ++i) {
            const std::string eid = kEmuKeys[i];
            bool sel = (i == st.selected_emulator_key_index);
            if (ImGui::Selectable(eid.c_str(), sel)) {
                st.selected_emulator_key_index = i;
                auto it = st.box_index_by_id.find(eid);
                if (it != st.box_index_by_id.end()) {
                    st.selected.clear();
                    st.selected.insert(it->second);
                    st.primary = (int)it->second;
                }
                sync_binding_selection_for_target(st, 2, eid);
            }
        }
        ImGui::EndChild();
        const std::string selected_emu_id =
            (st.selected_emulator_key_index >= 0 && st.selected_emulator_key_index < emu_key_count)
                ? std::string(kEmuKeys[st.selected_emulator_key_index])
                : std::string();
        bool emu_has_bbox = !selected_emu_id.empty() && (st.box_index_by_id.find(selected_emu_id) != st.box_index_by_id.end());
        bool can_create_emu_bbox = !selected_emu_id.empty() && !emu_has_bbox;
        ImGui::BeginDisabled(!can_create_emu_bbox);
        if (ImGui::Button("Create Emulator BBox")) {
            if (!selected_emu_id.empty() && st.box_index_by_id.find(selected_emu_id) == st.box_index_by_id.end()) {
                push_undo(st);
                MapperBox nb;
                nb.id = selected_emu_id;
                nb.x = (int)std::max(0.0f, (-st.pan.x / st.zoom) + 100.0f);
                nb.y = (int)std::max(0.0f, (-st.pan.y / st.zoom) + 100.0f);
                nb.w = 88;
                nb.h = 34;
                st.boxes.push_back(nb);
                rebuild_box_index(st);
                size_t bi = st.boxes.size() - 1;
                st.selected.clear();
                st.selected.insert(bi);
                st.primary = (int)bi;
                st.dirty_mapper = true;
            }
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(!emu_has_bbox);
        if (ImGui::Button("Remove Emulator BBox")) {
            if (!selected_emu_id.empty()) {
                auto it = st.box_index_by_id.find(selected_emu_id);
                if (it != st.box_index_by_id.end()) {
                    push_undo(st);
                    size_t idx = it->second;
                    st.boxes.erase(st.boxes.begin() + (long)idx);
                    rebuild_box_index(st);
                    st.selected.clear();
                    st.primary = -1;
                    st.dirty_mapper = true;
                }
            }
        }
        ImGui::EndDisabled();

        bool can_map_host_to_emu =
            st.selected_binding_global_index >= 0 && (size_t)st.selected_binding_global_index < st.bindings.size() &&
            !selected_emu_id.empty();
        ImGui::BeginDisabled(!can_map_host_to_emu);
        if (ImGui::Button("Map Selected Host -> Selected Emulator Key")) {
            push_undo(st);
            Binding& b = st.bindings[(size_t)st.selected_binding_global_index];
            b.mapper_key_id.clear();
            b.system_key_id.clear();
            b.emulator_key_id = selected_emu_id;
            st.dirty_map = true;
        }
        ImGui::EndDisabled();
        if (st.alias_capture_mode && st.alias_capture_target_kind == 2) {
            ImGui::TextColored(ImVec4(1.0f, 0.9f, 0.2f, 1.0f), "Waiting host key... (Esc to cancel)");
        }
        ImGui::BeginDisabled(selected_emu_id.empty());
        float btn_w = ImGui::GetContentRegionAvail().x;
        if (btn_w < 10.0f) btn_w = 10.0f;
        if (ImGui::Button(st.alias_capture_mode ? "Cancel Emu Capture" : "Add Emulator Alias", ImVec2(btn_w, 0.0f))) {
            if (st.alias_capture_mode) {
                st.alias_capture_mode = false;
                st.alias_capture_target_id.clear();
            } else {
                st.alias_capture_mode = true;
                st.alias_capture_target_kind = 2;
                st.alias_capture_target_id = selected_emu_id;
                status_msg = "Press host key to map to emulator key " + selected_emu_id;
                status_until_ms = SDL_GetTicks() + 3000u;
            }
        }
        ImGui::EndDisabled();

        if (!selected_emu_id.empty()) {
            ImGui::Separator();
            ImGui::Text("Bindings for selected emulator key");
            ImGui::BeginChild("emu_binds", ImVec2(0, 110), true);
            for (size_t bi = 0; bi < st.bindings.size(); ++bi) {
                const auto& b = st.bindings[bi];
                if (b.emulator_key_id != selected_emu_id) continue;
                std::string det;
                if (b.has_press) det = "r" + std::to_string(b.row) + "/b" + std::to_string(b.bit);
                else if (b.has_ascii || b.has_ascii_shift || b.has_ascii_ctrl) det = "ascii";
                else det = "unmapped";
                std::string lbl = b.host_token + " (sc=" + std::to_string(b.scancode) + ") -> emulator:" + selected_emu_id + " [" + det + "]";
                bool selb = ((int)bi == st.selected_binding_global_index);
                if (ImGui::Selectable(lbl.c_str(), selb)) {
                    st.selected_binding_global_index = (int)bi;
                    st.edit_target_kind = 2;
                    st.edit_target_id = selected_emu_id;
                    auto it = st.box_index_by_id.find(selected_emu_id);
                    if (it != st.box_index_by_id.end()) {
                        st.selected.clear();
                        st.selected.insert(it->second);
                        st.primary = (int)it->second;
                    }
                }
            }
            ImGui::EndChild();
        }

        ImGui::TextDisabled("Shortcuts: Ctrl+Z/Y undo/redo, Ctrl+N new, Ctrl+D duplicate, Ctrl+Q quit, Del remove, wheel zoom, middle-drag pan");
        if (ImGui::Button("Save Mapper")) {
            do_save_mapper();
        }
        ImGui::SameLine();
        if (ImGui::Button("Save Host Map")) {
            do_save_host_map();
        }
        ImGui::SameLine();
        if (ImGui::Button("Reload")) {
            std::unordered_set<std::string> prev_ids;
            for (size_t i : st.selected) {
                if (i < st.boxes.size()) prev_ids.insert(st.boxes[i].id);
            }
            load_mapper(st.mapper_path, st);
            load_host_map(st.host_map_path, st);
            if (image_tex) { SDL_DestroyTexture(image_tex); image_tex = nullptr; }
            if (image_surface) { SDL_FreeSurface(image_surface); image_surface = nullptr; }
            img_w = 0;
            img_h = 0;
            (void)load_image_texture(ren, st.image_path, &image_tex, &image_surface, &img_w, &img_h);
            st.selected.clear();
            st.primary = -1;
            for (size_t i = 0; i < st.boxes.size(); ++i) {
                if (prev_ids.count(st.boxes[i].id)) {
                    st.selected.insert(i);
                    st.primary = (int)i;
                }
            }
            st.dirty_mapper = false;
            st.dirty_map = false;
            status_msg = "Reloaded mapper + host map";
            status_until_ms = SDL_GetTicks() + 3000u;
        }
        if (!st.validation_errors.empty()) {
            ImGui::TextColored(
                ImVec4(1.0f, 0.75f, 0.25f, 1.0f),
                "Validation issues: %d (first: %s)",
                (int)st.validation_errors.size(),
                st.validation_errors.front().c_str()
            );
        }
        if (!status_msg.empty() && SDL_GetTicks() < status_until_ms) {
            ImGui::TextUnformatted(status_msg.c_str());
        }
        if (ImGui::CollapsingHeader("Verification Checklist", ImGuiTreeNodeFlags_DefaultOpen)) {
            ImGui::BulletText("1) Open emulator + mapper for same host map.");
            ImGui::BulletText("2) Press key and compare title scancode on both sides.");
            ImGui::BulletText("3) Confirm highlighted bbox matches mapped target.");
            ImGui::BulletText("4) Verify Shift/Ctrl combos and punctuation keys.");
            ImGui::BulletText("5) Save Host Map; ensure no validation issues.");
        }
        ImGui::End();

        if (st.validation_popup_open) {
            ImGui::OpenPopup("Invalid Links##host_map_validation");
            st.validation_popup_open = false;
        }
        if (ImGui::BeginPopupModal("Invalid Links##host_map_validation", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
            ImGui::TextUnformatted(st.validation_popup_title.empty() ? "Invalid links" : st.validation_popup_title.c_str());
            ImGui::Separator();
            ImGui::BeginChild("validation_list", ImVec2(760, 280), true);
            for (const auto& m : st.validation_errors) {
                ImGui::TextWrapped("%s", m.c_str());
            }
            ImGui::EndChild();
            if (ImGui::Button("OK")) {
                ImGui::CloseCurrentPopup();
            }
            ImGui::EndPopup();
        }

        if (st.quit_requested) {
            ImGui::OpenPopup("Exit PASM Keymapper##quit_flow");
            st.quit_requested = false;
        }
        if (ImGui::BeginPopupModal("Exit PASM Keymapper##quit_flow", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
            if (st.quit_stage == 1) {
                ImGui::TextUnformatted("Unsaved Mapper Changes");
                ImGui::Separator();
                ImGui::TextUnformatted("The keymapper file has unsaved edits.");
                ImGui::TextUnformatted("Save mapper before quitting?");
                bool key_save = ImGui::IsKeyPressed(ImGuiKey_S, false) && (ImGui::GetIO().KeyCtrl);
                bool key_skip = ImGui::IsKeyPressed(ImGuiKey_N, false);
                bool key_cancel = ImGui::IsKeyPressed(ImGuiKey_Escape, false);
                if (ImGui::Button("Save Mapper")) {
                    std::string err;
                    if (save_mapper_boxes(st, err)) {
                        st.dirty_mapper = false;
                        st.quit_stage = st.dirty_map ? 2 : 3;
                    } else {
                        status_msg = "Save failed: " + err;
                        status_until_ms = SDL_GetTicks() + 4000u;
                    }
                }
                ImGui::SameLine();
                if (ImGui::Button("Skip Mapper Save")) {
                    st.quit_stage = st.dirty_map ? 2 : 3;
                }
                ImGui::SameLine();
                if (ImGui::Button("Cancel")) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
                if (key_save) {
                    std::string err;
                    if (save_mapper_boxes(st, err)) {
                        st.dirty_mapper = false;
                        st.quit_stage = st.dirty_map ? 2 : 3;
                    } else {
                        status_msg = "Save failed: " + err;
                        status_until_ms = SDL_GetTicks() + 4000u;
                    }
                } else if (key_skip) {
                    st.quit_stage = st.dirty_map ? 2 : 3;
                } else if (key_cancel) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
            } else if (st.quit_stage == 2) {
                ImGui::TextUnformatted("Unsaved Host Map Changes");
                ImGui::Separator();
                ImGui::TextUnformatted("The host keyboard map has unsaved edits.");
                ImGui::TextUnformatted("Save host map before quitting?");
                bool key_save = ImGui::IsKeyPressed(ImGuiKey_S, false) && (ImGui::GetIO().KeyCtrl);
                bool key_skip = ImGui::IsKeyPressed(ImGuiKey_N, false);
                bool key_cancel = ImGui::IsKeyPressed(ImGuiKey_Escape, false);
                if (ImGui::Button("Save Host Map")) {
                    auto val_errs = validate_host_map_links(st);
                    std::string err;
                    if (!val_errs.empty()) {
                        st.validation_errors = std::move(val_errs);
                        st.validation_popup_title = "Invalid Host Map Links";
                        st.validation_popup_open = true;
                        status_msg = "Host map validation failed";
                        status_until_ms = SDL_GetTicks() + 4000u;
                    } else if (save_host_map(st, err)) {
                        st.dirty_map = false;
                        st.validation_errors.clear();
                        st.quit_stage = 3;
                    } else {
                        status_msg = "Host map save failed: " + err;
                        status_until_ms = SDL_GetTicks() + 4000u;
                    }
                }
                ImGui::SameLine();
                if (ImGui::Button("Skip Host Save")) {
                    st.quit_stage = 3;
                }
                ImGui::SameLine();
                if (ImGui::Button("Cancel")) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
                if (key_save) {
                    auto val_errs = validate_host_map_links(st);
                    std::string err;
                    if (!val_errs.empty()) {
                        st.validation_errors = std::move(val_errs);
                        st.validation_popup_title = "Invalid Host Map Links";
                        st.validation_popup_open = true;
                        status_msg = "Host map validation failed";
                        status_until_ms = SDL_GetTicks() + 4000u;
                    } else if (save_host_map(st, err)) {
                        st.dirty_map = false;
                        st.validation_errors.clear();
                        st.quit_stage = 3;
                    } else {
                        status_msg = "Host map save failed: " + err;
                        status_until_ms = SDL_GetTicks() + 4000u;
                    }
                } else if (key_skip) {
                    st.quit_stage = 3;
                } else if (key_cancel) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
            } else {
                ImGui::TextUnformatted("Confirm Exit");
                ImGui::Separator();
                ImGui::TextUnformatted("Are you sure you want to quit PASM Keymapper?");
                bool key_quit = ImGui::IsKeyPressed(ImGuiKey_Enter, false) || ImGui::IsKeyPressed(ImGuiKey_Q, false);
                bool key_cancel = ImGui::IsKeyPressed(ImGuiKey_Escape, false);
                if (ImGui::Button("Quit")) {
                    running = false;
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
                ImGui::SameLine();
                if (ImGui::Button("Cancel")) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
                if (key_quit) {
                    running = false;
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                } else if (key_cancel) {
                    st.quit_stage = 0;
                    ImGui::CloseCurrentPopup();
                }
            }
            ImGui::EndPopup();
        }

        std::string title = "PASM Keymapper";
        if (!st.system_name.empty()) title += " - " + st.system_name;
        if (st.dirty_mapper || st.dirty_map) title += " *";
        if (st.edit_mode) title += " | EDIT";
        if (st.alias_capture_mode) title += " | CAPTURE";
        if (st.capture_new_binding_mode) title += " | ADD-BIND";
        SDL_SetWindowTitle(win, title.c_str());

        ImGui::Render();
        SDL_SetRenderDrawColor(ren, 12, 14, 18, 255);
        SDL_RenderClear(ren);
        ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData(), ren);
        SDL_RenderPresent(ren);
    }

    if (image_tex) SDL_DestroyTexture(image_tex);
    if (image_surface) SDL_FreeSurface(image_surface);
    if (cursor_arrow) SDL_FreeCursor(cursor_arrow);
    if (cursor_cross) SDL_FreeCursor(cursor_cross);
    if (cursor_size_nwse) SDL_FreeCursor(cursor_size_nwse);
    if (cursor_size_all) SDL_FreeCursor(cursor_size_all);
    ImGui_ImplSDLRenderer2_Shutdown();
    ImGui_ImplSDL2_Shutdown();
    ImGui::DestroyContext();
    if (ren) SDL_DestroyRenderer(ren);
    if (win) SDL_DestroyWindow(win);
    IMG_Quit();
    SDL_Quit();
    return 0;
}
