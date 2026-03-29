"""Build system generator (CMake, Makefile)."""

from typing import Dict, Any, Optional

from .templates import get_template
from .cpu_hooks import HOOK_NAMES


def _hooks_enabled(isa_data: Dict[str, Any]) -> bool:
    hooks = isa_data.get("hooks", {})
    return any(hooks.get(name, {}).get("enabled", False) for name in HOOK_NAMES)


def _cmake_path(path: str) -> str:
    # Use forward slashes so CMake doesn't interpret backslashes as escapes on Windows.
    return path.replace("\\", "/")


def _make_path(path: str) -> str:
    return path.replace("\\", "/")


def _single_host_backend_target(isa_data: Dict[str, Any]) -> Optional[str]:
    target = str(isa_data.get("host_backend_target", "")).strip().lower()
    hosts = isa_data.get("hosts", []) or []
    has_hosts = bool(hosts)
    if not target:
        if not has_hosts:
            return None
        declared_targets = sorted(
            {
                str((host.get("backend") or {}).get("target", "")).strip().lower()
                for host in hosts
                if isinstance(host, dict)
            }
            - {""}
        )
        if not declared_targets:
            return None
        if len(declared_targets) != 1:
            raise ValueError(
                f"multiple host backend targets are not supported for build generation: {declared_targets}"
            )
        target = declared_targets[0]
    if target not in {"sdl2", "stub", "glfw"}:
        raise ValueError(f"unsupported host backend target for build generation: {target}")
    return target


def generate_cmake(
    isa_data: Dict[str, Any],
    cpu_name: str,
    include_hooks: Optional[bool] = None,
    dispatch_mode: str = "switch",
) -> str:
    """Generate CMakeLists.txt."""

    project_name = cpu_name.lower()

    has_hooks = _hooks_enabled(isa_data) if include_hooks is None else include_hooks

    extra_sources = f"    src/{cpu_name}_debug_abi.c\n"
    if has_hooks:
        extra_sources += f"    src/{cpu_name}_hooks.c\n"

    dispatch_cmake = ""
    if dispatch_mode == "threaded":
        dispatch_cmake = (
            'if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang|AppleClang")\n'
            "    add_compile_definitions(CPU_USE_THREADED_DISPATCH)\n"
            "endif()\n"
        )
    elif dispatch_mode == "both":
        dispatch_cmake = (
            'option(USE_THREADED_DISPATCH "Enable threaded dispatch (GCC/Clang)" OFF)\n'
            'if(USE_THREADED_DISPATCH AND CMAKE_C_COMPILER_ID MATCHES "GNU|Clang|AppleClang")\n'
            "    add_compile_definitions(CPU_USE_THREADED_DISPATCH)\n"
            "endif()\n"
        )
    elif dispatch_mode != "switch":
        raise ValueError(f"Unsupported dispatch mode: {dispatch_mode}")

    template = get_template("cmake")
    coding = isa_data.get("coding", {})
    include_paths = coding.get("include_paths", [])
    library_paths = coding.get("library_paths", [])
    linked_libraries = coding.get("linked_libraries", [])
    backend_target = _single_host_backend_target(isa_data)
    uses_sdl2_backend = backend_target == "sdl2"
    uses_glfw_backend = backend_target == "glfw"

    auto_dependency_setup = ""
    if uses_sdl2_backend:
        auto_dependency_setup = f"""
if(NOT DEFINED PASM_VCPKG_TRIPLET OR PASM_VCPKG_TRIPLET STREQUAL "")
    if(DEFINED ENV{{VCPKG_TARGET_TRIPLET}} AND NOT "$ENV{{VCPKG_TARGET_TRIPLET}}" STREQUAL "")
        set(PASM_VCPKG_TRIPLET "$ENV{{VCPKG_TARGET_TRIPLET}}")
    elseif(WIN32)
        set(PASM_VCPKG_TRIPLET "x64-windows")
    elseif(APPLE)
        set(PASM_VCPKG_TRIPLET "x64-osx")
    else()
        set(PASM_VCPKG_TRIPLET "x64-linux")
    endif()
endif()

if(NOT TARGET SDL2::SDL2)
    find_package(SDL2 CONFIG QUIET)
endif()

set(PASM_SDL2_LINK_TARGET SDL2)
if(TARGET SDL2::SDL2)
    set(PASM_SDL2_LINK_TARGET SDL2::SDL2)
else()
    set(PASM_VCPKG_ROOT_HINT "")
    if(DEFINED ENV{{VCPKG_ROOT}} AND NOT "$ENV{{VCPKG_ROOT}}" STREQUAL "")
        set(PASM_VCPKG_ROOT_HINT "$ENV{{VCPKG_ROOT}}")
    elseif(EXISTS "D:/Development/vcpkg")
        set(PASM_VCPKG_ROOT_HINT "D:/Development/vcpkg")
    elseif(EXISTS "C:/vcpkg")
        set(PASM_VCPKG_ROOT_HINT "C:/vcpkg")
    endif()

    if(NOT PASM_VCPKG_ROOT_HINT STREQUAL "")
        set(PASM_VCPKG_BASE "${{PASM_VCPKG_ROOT_HINT}}/installed/${{PASM_VCPKG_TRIPLET}}")
        find_path(PASM_SDL2_INCLUDE_DIR SDL2/SDL.h
            HINTS "${{PASM_VCPKG_BASE}}/include"
        )
        if(PASM_SDL2_INCLUDE_DIR)
            target_include_directories({project_name}_test PRIVATE "${{PASM_SDL2_INCLUDE_DIR}}")
            target_include_directories({project_name}_emu PRIVATE "${{PASM_SDL2_INCLUDE_DIR}}")
        endif()

        find_library(PASM_SDL2_LIBRARY NAMES SDL2
            HINTS "${{PASM_VCPKG_BASE}}/lib" "${{PASM_VCPKG_BASE}}/debug/lib"
        )
        if(PASM_SDL2_LIBRARY)
            set(PASM_SDL2_LINK_TARGET "${{PASM_SDL2_LIBRARY}}")
        endif()
    endif()
endif()
"""
    elif uses_glfw_backend:
        auto_dependency_setup = """
if(NOT TARGET glfw AND NOT TARGET glfw::glfw)
    find_package(glfw3 CONFIG QUIET)
endif()
if(NOT TARGET glfw AND NOT TARGET glfw::glfw)
    find_package(glfw3 QUIET)
endif()

set(PASM_GLFW_LINK_TARGET glfw)
if(TARGET glfw::glfw)
    set(PASM_GLFW_LINK_TARGET glfw::glfw)
elseif(TARGET glfw)
    set(PASM_GLFW_LINK_TARGET glfw)
endif()
"""

    extra_include_dirs = ""
    if include_paths:
        extra_include_dirs = (
            f"target_include_directories({project_name}_test PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in include_paths)
            + "\n)\n"
            + f"target_include_directories({project_name}_emu PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in include_paths)
            + "\n)\n"
        )

    extra_link_dirs = ""
    if library_paths:
        extra_link_dirs = (
            f"target_link_directories({project_name}_test PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in library_paths)
            + "\n)\n"
            + f"target_link_directories({project_name}_emu PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in library_paths)
            + "\n)\n"
        )

    cmake_lib_entries: list[str] = []
    has_explicit_sdl2_link = False
    has_explicit_glfw_link = False
    for lib in linked_libraries:
        if "name" in lib:
            name = str(lib["name"])
            if name == "SDL2":
                if uses_sdl2_backend:
                    has_explicit_sdl2_link = True
                    cmake_lib_entries.append("${PASM_SDL2_LINK_TARGET}")
                else:
                    cmake_lib_entries.append("SDL2")
            elif name.lower() == "glfw":
                if uses_glfw_backend:
                    has_explicit_glfw_link = True
                    cmake_lib_entries.append("${PASM_GLFW_LINK_TARGET}")
                else:
                    cmake_lib_entries.append(name)
            else:
                cmake_lib_entries.append(name)
        elif "path" in lib:
            path_str = str(lib["path"])
            if "sdl2" in path_str.lower():
                has_explicit_sdl2_link = True
            if "glfw" in path_str.lower():
                has_explicit_glfw_link = True
            cmake_lib_entries.append(f'"{_cmake_path(path_str)}"')
    if uses_sdl2_backend and not has_explicit_sdl2_link:
        cmake_lib_entries.append("${PASM_SDL2_LINK_TARGET}")
    if uses_glfw_backend and not has_explicit_glfw_link:
        cmake_lib_entries.append("${PASM_GLFW_LINK_TARGET}")
    extra_link_libs = ""
    if cmake_lib_entries:
        extra_link_libs = (
            f"target_link_libraries({project_name}_test PRIVATE\n"
            + "\n".join(f"    {entry}" for entry in cmake_lib_entries)
            + "\n)\n"
            + f"target_link_libraries({project_name}_emu PRIVATE\n"
            + "\n".join(f"    {entry}" for entry in cmake_lib_entries)
            + "\n)\n"
        )

    return template.format(
        project_name=project_name,
        cpu_name=cpu_name,
        extra_sources=extra_sources,
        dispatch_cmake=dispatch_cmake,
        auto_dependency_setup=auto_dependency_setup,
        extra_include_dirs=extra_include_dirs,
        extra_link_dirs=extra_link_dirs,
        extra_link_libs=extra_link_libs,
    )


def generate_makefile(
    isa_data: Dict[str, Any],
    cpu_name: str,
    include_hooks: Optional[bool] = None,
    dispatch_mode: str = "switch",
) -> str:
    """Generate Makefile."""

    cpu_prefix = cpu_name.lower()

    has_hooks = _hooks_enabled(isa_data) if include_hooks is None else include_hooks

    std_flag = "-std=c11"
    if dispatch_mode == "switch":
        dispatch_make = ""
    elif dispatch_mode == "threaded":
        dispatch_make = "CFLAGS += -DCPU_USE_THREADED_DISPATCH\n"
    elif dispatch_mode == "both":
        dispatch_make = (
            "DISPATCH ?= switch\n"
            "ifeq ($(DISPATCH),threaded)\n"
            "CFLAGS += -DCPU_USE_THREADED_DISPATCH\n"
            "endif\n"
        )
    else:
        raise ValueError(f"Unsupported dispatch mode: {dispatch_mode}")

    coding = isa_data.get("coding", {})
    backend_target = _single_host_backend_target(isa_data)
    uses_sdl2_backend = backend_target == "sdl2"
    uses_glfw_backend = backend_target == "glfw"
    include_flags = " ".join(
        f'-I\"{_make_path(path)}\"' for path in coding.get("include_paths", [])
    )
    link_dir_flags = " ".join(
        f'-L\"{_make_path(path)}\"' for path in coding.get("library_paths", [])
    )
    link_lib_flags_parts: list[str] = []
    has_explicit_sdl2_link = False
    has_explicit_glfw_link = False
    for lib in coding.get("linked_libraries", []):
        if "name" in lib:
            lib_name = str(lib["name"])
            if lib_name == "SDL2":
                has_explicit_sdl2_link = True
            if lib_name.lower() == "glfw":
                has_explicit_glfw_link = True
            link_lib_flags_parts.append(f"-l{lib_name}")
        elif "path" in lib:
            path_str = str(lib["path"])
            if "sdl2" in path_str.lower():
                has_explicit_sdl2_link = True
            if "glfw" in path_str.lower():
                has_explicit_glfw_link = True
            link_lib_flags_parts.append(f'"{_make_path(path_str)}"')
    if uses_sdl2_backend and not has_explicit_sdl2_link:
        link_lib_flags_parts.append("-lSDL2")
    if uses_glfw_backend and not has_explicit_glfw_link:
        link_lib_flags_parts.append("-lglfw")
    link_lib_flags = " ".join(link_lib_flags_parts)

    return f"""# Auto-generated Makefile
# Generated by PASM

CC = gcc
AR = ar
CFLAGS = -Wall -Wextra {std_flag} -O2 {include_flags}
LDFLAGS = {link_dir_flags} {link_lib_flags}
{dispatch_make}

SRC_DIR = src
BUILD_DIR = build
TARGET = {cpu_prefix}_test
EMU_LIB = lib{cpu_prefix}_emu.a

SOURCES = $(SRC_DIR)/{cpu_name}.c \\
    $(SRC_DIR)/{cpu_name}_decoder.c \\
    $(SRC_DIR)/{cpu_name}_debug_abi.c

# Add hooks if enabled
{f"SOURCES += $(SRC_DIR)/{cpu_name}_hooks.c" if has_hooks else ""}

OBJECTS = $(SOURCES:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)
MAIN_OBJ = $(BUILD_DIR)/main.o

.PHONY: all clean run test

all: $(TARGET)

$(TARGET): $(MAIN_OBJ) $(EMU_LIB)
\t$(CC) $(LDFLAGS) -o $@ $(MAIN_OBJ) $(EMU_LIB)

$(EMU_LIB): $(OBJECTS)
\t$(AR) rcs $@ $^

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c
\t@mkdir -p $(dir $@)
\t$(CC) $(CFLAGS) -c -o $@ $<

run: $(TARGET)
\t./$(TARGET)

test: $(TARGET)
\t./$(TARGET) --test basic

clean:
\trm -rf $(BUILD_DIR) $(TARGET) $(EMU_LIB)
"""
