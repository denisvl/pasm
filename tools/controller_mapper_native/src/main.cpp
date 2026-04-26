#include <SDL.h>
#include <SDL_image.h>

#include "backends/imgui_impl_sdl2.h"
#include "backends/imgui_impl_sdlrenderer2.h"
#include "imgui.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <optional>
#include <sstream>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

static std::string trim(std::string s) {
  size_t a = 0;
  while (a < s.size() && std::isspace((unsigned char)s[a]))
    a++;
  size_t b = s.size();
  while (b > a && std::isspace((unsigned char)s[b - 1]))
    b--;
  return s.substr(a, b - a);
}

static bool starts_with(const std::string &s, const char *pfx) {
  const size_t n = std::strlen(pfx);
  return s.size() >= n && std::memcmp(s.data(), pfx, n) == 0;
}

static std::string unquote(std::string s) {
  s = trim(s);
  if (s.size() >= 2 && ((s.front() == '"' && s.back() == '"') ||
                        (s.front() == '\'' && s.back() == '\''))) {
    return s.substr(1, s.size() - 2);
  }
  return s;
}

static std::optional<int> parse_int(const std::string &s) {
  char *end = nullptr;
  long v = std::strtol(s.c_str(), &end, 0);
  if (end == s.c_str())
    return std::nullopt;
  if (trim(end).size() != 0)
    return std::nullopt;
  return (int)v;
}

static std::optional<float> parse_float(const std::string &s) {
  char *end = nullptr;
  float v = std::strtof(s.c_str(), &end);
  if (end == s.c_str())
    return std::nullopt;
  if (trim(end).size() != 0)
    return std::nullopt;
  return v;
}

static std::string dir_of(const std::string &path) {
  size_t p = path.find_last_of("/\\");
  if (p == std::string::npos)
    return ".";
  return path.substr(0, p);
}

static std::string path_join(const std::string &a, const std::string &b) {
  if (a.empty())
    return b;
  if (b.empty())
    return a;
  if (a.back() == '/' || a.back() == '\\')
    return a + b;
  return a + "/" + b;
}

// Host scancode token parsing (reuse keymapper_native approach).
static int parse_scancode_token(const std::string &token) {
  std::string tok = unquote(trim(token));
  if (tok.empty())
    return -1;

  // Numeric tokens are SDL scancode numbers.
  bool numeric = true;
  for (char c : tok) {
    if (!(c >= '0' && c <= '9')) {
      numeric = false;
      break;
    }
  }
  if (numeric)
    return std::atoi(tok.c_str());

  std::string up = tok;
  for (char &c : up)
    c = (char)std::toupper((unsigned char)c);

  static const std::unordered_map<std::string, SDL_Scancode> kMap = {
      {"ESCAPE", SDL_SCANCODE_ESCAPE},
      {"TAB", SDL_SCANCODE_TAB},
      {"BACKSPACE", SDL_SCANCODE_BACKSPACE},
      {"RETURN", SDL_SCANCODE_RETURN},
      {"KP_ENTER", SDL_SCANCODE_KP_ENTER},
      {"SPACE", SDL_SCANCODE_SPACE},
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
  if (it != kMap.end())
    return (int)it->second;

  for (char &c : tok)
    if (c == '_')
      c = ' ';
  SDL_Scancode sc = SDL_GetScancodeFromName(tok.c_str());
  return sc == SDL_SCANCODE_UNKNOWN ? -1 : (int)sc;
}

static std::string host_token_for_scancode(int sc) {
  if (sc < 0)
    return "";
  return std::to_string(sc);
}

static int clamp_int(int v, int lo, int hi) {
  return (v < lo) ? lo : (v > hi) ? hi : v;
}

enum class ControlKind { Button, Axis, Hat, Switch };
static const char *control_kind_name(ControlKind k) {
  switch (k) {
  case ControlKind::Button:
    return "button";
  case ControlKind::Axis:
    return "axis";
  case ControlKind::Hat:
    return "hat";
  case ControlKind::Switch:
    return "switch";
  }
  return "button";
}

static ControlKind parse_control_kind(const std::string &s) {
  const std::string v = trim(unquote(s));
  if (v == "axis")
    return ControlKind::Axis;
  if (v == "hat")
    return ControlKind::Hat;
  if (v == "switch")
    return ControlKind::Switch;
  return ControlKind::Button;
}

struct MapperControl {
  std::string id;
  ControlKind kind = ControlKind::Button;
  int port = 1;
  bool has_bbox = false;
  int x = 0, y = 0, w = 1, h = 1;
  bool has_overlay = false;
  int r = 80, g = 160, b = 255;
};

enum class DeviceKind { Any, GameController, Joystick };
static const char *device_kind_name(DeviceKind k) {
  switch (k) {
  case DeviceKind::Any:
    return "any";
  case DeviceKind::GameController:
    return "gamecontroller";
  case DeviceKind::Joystick:
    return "joystick";
  }
  return "any";
}

struct DeviceSelector {
  DeviceKind kind = DeviceKind::Any;
  int index = -1;
  std::string guid;
};

enum class HostSourceKind {
  HostScancode,
  GamepadButton,
  GamepadAxis,
  JoystickButton,
  JoystickAxis,
  JoystickHat,
};

struct ControllerBinding {
  std::string target_control_id;
  HostSourceKind source_kind = HostSourceKind::HostScancode;
  DeviceSelector device;

  // Keyboard
  int scancode = -1;
  std::string host_token;

  // Gamepad/Joystick
  std::string
      control; // for gamepad: button/axis name; for joystick hat: hat_dir
  int button = -1;
  int axis = -1;
  int hat = -1;
  std::string hat_dir;
  char direction = 0; // '+' or '-'

  // transforms
  float deadzone = 0.15f;
  float scale = 1.0f;
  bool invert = false;
  float threshold = 0.5f;
};

struct PortDef {
  int port = 1;
  bool connected = true;
  DeviceSelector host_device;
};

struct Snapshot {
  int max_ports = 0;
  bool max_ports_explicit = false;
  std::vector<MapperControl> controls;
  std::vector<PortDef> ports;
  std::vector<ControllerBinding> bindings;
  std::unordered_set<size_t> selected;
  int primary = -1;
  int active_port = 1;
};

struct AppState {
  std::string mapper_path;
  std::string host_map_path;
  std::string system_name;

  int max_ports = 0;
  bool max_ports_explicit = false;

  std::string image_file;
  std::string image_path;

  bool focus_required = false;
  bool focus_required_explicit = false;

  std::vector<MapperControl> controls;
  std::unordered_map<std::string, size_t> control_index_by_id;

  std::vector<PortDef> ports;
  std::vector<ControllerBinding> bindings;

  // Selection
  std::unordered_set<size_t> selected;
  int primary = -1;
  bool dragging = false;
  bool resizing = false;
  ImVec2 drag_start{0, 0};
  std::unordered_map<size_t, ImVec2> drag_origin;
  int resize_start_w = 1;
  int resize_start_h = 1;
  // Rubber-band selection (box select in image coords).
  bool box_selecting = false;
  bool box_toggle = false; // when true, toggles membership of items in the box;
                           // otherwise replaces selection
  ImVec2 box_start{0, 0};
  ImVec2 box_end{0, 0};

  // View
  float zoom = 1.0f;
  bool auto_fit_pending = true;
  bool manual_view = false;
  bool request_fit = true;
  bool request_center = true;

  // UI state
  int selected_binding_index = -1;
  int active_port = 1;

  std::vector<Snapshot> undo_stack;
  std::vector<Snapshot> redo_stack;

  bool dirty_mapper = false;
  bool dirty_map = false;

  bool quit_requested = false;
  int quit_stage = 0; // 0=inactive, 1=mapper, 2=host map, 3=confirm

  // Capture
  bool capture_host_key = false;
  bool capture_gamepad = false;
  bool capture_joystick = false;
  std::string capture_target_id;
  std::string capture_status;
};

static void rebuild_control_index(AppState &st);
static void ensure_ports(AppState &st);

static Snapshot make_snapshot(const AppState &st) {
  Snapshot s;
  s.max_ports = st.max_ports;
  s.max_ports_explicit = st.max_ports_explicit;
  s.controls = st.controls;
  s.ports = st.ports;
  s.bindings = st.bindings;
  s.selected = st.selected;
  s.primary = st.primary;
  s.active_port = st.active_port;
  return s;
}

static void restore_snapshot(AppState &st, Snapshot &&s) {
  st.max_ports = s.max_ports;
  st.max_ports_explicit = s.max_ports_explicit;
  st.controls = std::move(s.controls);
  st.ports = std::move(s.ports);
  st.bindings = std::move(s.bindings);
  st.selected = std::move(s.selected);
  st.primary = s.primary;
  st.active_port = s.active_port;
  // Clear transient interaction state.
  st.dragging = false;
  st.resizing = false;
  st.drag_origin.clear();
  st.box_selecting = false;
  st.box_toggle = false;
  rebuild_control_index(st);
  ensure_ports(st);
}

static void push_undo(AppState &st) {
  st.undo_stack.push_back(make_snapshot(st));
  if (st.undo_stack.size() > 128) {
    st.undo_stack.erase(st.undo_stack.begin());
  }
  st.redo_stack.clear();
}

static bool do_undo(AppState &st) {
  if (st.undo_stack.empty())
    return false;
  st.redo_stack.push_back(make_snapshot(st));
  Snapshot s = std::move(st.undo_stack.back());
  st.undo_stack.pop_back();
  restore_snapshot(st, std::move(s));
  st.dirty_mapper = true;
  st.dirty_map = true;
  return true;
}

static bool do_redo(AppState &st) {
  if (st.redo_stack.empty())
    return false;
  st.undo_stack.push_back(make_snapshot(st));
  Snapshot s = std::move(st.redo_stack.back());
  st.redo_stack.pop_back();
  restore_snapshot(st, std::move(s));
  st.dirty_mapper = true;
  st.dirty_map = true;
  return true;
}

static void rebuild_control_index(AppState &st) {
  st.control_index_by_id.clear();
  for (size_t i = 0; i < st.controls.size(); ++i) {
    st.control_index_by_id[st.controls[i].id] = i;
  }
}

static int max_port_from_controls(const AppState &st) {
  int mx = 1;
  for (const auto &c : st.controls)
    mx = std::max(mx, c.port);
  return mx;
}

static int effective_max_ports(const AppState &st) {
  int mx = max_port_from_controls(st);
  if (st.max_ports_explicit)
    mx = std::max(mx, std::max(1, st.max_ports));
  return std::max(1, mx);
}

static void ensure_ports(AppState &st) {
  int mx = effective_max_ports(st);
  std::unordered_map<int, size_t> idx;
  for (size_t i = 0; i < st.ports.size(); ++i)
    idx[st.ports[i].port] = i;
  for (int p = 1; p <= mx; ++p) {
    if (idx.find(p) == idx.end()) {
      PortDef d;
      d.port = p;
      d.connected = true;
      st.ports.push_back(d);
    }
  }
  std::sort(st.ports.begin(), st.ports.end(),
            [](const PortDef &a, const PortDef &b) { return a.port < b.port; });
  // Drop any ports beyond the mapper's declared maximum.
  st.ports.erase(std::remove_if(st.ports.begin(), st.ports.end(),
                                [&](const PortDef &d) {
                                  return d.port < 1 || d.port > mx;
                                }),
                 st.ports.end());
  if (st.active_port < 1)
    st.active_port = 1;
  if (st.active_port > mx)
    st.active_port = mx;
}

static bool load_controller_mapper(const std::string &path, AppState &st) {
  std::ifstream in(path);
  if (!in.good())
    return false;

  st.controls.clear();
  st.control_index_by_id.clear();
  st.image_file.clear();
  st.system_name.clear();
  st.max_ports = 0;
  st.max_ports_explicit = false;

  MapperControl cur;
  bool have_cur = false;
  bool in_bbox = false;
  bool in_overlay = false;
  int overlay_idx = 0;

  auto flush = [&]() {
    if (!have_cur || cur.id.empty())
      return;
    cur.w = std::max(1, cur.w);
    cur.h = std::max(1, cur.h);
    st.controls.push_back(cur);
    have_cur = false;
    in_bbox = false;
    in_overlay = false;
    overlay_idx = 0;
  };

  std::string line;
  while (std::getline(in, line)) {
    std::string s = trim(line);
    if (s.empty() || s[0] == '#')
      continue;

    if (starts_with(s, "system_name:") && st.system_name.empty()) {
      st.system_name = unquote(trim(s.substr(std::strlen("system_name:"))));
      continue;
    }
    if (starts_with(s, "max_ports:") && !st.max_ports_explicit) {
      if (auto v = parse_int(trim(s.substr(std::strlen("max_ports:"))));
          v.has_value()) {
        st.max_ports = std::max(1, *v);
        st.max_ports_explicit = true;
      }
      continue;
    }
    if (starts_with(s, "file:") && st.image_file.empty()) {
      st.image_file = unquote(trim(s.substr(5)));
      continue;
    }

    if (starts_with(s, "- id:") || starts_with(s, "id:")) {
      flush();
      have_cur = true;
      cur = MapperControl{};
      auto pos = s.find(':');
      if (pos != std::string::npos)
        cur.id = unquote(trim(s.substr(pos + 1)));
      continue;
    }
    if (!have_cur)
      continue;

    if (starts_with(s, "port:")) {
      if (auto v = parse_int(trim(s.substr(5))); v.has_value())
        cur.port = std::max(1, *v);
      continue;
    }
    if (starts_with(s, "kind:")) {
      cur.kind = parse_control_kind(trim(s.substr(5)));
      continue;
    }
    if (starts_with(s, "bbox:")) {
      in_bbox = true;
      in_overlay = false;
      cur.has_bbox = true;
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
        if (!v.has_value())
          continue;
        if (k == "x")
          cur.x = std::max(0, *v);
        else if (k == "y")
          cur.y = std::max(0, *v);
        else if (k == "width")
          cur.w = std::max(1, *v);
        else if (k == "height")
          cur.h = std::max(1, *v);
      }
      continue;
    }
    if (in_overlay && starts_with(s, "-")) {
      auto v = parse_int(trim(s.substr(1)));
      if (!v.has_value())
        continue;
      if (overlay_idx == 0)
        cur.r = std::clamp(*v, 0, 255);
      if (overlay_idx == 1)
        cur.g = std::clamp(*v, 0, 255);
      if (overlay_idx == 2)
        cur.b = std::clamp(*v, 0, 255);
      overlay_idx++;
      continue;
    }
  }
  flush();

  rebuild_control_index(st);
  ensure_ports(st);

  std::string dir = dir_of(path);
  st.image_path = path_join(dir, st.image_file);
  return true;
}

static bool load_host_controller_map(const std::string &path, AppState &st) {
  std::ifstream in(path);
  if (!in.good())
    return false;

  st.bindings.clear();
  st.focus_required = false;
  st.focus_required_explicit = false;

  // Keep existing ports from mapper; override if file specifies.
  std::unordered_map<int, size_t> port_idx;
  for (size_t i = 0; i < st.ports.size(); ++i)
    port_idx[st.ports[i].port] = i;

  enum class Section { None, Ports, Bindings };
  Section sec = Section::None;

  PortDef port_cur;
  bool in_port_obj = false;

  ControllerBinding cur;
  bool in_binding = false;

  enum class Nested { None, HostGamepad, HostJoystick, HostDevice };
  Nested nested = Nested::None;

  auto flush_port = [&]() {
    if (!in_port_obj)
      return;
    if (port_cur.port >= 1) {
      auto it = port_idx.find(port_cur.port);
      if (it != port_idx.end()) {
        st.ports[it->second].connected = port_cur.connected;
        st.ports[it->second].host_device = port_cur.host_device;
      } else {
        st.ports.push_back(port_cur);
        port_idx[port_cur.port] = st.ports.size() - 1;
      }
    }
    port_cur = PortDef{};
    in_port_obj = false;
  };

  auto flush_binding = [&]() {
    if (!in_binding)
      return;
    if (!cur.target_control_id.empty())
      st.bindings.push_back(cur);
    cur = ControllerBinding{};
    in_binding = false;
    nested = Nested::None;
  };

  std::string line;
  while (std::getline(in, line)) {
    std::string raw = line;
    std::string s = trim(raw);
    if (s.empty() || s[0] == '#')
      continue;

    if (s == "controller_map:" || s == "controller:") {
      continue;
    }
    if (starts_with(s, "focus_required:")) {
      std::string v = trim(s.substr(std::strlen("focus_required:")));
      st.focus_required_explicit = true;
      st.focus_required = (v == "true" || v == "True" || v == "1");
      continue;
    }
    if (starts_with(s, "ports:")) {
      flush_binding();
      flush_port();
      sec = Section::Ports;
      continue;
    }
    if (starts_with(s, "bindings:")) {
      flush_port();
      sec = Section::Bindings;
      continue;
    }

    if (sec == Section::Ports) {
      if (starts_with(s, "-")) {
        flush_port();
        in_port_obj = true;
        port_cur = PortDef{};
        std::string rest = trim(s.substr(1));
        if (starts_with(rest, "port:")) {
          if (auto v = parse_int(trim(rest.substr(5))); v.has_value())
            port_cur.port = std::max(1, *v);
        }
        continue;
      }
      if (!in_port_obj)
        continue;
      if (starts_with(s, "port:")) {
        if (auto v = parse_int(trim(s.substr(5))); v.has_value())
          port_cur.port = std::max(1, *v);
        continue;
      }
      if (starts_with(s, "connected:")) {
        std::string v = trim(s.substr(std::strlen("connected:")));
        port_cur.connected = (v == "true" || v == "True" || v == "1");
        continue;
      }
      if (starts_with(s, "host_device:")) {
        nested = Nested::HostDevice;
        continue;
      }
      if (nested == Nested::HostDevice) {
        if (starts_with(s, "kind:")) {
          std::string v = trim(unquote(s.substr(5)));
          if (v == "gamecontroller")
            port_cur.host_device.kind = DeviceKind::GameController;
          else if (v == "joystick")
            port_cur.host_device.kind = DeviceKind::Joystick;
          else
            port_cur.host_device.kind = DeviceKind::Any;
          continue;
        }
        if (starts_with(s, "index:")) {
          if (auto v = parse_int(trim(s.substr(6))); v.has_value())
            port_cur.host_device.index = *v;
          continue;
        }
        if (starts_with(s, "guid:")) {
          port_cur.host_device.guid = unquote(trim(s.substr(5)));
          continue;
        }
      }
      continue;
    }

    if (sec == Section::Bindings) {
      if (starts_with(s, "-")) {
        flush_binding();
        in_binding = true;
        cur = ControllerBinding{};
        nested = Nested::None;
        std::string rest = trim(s.substr(1));
        if (starts_with(rest, "target_control_id:")) {
          cur.target_control_id =
              unquote(trim(rest.substr(std::strlen("target_control_id:"))));
        }
        continue;
      }
      if (!in_binding)
        continue;

      if (starts_with(s, "target_control_id:")) {
        cur.target_control_id =
            unquote(trim(s.substr(std::strlen("target_control_id:"))));
        continue;
      }
      if (starts_with(s, "host_scancode:")) {
        cur.source_kind = HostSourceKind::HostScancode;
        cur.host_token = trim(s.substr(std::strlen("host_scancode:")));
        cur.scancode = parse_scancode_token(cur.host_token);
        nested = Nested::None;
        continue;
      }
      if (starts_with(s, "host_gamepad:")) {
        cur.source_kind = HostSourceKind::GamepadButton;
        cur.device.kind = DeviceKind::Any;
        nested = Nested::HostGamepad;
        continue;
      }
      if (starts_with(s, "host_joystick:")) {
        cur.source_kind = HostSourceKind::JoystickButton;
        cur.device.kind = DeviceKind::Any;
        nested = Nested::HostJoystick;
        continue;
      }

      if (nested == Nested::HostGamepad) {
        if (starts_with(s, "device:")) {
          std::string v = trim(unquote(s.substr(7)));
          if (v == "gamecontroller")
            cur.device.kind = DeviceKind::GameController;
          else if (v == "joystick")
            cur.device.kind = DeviceKind::Joystick;
          else
            cur.device.kind = DeviceKind::Any;
          continue;
        }
        if (starts_with(s, "index:")) {
          if (auto v = parse_int(trim(s.substr(6))); v.has_value())
            cur.device.index = *v;
          continue;
        }
        if (starts_with(s, "guid:")) {
          cur.device.guid = unquote(trim(s.substr(5)));
          continue;
        }
        if (starts_with(s, "control:")) {
          cur.control = unquote(trim(s.substr(8)));
          continue;
        }
        if (starts_with(s, "direction:")) {
          std::string v = trim(unquote(s.substr(10)));
          cur.direction = (!v.empty() ? v[0] : 0);
          continue;
        }
        if (starts_with(s, "threshold:")) {
          if (auto v = parse_float(trim(s.substr(10))); v.has_value())
            cur.threshold = *v;
          continue;
        }
        if (starts_with(s, "deadzone:")) {
          if (auto v = parse_float(trim(s.substr(9))); v.has_value())
            cur.deadzone = *v;
          continue;
        }
        if (starts_with(s, "scale:")) {
          if (auto v = parse_float(trim(s.substr(6))); v.has_value())
            cur.scale = *v;
          continue;
        }
        if (starts_with(s, "invert:")) {
          std::string v = trim(s.substr(7));
          cur.invert = (v == "true" || v == "True" || v == "1");
          continue;
        }
        // Heuristic: axis mapping is declared by having direction set.
        if (!cur.control.empty() &&
            (cur.direction == '+' || cur.direction == '-')) {
          cur.source_kind = HostSourceKind::GamepadAxis;
        } else if (!cur.control.empty()) {
          cur.source_kind = HostSourceKind::GamepadButton;
        }
      }

      if (nested == Nested::HostJoystick) {
        if (starts_with(s, "device:")) {
          std::string v = trim(unquote(s.substr(7)));
          if (v == "joystick")
            cur.device.kind = DeviceKind::Joystick;
          else if (v == "gamecontroller")
            cur.device.kind = DeviceKind::GameController;
          else
            cur.device.kind = DeviceKind::Any;
          continue;
        }
        if (starts_with(s, "index:")) {
          if (auto v = parse_int(trim(s.substr(6))); v.has_value())
            cur.device.index = *v;
          continue;
        }
        if (starts_with(s, "guid:")) {
          cur.device.guid = unquote(trim(s.substr(5)));
          continue;
        }
        if (starts_with(s, "button:")) {
          if (auto v = parse_int(trim(s.substr(7))); v.has_value()) {
            cur.button = *v;
            cur.source_kind = HostSourceKind::JoystickButton;
          }
          continue;
        }
        if (starts_with(s, "axis:")) {
          if (auto v = parse_int(trim(s.substr(5))); v.has_value()) {
            cur.axis = *v;
            cur.source_kind = HostSourceKind::JoystickAxis;
          }
          continue;
        }
        if (starts_with(s, "hat:")) {
          if (auto v = parse_int(trim(s.substr(4))); v.has_value()) {
            cur.hat = *v;
            cur.source_kind = HostSourceKind::JoystickHat;
          }
          continue;
        }
        if (starts_with(s, "hat_dir:")) {
          cur.hat_dir = unquote(trim(s.substr(8)));
          continue;
        }
        if (starts_with(s, "direction:")) {
          std::string v = trim(unquote(s.substr(10)));
          cur.direction = (!v.empty() ? v[0] : 0);
          continue;
        }
        if (starts_with(s, "threshold:")) {
          if (auto v = parse_float(trim(s.substr(10))); v.has_value())
            cur.threshold = *v;
          continue;
        }
        if (starts_with(s, "deadzone:")) {
          if (auto v = parse_float(trim(s.substr(9))); v.has_value())
            cur.deadzone = *v;
          continue;
        }
        if (starts_with(s, "scale:")) {
          if (auto v = parse_float(trim(s.substr(6))); v.has_value())
            cur.scale = *v;
          continue;
        }
        if (starts_with(s, "invert:")) {
          std::string v = trim(s.substr(7));
          cur.invert = (v == "true" || v == "True" || v == "1");
          continue;
        }
      }
    }
  }

  flush_binding();
  flush_port();

  ensure_ports(st);
  return true;
}

static bool save_controller_mapper(const AppState &st, std::string &err) {
  // Like keymapper_native, preserve existing file and only rewrite bbox/overlay
  // for known ids.
  std::ifstream in(st.mapper_path);
  if (!in.good()) {
    err = "cannot open mapper for read: " + st.mapper_path;
    return false;
  }
  std::vector<std::string> lines;
  std::string line;
  while (std::getline(in, line))
    lines.push_back(line);

  // Update/insert max_ports (top-level) when explicitly set.
  if (st.max_ports_explicit) {
    bool updated = false;
    for (auto &l : lines) {
      std::string s = trim(l);
      if (starts_with(s, "max_ports:")) {
        l = "max_ports: " + std::to_string(std::max(1, st.max_ports));
        updated = true;
        break;
      }
    }
    if (!updated) {
      // Insert right after system_name if present; otherwise at top.
      size_t insert_at = 0;
      for (size_t i = 0; i < lines.size(); ++i) {
        std::string s = trim(lines[i]);
        if (starts_with(s, "system_name:")) {
          insert_at = i + 1;
          break;
        }
      }
      lines.insert(lines.begin() + (long)insert_at,
                   "max_ports: " + std::to_string(std::max(1, st.max_ports)));
    }
  }

  std::unordered_map<std::string, const MapperControl *> by_id;
  by_id.reserve(st.controls.size());
  for (const auto &c : st.controls)
    by_id[c.id] = &c;
  std::unordered_set<std::string> seen;

  auto leading_ws = [](const std::string &s) {
    size_t i = 0;
    while (i < s.size() && std::isspace((unsigned char)s[i]))
      i++;
    return s.substr(0, i);
  };

  std::vector<std::string> out;
  out.reserve(lines.size() + 64);

  std::string current_id;
  const MapperControl *current = nullptr;
  bool in_obj = false;
  bool keep_obj = true;
  bool saw_overlay = false;
  std::string obj_ws = "  ";

  auto append_overlay_if_missing = [&]() {
    if (!in_obj || !keep_obj || current == nullptr || !current->has_overlay ||
        saw_overlay)
      return;
    out.push_back(obj_ws + "  overlay_color:");
    // YAML list items must be indented further than the parent key.
    out.push_back(obj_ws + "    - " + std::to_string(current->r));
    out.push_back(obj_ws + "    - " + std::to_string(current->g));
    out.push_back(obj_ws + "    - " + std::to_string(current->b));
  };

  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string &raw = lines[i];
    const std::string s = trim(raw);
    const std::string ws = leading_ws(raw);

    if (starts_with(s, "- id:") || starts_with(s, "id:")) {
      if (in_obj)
        append_overlay_if_missing();
      in_obj = true;
      saw_overlay = false;
      obj_ws = ws;
      auto pos = s.find(':');
      current_id =
          (pos == std::string::npos) ? "" : unquote(trim(s.substr(pos + 1)));
      auto it = by_id.find(current_id);
      current = (it == by_id.end()) ? nullptr : it->second;
      keep_obj = (current != nullptr);
      if (keep_obj) {
        seen.insert(current_id);
        out.push_back(raw);
      }
      continue;
    }

    if (in_obj && !keep_obj) {
      continue;
    }

    if (in_obj && starts_with(s, "bbox:") && current != nullptr) {
      out.push_back(ws + "bbox:");
      out.push_back(ws + "  x: " + std::to_string(std::max(0, current->x)));
      out.push_back(ws + "  y: " + std::to_string(std::max(0, current->y)));
      out.push_back(ws + "  width: " + std::to_string(std::max(1, current->w)));
      out.push_back(ws +
                    "  height: " + std::to_string(std::max(1, current->h)));
      // Skip old bbox block.
      size_t j = i + 1;
      while (j < lines.size()) {
        std::string sj = trim(lines[j]);
        std::string wj = leading_ws(lines[j]);
        if (sj.empty()) {
          j++;
          continue;
        }
        if (wj.size() <= ws.size())
          break;
        if (starts_with(sj, "x:") || starts_with(sj, "y:") ||
            starts_with(sj, "width:") || starts_with(sj, "height:")) {
          j++;
          continue;
        }
        break;
      }
      i = j - 1;
      continue;
    }

    if (in_obj && starts_with(s, "overlay_color:") && current != nullptr &&
        current->has_overlay) {
      saw_overlay = true;
      out.push_back(ws + "overlay_color:");
      // YAML list items must be indented further than the parent key.
      out.push_back(ws + "  - " +
                    std::to_string(std::clamp(current->r, 0, 255)));
      out.push_back(ws + "  - " +
                    std::to_string(std::clamp(current->g, 0, 255)));
      out.push_back(ws + "  - " +
                    std::to_string(std::clamp(current->b, 0, 255)));
      // Skip old list items.
      size_t j = i + 1;
      while (j < lines.size()) {
        std::string sj = trim(lines[j]);
        std::string wj = leading_ws(lines[j]);
        if (sj.empty()) {
          j++;
          continue;
        }
        // Old files may have invalid indentation; skip any list items following
        // overlay_color.
        if (starts_with(sj, "-")) {
          j++;
          continue;
        }
        if (wj.size() <= ws.size())
          break;
        break;
      }
      i = j - 1;
      continue;
    }

    out.push_back(raw);
  }

  if (in_obj)
    append_overlay_if_missing();

  // Append new controls if any.
  for (const auto &c : st.controls) {
    if (seen.count(c.id))
      continue;
    out.push_back("  - id: " + c.id);
    out.push_back("    kind: " + std::string(control_kind_name(c.kind)));
    out.push_back("    port: " + std::to_string(std::max(1, c.port)));
    out.push_back("    legend:");
    out.push_back("    - " + c.id);
    out.push_back("    legend_combos:");
    out.push_back("      " + c.id + ":");
    out.push_back("      - " + c.id);
    out.push_back("    bbox:");
    out.push_back("      x: " + std::to_string(std::max(0, c.x)));
    out.push_back("      y: " + std::to_string(std::max(0, c.y)));
    out.push_back("      width: " + std::to_string(std::max(1, c.w)));
    out.push_back("      height: " + std::to_string(std::max(1, c.h)));
    if (c.has_overlay) {
      out.push_back("    overlay_color:");
      out.push_back("    - " + std::to_string(std::clamp(c.r, 0, 255)));
      out.push_back("    - " + std::to_string(std::clamp(c.g, 0, 255)));
      out.push_back("    - " + std::to_string(std::clamp(c.b, 0, 255)));
    }
  }

  std::ofstream o(st.mapper_path, std::ios::trunc);
  if (!o.good()) {
    err = "cannot open mapper for write: " + st.mapper_path;
    return false;
  }
  for (const auto &l : out)
    o << l << "\n";
  return true;
}

static bool save_host_controller_map(const AppState &st, std::string &err) {
  std::ofstream o(st.host_map_path, std::ios::trunc);
  if (!o.good()) {
    err = "cannot open host controller map for write: " + st.host_map_path;
    return false;
  }

  o << "controller_map:\n";
  o << "  focus_required: " << (st.focus_required ? "true" : "false") << "\n";
  o << "  ports:\n";
  for (const auto &p : st.ports) {
    o << "  - port: " << p.port << "\n";
    o << "    connected: " << (p.connected ? "true" : "false") << "\n";
    o << "    host_device:\n";
    o << "      kind: " << device_kind_name(p.host_device.kind) << "\n";
    if (p.host_device.index >= 0)
      o << "      index: " << p.host_device.index << "\n";
    if (!p.host_device.guid.empty())
      o << "      guid: '" << p.host_device.guid << "'\n";
  }

  o << "  bindings:\n";
  for (const auto &b : st.bindings) {
    if (b.target_control_id.empty())
      continue;
    o << "  - target_control_id: " << b.target_control_id << "\n";
    if (b.source_kind == HostSourceKind::HostScancode) {
      const std::string tok = !b.host_token.empty()
                                  ? b.host_token
                                  : host_token_for_scancode(b.scancode);
      o << "    host_scancode: " << tok << "\n";
    } else if (b.source_kind == HostSourceKind::GamepadButton ||
               b.source_kind == HostSourceKind::GamepadAxis) {
      o << "    host_gamepad:\n";
      o << "      device: " << device_kind_name(b.device.kind) << "\n";
      if (b.device.index >= 0)
        o << "      index: " << b.device.index << "\n";
      if (!b.device.guid.empty())
        o << "      guid: '" << b.device.guid << "'\n";
      o << "      control: '" << b.control << "'\n";
      if (b.source_kind == HostSourceKind::GamepadAxis &&
          (b.direction == '+' || b.direction == '-')) {
        o << "      direction: '" << b.direction << "'\n";
        o << "      threshold: " << b.threshold << "\n";
        o << "      deadzone: " << b.deadzone << "\n";
        o << "      scale: " << b.scale << "\n";
        o << "      invert: " << (b.invert ? "true" : "false") << "\n";
      }
    } else {
      o << "    host_joystick:\n";
      o << "      device: " << device_kind_name(b.device.kind) << "\n";
      if (b.device.index >= 0)
        o << "      index: " << b.device.index << "\n";
      if (!b.device.guid.empty())
        o << "      guid: '" << b.device.guid << "'\n";
      if (b.source_kind == HostSourceKind::JoystickButton) {
        o << "      button: " << b.button << "\n";
      } else if (b.source_kind == HostSourceKind::JoystickAxis) {
        o << "      axis: " << b.axis << "\n";
        if (b.direction == '+' || b.direction == '-') {
          o << "      direction: '" << b.direction << "'\n";
          o << "      threshold: " << b.threshold << "\n";
        }
        o << "      deadzone: " << b.deadzone << "\n";
        o << "      scale: " << b.scale << "\n";
        o << "      invert: " << (b.invert ? "true" : "false") << "\n";
      } else if (b.source_kind == HostSourceKind::JoystickHat) {
        o << "      hat: " << b.hat << "\n";
        o << "      hat_dir: '" << b.hat_dir << "'\n";
      }
    }
  }

  return true;
}

static std::vector<std::string> validate_links(const AppState &st) {
  std::vector<std::string> errs;
  for (const auto &b : st.bindings) {
    if (b.target_control_id.empty()) {
      errs.push_back("binding missing target_control_id");
      continue;
    }
    if (st.control_index_by_id.find(b.target_control_id) ==
        st.control_index_by_id.end()) {
      errs.push_back("target_control_id not found: " + b.target_control_id);
    }
    int src = 0;
    if (b.source_kind == HostSourceKind::HostScancode)
      src++;
    else if (b.source_kind == HostSourceKind::GamepadButton ||
             b.source_kind == HostSourceKind::GamepadAxis)
      src++;
    else
      src++;
    (void)src;
  }
  return errs;
}

static int find_control_at(const AppState &st, float x, float y) {
  for (int i = (int)st.controls.size() - 1; i >= 0; --i) {
    const auto &c = st.controls[(size_t)i];
    if (!c.has_bbox)
      continue;
    if (x >= c.x && x <= (c.x + c.w) && y >= c.y && y <= (c.y + c.h))
      return i;
  }
  return -1;
}

static std::vector<size_t> selected_in_order(const AppState &st) {
  std::vector<size_t> out;
  if (st.primary >= 0 && (size_t)st.primary < st.controls.size() &&
      st.selected.count((size_t)st.primary)) {
    out.push_back((size_t)st.primary);
  }
  for (size_t i : st.selected) {
    if (!out.empty() && i == out[0])
      continue;
    out.push_back(i);
  }
  std::sort(out.begin() + (out.empty() ? 0 : 1), out.end());
  return out;
}

static bool point_in_resize_handle(const MapperControl &c, float ix, float iy,
                                   float hs_img) {
  if (!c.has_bbox)
    return false;
  const float hx0 = (float)c.x + (float)c.w - hs_img;
  const float hy0 = (float)c.y + (float)c.h - hs_img;
  const float hx1 = (float)c.x + (float)c.w;
  const float hy1 = (float)c.y + (float)c.h;
  return (ix >= hx0 && ix <= hx1 && iy >= hy0 && iy <= hy1);
}

static void select_control(AppState &st, int idx, bool toggle) {
  if (idx < 0 || (size_t)idx >= st.controls.size())
    return;
  if (toggle) {
    if (st.selected.count((size_t)idx))
      st.selected.erase((size_t)idx);
    else
      st.selected.insert((size_t)idx);
    st.primary = idx;
  } else {
    st.selected.clear();
    st.selected.insert((size_t)idx);
    st.primary = idx;
  }
}

static void apply_bbox_to_selected(AppState &st, const char *field, int value) {
  auto sel = selected_in_order(st);
  if (sel.empty())
    return;
  for (size_t i : sel) {
    auto &c = st.controls[i];
    if (!c.has_bbox)
      c.has_bbox = true;
    if (std::strcmp(field, "x") == 0)
      c.x = std::max(0, value);
    else if (std::strcmp(field, "y") == 0)
      c.y = std::max(0, value);
    else if (std::strcmp(field, "w") == 0)
      c.w = std::max(1, value);
    else if (std::strcmp(field, "h") == 0)
      c.h = std::max(1, value);
  }
  st.dirty_mapper = true;
}

static void apply_color_to_selected(AppState &st, int r, int g, int b) {
  auto sel = selected_in_order(st);
  if (sel.empty())
    return;
  for (size_t i : sel) {
    auto &c = st.controls[i];
    c.has_overlay = true;
    c.r = std::clamp(r, 0, 255);
    c.g = std::clamp(g, 0, 255);
    c.b = std::clamp(b, 0, 255);
  }
  st.dirty_mapper = true;
}

static void align_selected(AppState &st, const char *mode) {
  auto ids = selected_in_order(st);
  if (ids.size() < 2)
    return;
  const MapperControl &a = st.controls[ids[0]];
  if (!a.has_bbox)
    return;
  int ax0 = a.x, ay0 = a.y, ax1 = a.x + a.w, ay1 = a.y + a.h;
  int acx = a.x + (a.w / 2);
  int acy = a.y + (a.h / 2);
  for (size_t i = 1; i < ids.size(); ++i) {
    auto &c = st.controls[ids[i]];
    if (!c.has_bbox)
      continue;
    int x = c.x, y = c.y, w = c.w, h = c.h;
    if (std::strcmp(mode, "left") == 0)
      x = ax0;
    else if (std::strcmp(mode, "right") == 0)
      x = ax1 - w;
    else if (std::strcmp(mode, "top") == 0)
      y = ay0;
    else if (std::strcmp(mode, "bottom") == 0)
      y = ay1 - h;
    else if (std::strcmp(mode, "hcenter") == 0)
      x = acx - (w / 2);
    else if (std::strcmp(mode, "vcenter") == 0)
      y = acy - (h / 2);
    c.x = std::max(0, x);
    c.y = std::max(0, y);
  }
  st.dirty_mapper = true;
}

static void size_selected(AppState &st, const char *mode) {
  auto ids = selected_in_order(st);
  if (ids.size() < 2)
    return;
  const MapperControl &a = st.controls[ids[0]];
  if (!a.has_bbox)
    return;
  const int aw = a.w;
  const int ah = a.h;
  for (size_t i = 1; i < ids.size(); ++i) {
    auto &c = st.controls[ids[i]];
    if (!c.has_bbox)
      continue;
    int w = c.w, h = c.h;
    if (std::strcmp(mode, "width") == 0 || std::strcmp(mode, "both") == 0)
      w = aw;
    if (std::strcmp(mode, "height") == 0 || std::strcmp(mode, "both") == 0)
      h = ah;
    c.w = std::max(1, w);
    c.h = std::max(1, h);
  }
  st.dirty_mapper = true;
}

static void distribute_selected(AppState &st, const char *mode) {
  auto ids = selected_in_order(st);
  if (ids.size() < 3)
    return;
  struct Box {
    size_t idx;
    float cx;
    float cy;
  };
  std::vector<Box> boxes;
  boxes.reserve(ids.size());
  for (size_t i : ids) {
    const auto &c = st.controls[i];
    if (!c.has_bbox)
      continue;
    boxes.push_back(Box{i, c.x + c.w * 0.5f, c.y + c.h * 0.5f});
  }
  if (boxes.size() < 3)
    return;
  if (std::strcmp(mode, "horizontal") == 0) {
    std::sort(boxes.begin(), boxes.end(),
              [](const Box &a, const Box &b) { return a.cx < b.cx; });
    float start = boxes.front().cx;
    float end = boxes.back().cx;
    float step = (end - start) / (float)(boxes.size() - 1);
    for (size_t i = 1; i + 1 < boxes.size(); ++i) {
      auto &c = st.controls[boxes[i].idx];
      float center = start + step * (float)i;
      c.x = std::max(0, (int)std::lround(center - c.w * 0.5f));
    }
  } else if (std::strcmp(mode, "vertical") == 0) {
    std::sort(boxes.begin(), boxes.end(),
              [](const Box &a, const Box &b) { return a.cy < b.cy; });
    float start = boxes.front().cy;
    float end = boxes.back().cy;
    float step = (end - start) / (float)(boxes.size() - 1);
    for (size_t i = 1; i + 1 < boxes.size(); ++i) {
      auto &c = st.controls[boxes[i].idx];
      float center = start + step * (float)i;
      c.y = std::max(0, (int)std::lround(center - c.h * 0.5f));
    }
  }
  st.dirty_mapper = true;
}

// Minimal evaluation for highlighting: host-scancode only (gamepad/joystick
// highlight is direct via SDL state in the loop).
static bool is_binding_active_scancode(const ControllerBinding &b,
                                       const uint8_t *ks, int key_count) {
  if (!ks || key_count <= 0)
    return false;
  if (b.scancode < 0 || b.scancode >= key_count)
    return false;
  return ks[b.scancode] != 0;
}

static std::optional<int> parse_int_loose(const std::string &s) {
  std::string t = trim(unquote(s));
  if (t.empty())
    return std::nullopt;
  char *end = nullptr;
  long v = std::strtol(t.c_str(), &end, 0);
  if (end == t.c_str())
    return std::nullopt;
  return (int)v;
}

static float norm_axis_s16(int v) {
  if (v >= 0)
    return (float)v / 32767.0f;
  return (float)v / 32768.0f;
}

static float apply_axis_xform(const ControllerBinding &b, float v) {
  if (b.invert)
    v = -v;
  // deadzone
  if (std::fabs(v) < b.deadzone)
    v = 0.0f;
  v *= b.scale;
  if (v > 1.0f)
    v = 1.0f;
  if (v < -1.0f)
    v = -1.0f;
  return v;
}

static bool is_binding_active(const ControllerBinding &b, const uint8_t *ks,
                              int key_count,
                              const std::vector<SDL_GameController *> &pads,
                              const std::vector<SDL_Joystick *> &joys) {
  if (b.source_kind == HostSourceKind::HostScancode) {
    return is_binding_active_scancode(b, ks, key_count);
  }
  if (b.source_kind == HostSourceKind::GamepadButton) {
    SDL_GameControllerButton btn = SDL_CONTROLLER_BUTTON_INVALID;
    if (!b.control.empty())
      btn = SDL_GameControllerGetButtonFromString(b.control.c_str());
    if (btn == SDL_CONTROLLER_BUTTON_INVALID) {
      if (auto v = parse_int_loose(b.control); v.has_value())
        btn = (SDL_GameControllerButton)*v;
    }
    if (btn == SDL_CONTROLLER_BUTTON_INVALID)
      return false;
    for (auto *gc : pads) {
      if (!gc)
        continue;
      if (SDL_GameControllerGetButton(gc, btn) != 0)
        return true;
    }
    return false;
  }
  if (b.source_kind == HostSourceKind::GamepadAxis) {
    SDL_GameControllerAxis ax = SDL_CONTROLLER_AXIS_INVALID;
    if (!b.control.empty())
      ax = SDL_GameControllerGetAxisFromString(b.control.c_str());
    if (ax == SDL_CONTROLLER_AXIS_INVALID) {
      if (auto v = parse_int_loose(b.control); v.has_value())
        ax = (SDL_GameControllerAxis)*v;
    }
    if (ax == SDL_CONTROLLER_AXIS_INVALID)
      return false;
    for (auto *gc : pads) {
      if (!gc)
        continue;
      int v = (int)SDL_GameControllerGetAxis(gc, ax);
      float nv = apply_axis_xform(b, norm_axis_s16(v));
      if (b.direction == '+') {
        if (nv >= b.threshold)
          return true;
      } else if (b.direction == '-') {
        if (nv <= -b.threshold)
          return true;
      }
    }
    return false;
  }
  if (b.source_kind == HostSourceKind::JoystickButton) {
    if (b.button < 0)
      return false;
    for (auto *j : joys) {
      if (!j)
        continue;
      if (SDL_JoystickGetButton(j, b.button) != 0)
        return true;
    }
    return false;
  }
  if (b.source_kind == HostSourceKind::JoystickAxis) {
    if (b.axis < 0)
      return false;
    for (auto *j : joys) {
      if (!j)
        continue;
      int v = (int)SDL_JoystickGetAxis(j, b.axis);
      float nv = apply_axis_xform(b, norm_axis_s16(v));
      if (b.direction == '+') {
        if (nv >= b.threshold)
          return true;
      } else if (b.direction == '-') {
        if (nv <= -b.threshold)
          return true;
      } else {
        if (std::fabs(nv) >= b.threshold)
          return true;
      }
    }
    return false;
  }
  if (b.source_kind == HostSourceKind::JoystickHat) {
    if (b.hat < 0)
      return false;
    Uint8 want = 0;
    if (b.hat_dir == "up")
      want = SDL_HAT_UP;
    else if (b.hat_dir == "down")
      want = SDL_HAT_DOWN;
    else if (b.hat_dir == "left")
      want = SDL_HAT_LEFT;
    else if (b.hat_dir == "right")
      want = SDL_HAT_RIGHT;
    if (want == 0)
      return false;
    for (auto *j : joys) {
      if (!j)
        continue;
      Uint8 hv = SDL_JoystickGetHat(j, b.hat);
      if ((hv & want) != 0)
        return true;
    }
    return false;
  }
  return false;
}

int main(int argc, char **argv) {
  AppState st;
  st.mapper_path =
      std::getenv("MAPPER")
          ? std::getenv("MAPPER")
          : "examples/hosts/atari2600/atari2600_console_mapper.yaml";
  st.host_map_path =
      std::getenv("HOST_MAP")
          ? std::getenv("HOST_MAP")
          : "examples/hosts/atari2600/host_console_atari2600.yaml";

  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if ((a == "--mapper" || a == "--controller-mapper") && i + 1 < argc)
      st.mapper_path = argv[++i];
    else if ((a == "--host-map" || a == "--controller-map") && i + 1 < argc)
      st.host_map_path = argv[++i];
  }

  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_EVENTS |
               SDL_INIT_GAMECONTROLLER | SDL_INIT_JOYSTICK) != 0) {
    std::fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
    return 2;
  }
  IMG_Init(IMG_INIT_PNG | IMG_INIT_JPG);

  if (!load_controller_mapper(st.mapper_path, st)) {
    std::fprintf(stderr, "Failed loading controller mapper: %s\n",
                 st.mapper_path.c_str());
    return 2;
  }
  (void)load_host_controller_map(st.host_map_path, st);

  SDL_Window *win = SDL_CreateWindow(
      (std::string("PASM Controller Mapper - ") + st.system_name).c_str(),
      SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1280, 780,
      SDL_WINDOW_RESIZABLE);
  if (!win) {
    std::fprintf(stderr, "SDL_CreateWindow failed: %s\n", SDL_GetError());
    return 2;
  }

  SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
  if (!ren)
    ren = SDL_CreateRenderer(win, -1, 0);
  if (!ren) {
    std::fprintf(stderr, "SDL_CreateRenderer failed: %s\n", SDL_GetError());
    return 2;
  }

  SDL_Texture *tex = nullptr;
  SDL_Surface *img = nullptr;
  if (!st.image_file.empty()) {
    img = IMG_Load(st.image_path.c_str());
  }
  int img_w = 0, img_h = 0;
  if (img) {
    img_w = img->w;
    img_h = img->h;
    tex = SDL_CreateTextureFromSurface(ren, img);
    SDL_FreeSurface(img);
  }
  st.auto_fit_pending = true;
  st.request_center = true;

  IMGUI_CHECKVERSION();
  ImGui::CreateContext();
  ImGuiIO &io = ImGui::GetIO();
  io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
  // Prevent off-screen/partial panels due to persisted window positions.
  io.IniFilename = nullptr;
  ImGui::StyleColorsDark();

  ImGui_ImplSDL2_InitForSDLRenderer(win, ren);
  ImGui_ImplSDLRenderer2_Init(ren);

  std::vector<SDL_GameController *> pads;
  std::vector<SDL_Joystick *> joys;
  auto refresh_devices = [&]() {
    for (auto *gc : pads)
      if (gc)
        SDL_GameControllerClose(gc);
    for (auto *j : joys)
      if (j)
        SDL_JoystickClose(j);
    pads.clear();
    joys.clear();
    int n = SDL_NumJoysticks();
    for (int i = 0; i < n; ++i) {
      if (SDL_IsGameController(i)) {
        SDL_GameController *gc = SDL_GameControllerOpen(i);
        if (gc)
          pads.push_back(gc);
      } else {
        SDL_Joystick *j = SDL_JoystickOpen(i);
        if (j)
          joys.push_back(j);
      }
    }
  };
  refresh_devices();

  bool running = true;
  bool want_fit = true;

  while (running) {
    SDL_Event e;
    bool want_refresh_devices = false;
    while (SDL_PollEvent(&e)) {
      ImGui_ImplSDL2_ProcessEvent(&e);
      if (e.type == SDL_QUIT) {
        st.quit_requested = true;
        if (st.quit_stage == 0) {
          st.quit_stage = st.dirty_mapper ? 1 : (st.dirty_map ? 2 : 3);
        }
      }
      if (e.type == SDL_CONTROLLERDEVICEADDED ||
          e.type == SDL_CONTROLLERDEVICEREMOVED ||
          e.type == SDL_JOYDEVICEADDED || e.type == SDL_JOYDEVICEREMOVED) {
        want_refresh_devices = true;
      }

      if (st.capture_host_key && e.type == SDL_KEYDOWN && e.key.repeat == 0) {
        push_undo(st);
        int sc = (int)e.key.keysym.scancode;
        ControllerBinding b;
        b.target_control_id = st.capture_target_id;
        b.source_kind = HostSourceKind::HostScancode;
        b.scancode = sc;
        b.host_token = host_token_for_scancode(sc);
        st.bindings.push_back(b);
        st.capture_status = "Captured host scancode=" + std::to_string(sc);
        st.capture_host_key = false;
        st.dirty_map = true;
      }

      if (st.capture_gamepad) {
        if (e.type == SDL_CONTROLLERBUTTONDOWN) {
          push_undo(st);
          ControllerBinding b;
          b.target_control_id = st.capture_target_id;
          b.source_kind = HostSourceKind::GamepadButton;
          b.device.kind = DeviceKind::Any;
          b.control = SDL_GameControllerGetStringForButton(
              (SDL_GameControllerButton)e.cbutton.button);
          if (b.control.empty())
            b.control = std::to_string((int)e.cbutton.button);
          st.bindings.push_back(b);
          st.capture_status = "Captured gamepad button=" + b.control;
          st.capture_gamepad = false;
          st.dirty_map = true;
        } else if (e.type == SDL_CONTROLLERAXISMOTION) {
          const int v = (int)e.caxis.value;
          if (std::abs(v) > 16000) {
            push_undo(st);
            ControllerBinding b;
            b.target_control_id = st.capture_target_id;
            b.source_kind = HostSourceKind::GamepadAxis;
            b.device.kind = DeviceKind::Any;
            b.control = SDL_GameControllerGetStringForAxis(
                (SDL_GameControllerAxis)e.caxis.axis);
            b.direction = (v > 0) ? '+' : '-';
            b.threshold = 0.5f;
            st.bindings.push_back(b);
            st.capture_status =
                "Captured gamepad axis=" + b.control + b.direction;
            st.capture_gamepad = false;
            st.dirty_map = true;
          }
        }
      }

      if (st.capture_joystick) {
        if (e.type == SDL_JOYBUTTONDOWN) {
          push_undo(st);
          ControllerBinding b;
          b.target_control_id = st.capture_target_id;
          b.source_kind = HostSourceKind::JoystickButton;
          b.device.kind = DeviceKind::Any;
          b.button = (int)e.jbutton.button;
          st.bindings.push_back(b);
          st.capture_status =
              "Captured joystick button=" + std::to_string(b.button);
          st.capture_joystick = false;
          st.dirty_map = true;
        } else if (e.type == SDL_JOYAXISMOTION) {
          const int v = (int)e.jaxis.value;
          if (std::abs(v) > 16000) {
            push_undo(st);
            ControllerBinding b;
            b.target_control_id = st.capture_target_id;
            b.source_kind = HostSourceKind::JoystickAxis;
            b.device.kind = DeviceKind::Any;
            b.axis = (int)e.jaxis.axis;
            b.direction = (v > 0) ? '+' : '-';
            b.threshold = 0.5f;
            st.bindings.push_back(b);
            st.capture_status =
                "Captured joystick axis=" + std::to_string(b.axis) +
                b.direction;
            st.capture_joystick = false;
            st.dirty_map = true;
          }
        } else if (e.type == SDL_JOYHATMOTION) {
          if (e.jhat.value != SDL_HAT_CENTERED) {
            push_undo(st);
            ControllerBinding b;
            b.target_control_id = st.capture_target_id;
            b.source_kind = HostSourceKind::JoystickHat;
            b.device.kind = DeviceKind::Any;
            b.hat = (int)e.jhat.hat;
            if (e.jhat.value & SDL_HAT_UP)
              b.hat_dir = "up";
            else if (e.jhat.value & SDL_HAT_DOWN)
              b.hat_dir = "down";
            else if (e.jhat.value & SDL_HAT_LEFT)
              b.hat_dir = "left";
            else if (e.jhat.value & SDL_HAT_RIGHT)
              b.hat_dir = "right";
            st.bindings.push_back(b);
            st.capture_status =
                "Captured joystick hat=" + std::to_string(b.hat) + "/" +
                b.hat_dir;
            st.capture_joystick = false;
            st.dirty_map = true;
          }
        }
      }
    }
    if (want_refresh_devices)
      refresh_devices();

    ImGui_ImplSDLRenderer2_NewFrame();
    ImGui_ImplSDL2_NewFrame();
    ImGui::NewFrame();

    // Menu
    if (ImGui::BeginMainMenuBar()) {
      if (ImGui::BeginMenu("File")) {
        auto do_save_mapper = [&]() {
          std::string err;
          if (!save_controller_mapper(st, err)) {
            std::fprintf(stderr, "Save mapper failed: %s\n", err.c_str());
          } else {
            st.dirty_mapper = false;
          }
        };
        auto do_save_host_map = [&]() {
          std::string err;
          auto errs = validate_links(st);
          if (!errs.empty()) {
            std::fprintf(stderr, "Invalid links (%zu)\n", errs.size());
          } else if (!save_host_controller_map(st, err)) {
            std::fprintf(stderr, "Save controller map failed: %s\n",
                         err.c_str());
          } else {
            st.dirty_map = false;
          }
        };
        auto do_reload = [&]() {
          AppState fresh;
          // Preserve paths.
          fresh.mapper_path = st.mapper_path;
          fresh.host_map_path = st.host_map_path;
          if (!load_controller_mapper(fresh.mapper_path, fresh)) {
            std::fprintf(stderr, "Reload failed (mapper): %s\n",
                         fresh.mapper_path.c_str());
            return;
          }
          (void)load_host_controller_map(fresh.host_map_path, fresh);
          st = std::move(fresh);
          rebuild_control_index(st);
          ensure_ports(st);
          st.undo_stack.clear();
          st.redo_stack.clear();
          st.dirty_mapper = false;
          st.dirty_map = false;
          want_fit = true;
        };

        if (ImGui::MenuItem("Save Mapper", "Ctrl+S", false, st.dirty_mapper))
          do_save_mapper();
        if (ImGui::MenuItem("Save Host Map", nullptr, false, st.dirty_map))
          do_save_host_map();
        if (ImGui::MenuItem("Reload"))
          do_reload();
        ImGui::Separator();
        if (ImGui::MenuItem("Quit", "Ctrl+Q")) {
          st.quit_requested = true;
          if (st.quit_stage == 0)
            st.quit_stage = st.dirty_mapper ? 1 : (st.dirty_map ? 2 : 3);
        }
        ImGui::EndMenu();
      }
      if (ImGui::BeginMenu("Edit")) {
        if (ImGui::MenuItem("Undo", "Ctrl+Z", false, !st.undo_stack.empty()))
          (void)do_undo(st);
        if (ImGui::MenuItem("Redo", "Ctrl+Y", false, !st.redo_stack.empty()))
          (void)do_redo(st);
        ImGui::Separator();
        bool has_sel = !st.selected.empty();
        if (ImGui::MenuItem("Create New Box", "Ctrl+N", false,
                            st.primary >= 0)) {
          if (st.primary >= 0) {
            push_undo(st);
            auto &c = st.controls[(size_t)st.primary];
            if (!c.has_bbox) {
              c.has_bbox = true;
              c.w = std::max(1, c.w);
              c.h = std::max(1, c.h);
            }
            st.dirty_mapper = true;
          }
        }
        if (ImGui::MenuItem("Duplicate Selected", "Ctrl+D", false, has_sel)) {
          // Duplicate selected controls (useful for creating variants).
          push_undo(st);
          std::vector<MapperControl> adds;
          for (size_t i : selected_in_order(st)) {
            MapperControl c = st.controls[i];
            c.id = c.id + "_COPY";
            // Ensure unique id.
            int n = 2;
            while (st.control_index_by_id.find(c.id) !=
                   st.control_index_by_id.end()) {
              c.id = st.controls[i].id + "_COPY" + std::to_string(n++);
            }
            adds.push_back(c);
          }
          for (auto &c : adds)
            st.controls.push_back(c);
          rebuild_control_index(st);
          ensure_ports(st);
          st.dirty_mapper = true;
        }
        if (ImGui::MenuItem("Delete Selected", "Del", false, has_sel)) {
          // Actually delete selected controls from the controls vector.
          push_undo(st);
          std::vector<MapperControl> new_controls;
          new_controls.reserve(st.controls.size());
          for (size_t i = 0; i < st.controls.size(); ++i) {
            if (!st.selected.count(i)) {
              new_controls.push_back(st.controls[i]);
            }
          }
          st.controls = std::move(new_controls);
          st.selected.clear();
          st.primary = -1;
          rebuild_control_index(st);
          ensure_ports(st);
          st.dirty_mapper = true;
        }
        ImGui::EndMenu();
      }
      ImGui::EndMainMenuBar();
    }

    // Layout: two windows
    ImGuiWindowFlags panel_flags = ImGuiWindowFlags_NoCollapse;
    const bool free_layout = ([]() -> bool {
      const char *v = SDL_getenv("PASM_CONTROLLER_MAPPER_FREE_LAYOUT");
      return (v != nullptr && v[0] != '\0' && v[0] != '0');
    })();

    if (!free_layout) {
      ImGuiViewport *vp = ImGui::GetMainViewport();
      const ImVec2 wp = vp->WorkPos;
      const ImVec2 ws = vp->WorkSize;
      float inspector_w = std::max(380.0f, ws.x * 0.32f);
      inspector_w = std::min(inspector_w, ws.x * 0.60f);
      float canvas_w = std::max(240.0f, ws.x - inspector_w);
      ImGui::SetNextWindowPos(wp, ImGuiCond_Always);
      ImGui::SetNextWindowSize(ImVec2(canvas_w, ws.y), ImGuiCond_Always);
      panel_flags |= ImGuiWindowFlags_NoSavedSettings;
    } else {
      ImGui::SetNextWindowSize(ImVec2(900, 700), ImGuiCond_FirstUseEver);
    }

    ImGui::Begin("Canvas", nullptr, panel_flags);

    ImVec2 canvas_avail = ImGui::GetContentRegionAvail();

    ImGui::Text("Image: %s",
                st.image_file.empty() ? "(none)" : st.image_file.c_str());
    ImGui::SameLine();
    int zoom_pct = clamp_int((int)std::lround(st.zoom * 100.0f), 25, 400);
    ImGui::Text("Zoom");
    ImGui::SameLine();
    ImGui::PushItemWidth(220.0f);
    if (ImGui::SliderInt("##zoom", &zoom_pct, 25, 400, "%d%%")) {
      st.zoom = (float)zoom_pct / 100.0f;
      st.manual_view = true;
    }
    ImGui::PopItemWidth();
    ImGui::SameLine();
    if (ImGui::Button("Fit")) {
      st.auto_fit_pending = true;
      st.request_center = true;
    }
    ImGui::SameLine();
    if (ImGui::Button("100%")) {
      st.zoom = 1.0f;
      st.manual_view = true;
    }

    ImGui::BeginChild("canvas_child", ImVec2(0, 0), true,
                      ImGuiWindowFlags_HorizontalScrollbar);
    ImDrawList *dl = ImGui::GetWindowDrawList();
    ImVec2 origin = ImGui::GetCursorScreenPos();

    ImVec2 content_size =
        ImVec2((float)img_w * st.zoom, (float)img_h * st.zoom);
    if (content_size.x < 1)
      content_size.x = canvas_avail.x;
    if (content_size.y < 1)
      content_size.y = canvas_avail.y;
    ImVec2 child_size = ImGui::GetContentRegionAvail();
    ImVec2 canvas_size = ImVec2(std::max(content_size.x, child_size.x),
                                std::max(content_size.y, child_size.y));

    if (want_fit) {
      st.auto_fit_pending = true;
      st.request_center = true;
      want_fit = false;
    }
    if (st.auto_fit_pending && img_w > 0 && img_h > 0) {
      ImVec2 child_size = ImGui::GetContentRegionAvail();
      float zx = (child_size.x > 1.0f) ? (child_size.x / (float)img_w) : 1.0f;
      float zy = (child_size.y > 1.0f) ? (child_size.y / (float)img_h) : 1.0f;
      st.zoom = std::max(0.05f, std::min(zx, zy));
      st.manual_view = false;
      st.auto_fit_pending = false;
      // recompute content size after zoom
      content_size = ImVec2((float)img_w * st.zoom, (float)img_h * st.zoom);
    }

    if (st.request_center) {
      float cx = std::max(0.0f, (content_size.x - child_size.x) * 0.5f);
      float cy = std::max(0.0f, (content_size.y - child_size.y) * 0.5f);
      ImGui::SetScrollX(cx);
      ImGui::SetScrollY(cy);
      st.request_center = false;
    }

    ImGui::InvisibleButton("canvas_btn", canvas_size,
                           ImGuiButtonFlags_MouseButtonLeft |
                               ImGuiButtonFlags_MouseButtonRight);
    ImVec2 bb_min = ImGui::GetItemRectMin();
    ImVec2 bb_max = ImGui::GetItemRectMax();
    ImVec2 draw_off =
        ImVec2(std::max(0.0f, (child_size.x - content_size.x) * 0.5f),
               std::max(0.0f, (child_size.y - content_size.y) * 0.5f));
    ImVec2 draw_origin = ImVec2(bb_min.x + draw_off.x, bb_min.y + draw_off.y);

    // Background
    dl->AddRectFilled(bb_min, bb_max, IM_COL32(20, 20, 20, 255));

    if (tex) {
      dl->AddImage((ImTextureID)tex, draw_origin,
                   ImVec2(draw_origin.x + content_size.x,
                          draw_origin.y + content_size.y));
    }

    // Mouse pos in image coords
    ImVec2 mp = ImGui::GetIO().MousePos;
    float ix = (mp.x - draw_origin.x) / st.zoom;
    float iy = (mp.y - draw_origin.y) / st.zoom;

    bool hovered = ImGui::IsItemHovered();
    const float hs_px = 10.0f;
    const float hs_img = hs_px / std::max(0.001f, st.zoom);
    int hover_hit = hovered ? find_control_at(st, ix, iy) : -1;
    bool hover_handle = false;
    if (hover_hit >= 0) {
      const auto &hc = st.controls[(size_t)hover_hit];
      hover_handle = point_in_resize_handle(hc, ix, iy, hs_img);
      if (hover_handle)
        ImGui::SetMouseCursor(ImGuiMouseCursor_ResizeNWSE);
      else
        ImGui::SetMouseCursor(ImGuiMouseCursor_Hand);
    }

    if (hovered) {
      float wheel = ImGui::GetIO().MouseWheel;
      if (wheel != 0.0f) {
        const float factor = (wheel > 0.0f) ? 1.15f : (1.0f / 1.15f);
        int zp =
            clamp_int((int)std::lround(st.zoom * 100.0f * factor), 25, 400);
        st.zoom = (float)zp / 100.0f;
        st.manual_view = true;
      }
    }
    bool lclick = hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Left);
    bool rclick = hovered && ImGui::IsMouseClicked(ImGuiMouseButton_Right);

    if (lclick) {
      int hit = hover_hit;
      // Modifier semantics:
      // - no modifiers: replace selection
      // - Shift or Ctrl: toggle selection membership (and for box-select,
      // toggles membership inside the box)
      const SDL_Keymod mods = SDL_GetModState();
      bool toggle = (mods & (KMOD_SHIFT | KMOD_CTRL)) != 0;
      bool was_selected =
          (hit >= 0) ? (st.selected.count((size_t)hit) != 0) : false;

      // Any new click cancels an in-progress box select.
      st.box_selecting = false;

      if (hit >= 0) {
        // If we already have a multi-selection and the user clicks one of the
        // selected items without modifiers, preserve the whole selection
        // (keyboard-mapper behavior).
        if (!toggle && was_selected && st.selected.size() > 1) {
          st.primary = hit;
        } else {
          select_control(st, hit, toggle);
        }
      } else {
        // Start rubber-band selection when clicking empty canvas.
        st.box_selecting = true;
        st.box_toggle = toggle;
        st.box_start = ImVec2(ix, iy);
        st.box_end = st.box_start;
        if (!toggle) {
          // Replace semantics: clear immediately so the user sees selection
          // updating on release.
          st.selected.clear();
          st.primary = -1;
        }
      }

      // Start drag/resize if we clicked on something that remains selected.
      if (hit >= 0 && st.selected.count((size_t)hit) != 0) {
        // If toggle deselected an item, don't start dragging.
        if (!(toggle && was_selected && st.selected.count((size_t)hit) == 0)) {
          push_undo(st);
          st.dragging = true;
          st.resizing = hover_handle;
          st.drag_start = ImVec2(ix, iy);
          st.drag_origin.clear();
          // reuse existing map as origin cache (x/y only) via drag_origin
          for (size_t sid : st.selected) {
            const auto &c = st.controls[sid];
            st.drag_origin[sid] = ImVec2((float)c.x, (float)c.y);
          }
          // Store starting rect of primary for resizing.
          if (st.resizing && st.primary >= 0) {
            const auto &c = st.controls[(size_t)st.primary];
            st.resize_start_w = std::max(1, c.w);
            st.resize_start_h = std::max(1, c.h);
          }
        }
      }
    }

    // Context menu: right click selects or sets primary, then opens popup.
    if (rclick) {
      int hit = hover_hit;
      if (hit >= 0) {
        if (st.selected.count((size_t)hit) != 0) {
          st.primary = hit; // source of operations
        } else {
          select_control(st, hit, false);
        }
      }
      ImGui::OpenPopup("canvas_ctx");
    }

    // Rubber-band (drag) selection update.
    if (st.box_selecting) {
      bool still_down = ImGui::IsMouseDown(ImGuiMouseButton_Left);
      st.box_end = ImVec2(ix, iy);

      float x0 = std::min(st.box_start.x, st.box_end.x);
      float y0 = std::min(st.box_start.y, st.box_end.y);
      float x1 = std::max(st.box_start.x, st.box_end.x);
      float y1 = std::max(st.box_start.y, st.box_end.y);

      // Auto-scroll while selecting near edges of the child window.
      const float margin = 22.0f;
      const float speed = 18.0f;
      float sx = ImGui::GetScrollX();
      float sy = ImGui::GetScrollY();
      if (mp.x < bb_min.x + margin)
        sx = std::max(0.0f, sx - speed);
      if (mp.x > bb_max.x - margin)
        sx = sx + speed;
      if (mp.y < bb_min.y + margin)
        sy = std::max(0.0f, sy - speed);
      if (mp.y > bb_max.y - margin)
        sy = sy + speed;
      ImGui::SetScrollX(sx);
      ImGui::SetScrollY(sy);

      if (!still_down) {
        // Commit selection on mouse release.
        float w_img = x1 - x0;
        float h_img = y1 - y0;
        const float tiny = 2.0f; // treat as click if smaller than this

        std::vector<size_t> hits;
        if (w_img >= tiny || h_img >= tiny) {
          for (size_t i = 0; i < st.controls.size(); ++i) {
            const auto &c = st.controls[i];
            if (!c.has_bbox)
              continue;
            const float cx0 = (float)c.x;
            const float cy0 = (float)c.y;
            const float cx1 = (float)c.x + (float)c.w;
            const float cy1 = (float)c.y + (float)c.h;
            const bool overlap =
                !(x1 < cx0 || x0 > cx1 || y1 < cy0 || y0 > cy1);
            if (overlap)
              hits.push_back(i);
          }
        }

        if (!hits.empty() || !st.box_toggle) {
          if (st.box_toggle) {
            for (size_t i : hits) {
              if (st.selected.count(i))
                st.selected.erase(i);
              else
                st.selected.insert(i);
            }
          } else {
            st.selected.clear();
            for (size_t i : hits)
              st.selected.insert(i);
          }
        }

        if (st.selected.empty()) {
          st.primary = -1;
        } else if (st.primary < 0 ||
                   st.selected.count((size_t)st.primary) == 0) {
          // Pick a stable primary (highest index in selection feels like
          // "last").
          size_t best = 0;
          for (size_t i : st.selected)
            best = std::max(best, i);
          st.primary = (int)best;
        }

        st.box_selecting = false;
        st.box_toggle = false;
      }
    }

    // Drag/resize update
    if (st.dragging) {
      bool still_down = ImGui::IsMouseDown(ImGuiMouseButton_Left);
      if (!still_down) {
        st.dragging = false;
        st.resizing = false;
      } else if (st.primary >= 0) {
        float dx = ix - st.drag_start.x;
        float dy = iy - st.drag_start.y;
        if (st.resizing) {
          size_t pid = (size_t)st.primary;
          auto &c = st.controls[pid];
          if (c.has_bbox) {
            int nw =
                std::max(1, (int)std::lround((float)st.resize_start_w + dx));
            int nh =
                std::max(1, (int)std::lround((float)st.resize_start_h + dy));
            c.w = nw;
            c.h = nh;
            st.dirty_mapper = true;
          }
        } else {
          for (auto &it : st.drag_origin) {
            size_t sid = it.first;
            auto &c = st.controls[sid];
            if (!c.has_bbox)
              continue;
            int nx = std::max(0, (int)std::lround(it.second.x + dx));
            int ny = std::max(0, (int)std::lround(it.second.y + dy));
            c.x = nx;
            c.y = ny;
          }
          st.dirty_mapper = true;
        }

        // Auto-scroll when dragging near edges of the child window.
        const float margin = 22.0f;
        const float speed = 18.0f;
        float sx = ImGui::GetScrollX();
        float sy = ImGui::GetScrollY();
        if (mp.x < bb_min.x + margin)
          sx = std::max(0.0f, sx - speed);
        if (mp.x > bb_max.x - margin)
          sx = sx + speed;
        if (mp.y < bb_min.y + margin)
          sy = std::max(0.0f, sy - speed);
        if (mp.y > bb_max.y - margin)
          sy = sy + speed;
        ImGui::SetScrollX(sx);
        ImGui::SetScrollY(sy);
      }
    }

    // Draw controls
    int key_count = 0;
    const uint8_t *ks = SDL_GetKeyboardState(&key_count);
    const bool has_focus =
        (SDL_GetWindowFlags(win) & SDL_WINDOW_INPUT_FOCUS) != 0;
    for (size_t i = 0; i < st.controls.size(); ++i) {
      const auto &c = st.controls[i];
      if (!c.has_bbox)
        continue;
      ImVec2 p0 =
          ImVec2(draw_origin.x + c.x * st.zoom, draw_origin.y + c.y * st.zoom);
      ImVec2 p1 = ImVec2(p0.x + c.w * st.zoom, p0.y + c.h * st.zoom);

      bool is_primary = (st.primary >= 0 && (size_t)st.primary == i);
      bool is_sel = st.selected.count(i) != 0;
      bool pressed = false;
      if (has_focus || !st.focus_required) {
        for (const auto &b : st.bindings) {
          if (b.target_control_id != c.id)
            continue;
          if (is_binding_active(b, ks, key_count, pads, joys)) {
            pressed = true;
            break;
          }
        }
      }

      ImU32 fill = IM_COL32(c.has_overlay ? c.r : 80, c.has_overlay ? c.g : 160,
                            c.has_overlay ? c.b : 255, is_sel ? 120 : 70);
      ImU32 border = is_primary ? IM_COL32(255, 190, 30, 255)
                                : (is_sel ? IM_COL32(255, 170, 80, 220)
                                          : IM_COL32(20, 20, 20, 200));
      float thick = is_primary ? 2.5f : (is_sel ? 2.0f : 1.0f);
      if (pressed) {
        fill = IM_COL32(255, 90, 90, 140);
        border = IM_COL32(255, 120, 120, 255);
        thick = 2.5f;
      }

      dl->AddRectFilled(p0, p1, fill);
      dl->AddRect(p0, p1, border, 0.0f, 0, thick);

      // resize handle
      dl->AddRectFilled(ImVec2(p1.x - hs_px, p1.y - hs_px), p1,
                        IM_COL32(240, 240, 240, 200));
      dl->AddRect(ImVec2(p1.x - hs_px, p1.y - hs_px), p1,
                  IM_COL32(20, 20, 20, 220));
    }

    // Draw rubber-band selection rectangle on top of the canvas items.
    if (st.box_selecting) {
      float x0 = std::min(st.box_start.x, st.box_end.x);
      float y0 = std::min(st.box_start.y, st.box_end.y);
      float x1 = std::max(st.box_start.x, st.box_end.x);
      float y1 = std::max(st.box_start.y, st.box_end.y);
      ImVec2 sp0 =
          ImVec2(draw_origin.x + x0 * st.zoom, draw_origin.y + y0 * st.zoom);
      ImVec2 sp1 =
          ImVec2(draw_origin.x + x1 * st.zoom, draw_origin.y + y1 * st.zoom);
      dl->AddRectFilled(sp0, sp1, IM_COL32(90, 160, 255, 50));
      dl->AddRect(sp0, sp1, IM_COL32(90, 160, 255, 200), 0.0f, 0, 2.0f);
    }

    // Canvas context menu actions.
    if (ImGui::BeginPopup("canvas_ctx")) {
      int sel_count = (int)st.selected.size();
      if (ImGui::BeginMenu("Align", sel_count >= 2)) {
        if (ImGui::MenuItem("Left")) {
          push_undo(st);
          align_selected(st, "left");
        }
        if (ImGui::MenuItem("Right")) {
          push_undo(st);
          align_selected(st, "right");
        }
        if (ImGui::MenuItem("Top")) {
          push_undo(st);
          align_selected(st, "top");
        }
        if (ImGui::MenuItem("Bottom")) {
          push_undo(st);
          align_selected(st, "bottom");
        }
        if (ImGui::MenuItem("Horizontal Center")) {
          push_undo(st);
          align_selected(st, "hcenter");
        }
        if (ImGui::MenuItem("Vertical Center")) {
          push_undo(st);
          align_selected(st, "vcenter");
        }
        ImGui::EndMenu();
      }
      if (ImGui::BeginMenu("Size", sel_count >= 2)) {
        if (ImGui::MenuItem("Match Width")) {
          push_undo(st);
          size_selected(st, "width");
        }
        if (ImGui::MenuItem("Match Height")) {
          push_undo(st);
          size_selected(st, "height");
        }
        if (ImGui::MenuItem("Match Size")) {
          push_undo(st);
          size_selected(st, "both");
        }
        ImGui::EndMenu();
      }
      if (ImGui::BeginMenu("Distribute", sel_count >= 3)) {
        if (ImGui::MenuItem("Horizontal")) {
          push_undo(st);
          distribute_selected(st, "horizontal");
        }
        if (ImGui::MenuItem("Vertical")) {
          push_undo(st);
          distribute_selected(st, "vertical");
        }
        ImGui::EndMenu();
      }
      if (ImGui::BeginMenu("Color", sel_count >= 1)) {
        if (ImGui::MenuItem("Make Same Color", nullptr, false,
                            sel_count >= 2)) {
          auto ids = selected_in_order(st);
          if (!ids.empty()) {
            push_undo(st);
            const auto &src = st.controls[ids[0]];
            apply_color_to_selected(st, src.r, src.g, src.b);
          }
        }
        if (ImGui::MenuItem("Clear Overlay")) {
          push_undo(st);
          auto ids = selected_in_order(st);
          for (size_t i : ids)
            st.controls[i].has_overlay = false;
          st.dirty_mapper = true;
        }
        ImGui::EndMenu();
      }
      ImGui::EndPopup();
    }

    ImGui::EndChild();

    // Centering must happen inside the child window; schedule it for next
    // frame.

    ImGui::End();

    if (!free_layout) {
      ImGuiViewport *vp = ImGui::GetMainViewport();
      const ImVec2 wp = vp->WorkPos;
      const ImVec2 ws = vp->WorkSize;
      float inspector_w = std::max(380.0f, ws.x * 0.32f);
      inspector_w = std::min(inspector_w, ws.x * 0.60f);
      float canvas_w = std::max(240.0f, ws.x - inspector_w);
      ImGui::SetNextWindowPos(ImVec2(wp.x + canvas_w, wp.y), ImGuiCond_Always);
      ImGui::SetNextWindowSize(ImVec2(inspector_w, ws.y), ImGuiCond_Always);
      panel_flags |= ImGuiWindowFlags_NoSavedSettings;
    } else {
      ImGui::SetNextWindowSize(ImVec2(360, 700), ImGuiCond_FirstUseEver);
    }
    ImGui::Begin("Inspector", nullptr, panel_flags);
    ImGui::BeginChild("inspector_scroll", ImVec2(0, 0), false);

    ImGui::Text("Mapper: %s", st.mapper_path.c_str());
    ImGui::Text("Map: %s", st.host_map_path.c_str());
    {
      static char image_file_buf[512] = {0};
      static std::string image_file_sync;
      if (image_file_sync != st.image_file) {
        std::snprintf(image_file_buf, sizeof(image_file_buf), "%s",
                      st.image_file.c_str());
        image_file_sync = st.image_file;
      }
      if (ImGui::InputText("Image file", image_file_buf,
                           sizeof(image_file_buf))) {
        push_undo(st);
        st.image_file = trim(image_file_buf);
        image_file_sync = st.image_file;
        st.image_path = path_join(dir_of(st.mapper_path), st.image_file);
        st.dirty_mapper = true;
      }
      ImGui::SameLine();
      if (ImGui::Button("Reload Image")) {
        if (tex) {
          SDL_DestroyTexture(tex);
          tex = nullptr;
        }
        img_w = 0;
        img_h = 0;
        if (!st.image_file.empty()) {
          SDL_Surface *tmp = IMG_Load(st.image_path.c_str());
          if (tmp) {
            img_w = tmp->w;
            img_h = tmp->h;
            tex = SDL_CreateTextureFromSurface(ren, tmp);
            SDL_FreeSurface(tmp);
          }
        }
        st.auto_fit_pending = true;
        st.request_center = true;
      }
    }
    ImGui::Separator();

    // Ports
    ImGui::Text("Ports");
    int mp_edit =
        st.max_ports_explicit ? st.max_ports : effective_max_ports(st);
    if (ImGui::InputInt("Max ports", &mp_edit)) {
      push_undo(st);
      st.max_ports_explicit = true;
      st.max_ports = std::max(1, mp_edit);
      ensure_ports(st);
      st.dirty_mapper = true;
      st.dirty_map = true;
    }

    const int maxp = effective_max_ports(st);
    if (st.active_port < 1)
      st.active_port = 1;
    if (st.active_port > maxp)
      st.active_port = maxp;

    if (ImGui::BeginCombo("Active port",
                          ("Port " + std::to_string(st.active_port)).c_str())) {
      for (int p = 1; p <= maxp; ++p) {
        bool sel = (p == st.active_port);
        std::string lab = "Port " + std::to_string(p);
        if (ImGui::Selectable(lab.c_str(), sel))
          st.active_port = p;
        if (sel)
          ImGui::SetItemDefaultFocus();
      }
      ImGui::EndCombo();
    }

    for (auto &p : st.ports) {
      if (p.port < 1 || p.port > maxp)
        continue;
      ImGui::PushID(p.port);
      std::string lab = "Port " + std::to_string(p.port);
      if (ImGui::Checkbox(lab.c_str(), &p.connected)) {
        push_undo(st);
        st.dirty_map = true;
      }
      ImGui::PopID();
    }

    ImGui::Separator();

    // Controls list (so non-visual controls are still editable/mappable).
    ImGui::Text("Controls");
    ImGui::PushItemWidth(-1.0f);
    if (ImGui::BeginListBox("##controls", ImVec2(0, 220))) {
      for (size_t i = 0; i < st.controls.size(); ++i) {
        const auto &c = st.controls[i];
        if (c.port != st.active_port)
          continue;
        bool sel = st.selected.count(i) != 0;
        std::string label = c.id + " [" + control_kind_name(c.kind) + "]";
        if (ImGui::Selectable(label.c_str(), sel)) {
          bool toggle = ImGui::GetIO().KeyShift;
          select_control(st, (int)i, toggle);
        }
      }
      ImGui::EndListBox();
    }
    ImGui::PopItemWidth();

    ImGui::Separator();

    // Selection editor
    if (st.primary < 0 || st.selected.empty()) {
      ImGui::TextDisabled("No control selected");
    } else {
      auto &c0 = st.controls[(size_t)st.primary];
      ImGui::Text("Selected: %s", c0.id.c_str());
      ImGui::Text("Kind: %s  Port: %d", control_kind_name(c0.kind), c0.port);

      int x = c0.x, y = c0.y, w = c0.w, h = c0.h;
      int r = c0.r, g = c0.g, b = c0.b;

      if (ImGui::InputInt("BBox X", &x)) {
        push_undo(st);
        apply_bbox_to_selected(st, "x", x);
      }
      if (ImGui::InputInt("BBox Y", &y)) {
        push_undo(st);
        apply_bbox_to_selected(st, "y", y);
      }
      if (ImGui::InputInt("BBox W", &w)) {
        push_undo(st);
        apply_bbox_to_selected(st, "w", w);
      }
      if (ImGui::InputInt("BBox H", &h)) {
        push_undo(st);
        apply_bbox_to_selected(st, "h", h);
      }

      if (ImGui::InputInt("Overlay R", &r) ||
          ImGui::InputInt("Overlay G", &g) ||
          ImGui::InputInt("Overlay B", &b)) {
        push_undo(st);
        apply_color_to_selected(st, r, g, b);
      }

      ImGui::Separator();
      ImGui::Text("Bindings for selected");

      if (ImGui::Button("Add Host Key Binding")) {
        st.capture_host_key = true;
        st.capture_gamepad = false;
        st.capture_joystick = false;
        st.capture_target_id = c0.id;
        st.capture_status = "Waiting for key...";
      }
      ImGui::SameLine();
      if (ImGui::Button("Add Gamepad Binding")) {
        st.capture_host_key = false;
        st.capture_gamepad = true;
        st.capture_joystick = false;
        st.capture_target_id = c0.id;
        st.capture_status = "Waiting for gamepad input...";
      }
      ImGui::SameLine();
      if (ImGui::Button("Add Joystick Binding")) {
        st.capture_host_key = false;
        st.capture_gamepad = false;
        st.capture_joystick = true;
        st.capture_target_id = c0.id;
        st.capture_status = "Waiting for joystick input...";
      }

      if (st.capture_host_key || st.capture_gamepad || st.capture_joystick) {
        ImGui::TextColored(ImVec4(1, 1, 0, 1), "%s", st.capture_status.c_str());
      }

      // List bindings that target this control
      int remove_idx = -1;
      for (size_t i = 0; i < st.bindings.size(); ++i) {
        const auto &bnd = st.bindings[i];
        if (bnd.target_control_id != c0.id)
          continue;
        ImGui::PushID((int)i);
        std::string label;
        if (bnd.source_kind == HostSourceKind::HostScancode) {
          label = "key " + (bnd.host_token.empty()
                                ? host_token_for_scancode(bnd.scancode)
                                : bnd.host_token);
        } else if (bnd.source_kind == HostSourceKind::GamepadButton) {
          label = std::string("pad btn ") + bnd.control;
        } else if (bnd.source_kind == HostSourceKind::GamepadAxis) {
          label = std::string("pad axis ") + bnd.control + bnd.direction;
        } else if (bnd.source_kind == HostSourceKind::JoystickButton) {
          label = "joy btn " + std::to_string(bnd.button);
        } else if (bnd.source_kind == HostSourceKind::JoystickAxis) {
          label = "joy axis " + std::to_string(bnd.axis) + bnd.direction;
        } else {
          label = "joy hat " + std::to_string(bnd.hat) + "/" + bnd.hat_dir;
        }
        ImGui::BulletText("%s", label.c_str());
        ImGui::SameLine();
        if (ImGui::SmallButton("Remove")) {
          remove_idx = (int)i;
        }
        ImGui::PopID();
      }
      if (remove_idx >= 0) {
        push_undo(st);
        st.bindings.erase(st.bindings.begin() + remove_idx);
        st.dirty_map = true;
      }
    }

    ImGui::EndChild();
    ImGui::End();

    if (st.quit_requested) {
      ImGui::OpenPopup("Exit PASM Controller Mapper##quit_flow");
      st.quit_requested = false;
    }
    if (ImGui::BeginPopupModal("Exit PASM Controller Mapper##quit_flow",
                               nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
      if (st.quit_stage == 1) {
        ImGui::TextUnformatted("Unsaved Mapper Changes");
        ImGui::Separator();
        ImGui::TextUnformatted("The controller-mapper file has unsaved edits.");
        ImGui::TextUnformatted("Save mapper before quitting?");
        bool key_save =
            ImGui::IsKeyPressed(ImGuiKey_S, false) && (ImGui::GetIO().KeyCtrl);
        bool key_skip = ImGui::IsKeyPressed(ImGuiKey_N, false);
        bool key_cancel = ImGui::IsKeyPressed(ImGuiKey_Escape, false);
        if (ImGui::Button("Save Mapper")) {
          std::string err;
          if (save_controller_mapper(st, err)) {
            st.dirty_mapper = false;
            st.quit_stage = st.dirty_map ? 2 : 3;
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
          if (save_controller_mapper(st, err)) {
            st.dirty_mapper = false;
            st.quit_stage = st.dirty_map ? 2 : 3;
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
        ImGui::TextUnformatted("The host controller map has unsaved edits.");
        ImGui::TextUnformatted("Save host map before quitting?");
        bool key_save =
            ImGui::IsKeyPressed(ImGuiKey_S, false) && (ImGui::GetIO().KeyCtrl);
        bool key_skip = ImGui::IsKeyPressed(ImGuiKey_N, false);
        bool key_cancel = ImGui::IsKeyPressed(ImGuiKey_Escape, false);
        if (ImGui::Button("Save Host Map")) {
          auto errs = validate_links(st);
          std::string err;
          if (!errs.empty()) {
            // Keep modal open; user must fix and retry or skip.
          } else if (save_host_controller_map(st, err)) {
            st.dirty_map = false;
            st.quit_stage = 3;
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
          auto errs = validate_links(st);
          std::string err;
          if (errs.empty() && save_host_controller_map(st, err)) {
            st.dirty_map = false;
            st.quit_stage = 3;
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
        ImGui::TextUnformatted(
            "Are you sure you want to quit PASM Controller Mapper?");
        bool key_quit = ImGui::IsKeyPressed(ImGuiKey_Enter, false) ||
                        ImGui::IsKeyPressed(ImGuiKey_Q, false);
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

    // Render
    ImGui::Render();
    SDL_SetRenderDrawColor(ren, 10, 10, 10, 255);
    SDL_RenderClear(ren);
    ImGui_ImplSDLRenderer2_RenderDrawData(ImGui::GetDrawData(), ren);
    SDL_RenderPresent(ren);

    // Keyboard shortcuts
    // While typing in a text widget, don't run global shortcuts or canvas
    // actions.
    if (!io.WantTextInput && !st.capture_host_key && !st.capture_gamepad &&
        !st.capture_joystick) {
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Q))
        running = false;
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_0))
        want_fit = true;
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_S)) {
        std::string err;
        (void)save_controller_mapper(st, err);
        st.dirty_mapper = false;
      }
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Z))
        (void)do_undo(st);
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Y))
        (void)do_redo(st);
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_N)) {
        if (st.primary >= 0) {
          push_undo(st);
          auto &c = st.controls[(size_t)st.primary];
          if (!c.has_bbox) {
            c.has_bbox = true;
            c.w = std::max(1, c.w);
            c.h = std::max(1, c.h);
          }
          st.dirty_mapper = true;
        }
      }
      if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_D) &&
          !st.selected.empty()) {
        push_undo(st);
        std::vector<MapperControl> adds;
        for (size_t i : selected_in_order(st)) {
          MapperControl c = st.controls[i];
          c.id = c.id + "_COPY";
          int n = 2;
          while (st.control_index_by_id.find(c.id) !=
                 st.control_index_by_id.end()) {
            c.id = st.controls[i].id + "_COPY" + std::to_string(n++);
          }
          adds.push_back(c);
        }
        for (auto &c : adds)
          st.controls.push_back(c);
        rebuild_control_index(st);
        ensure_ports(st);
        st.dirty_mapper = true;
      }
    }
  }

  if (tex)
    SDL_DestroyTexture(tex);
  ImGui_ImplSDLRenderer2_Shutdown();
  ImGui_ImplSDL2_Shutdown();
  ImGui::DestroyContext();

  SDL_DestroyRenderer(ren);
  SDL_DestroyWindow(win);

  IMG_Quit();
  SDL_Quit();
  return 0;
}
