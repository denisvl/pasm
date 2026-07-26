"""Build system generator (CMake, Makefile)."""

from pathlib import Path
from typing import Dict, Any, Optional

from .templates import get_template
from .cpu_hooks import HOOK_NAMES
from .split_layout import all_system_sources, system_ident


def _hooks_enabled(isa_data: Dict[str, Any]) -> bool:
    hooks = isa_data.get("hooks", {})
    return any(hooks.get(name, {}).get("enabled", False) for name in HOOK_NAMES)


def _cmake_path(path: str) -> str:
    # Use forward slashes so CMake doesn't interpret backslashes as escapes on Windows.
    return path.replace("\\", "/")


def _make_path(path: str) -> str:
    return path.replace("\\", "/")


def _cmake_escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
    cpu_core_target = f"{project_name}_cpu_core"
    system_prefix = system_ident(
        isa_data.get("system", {}).get("metadata", {}).get("name", "system"), project_name
    )
    system_target = f"{system_prefix}_system"

    has_hooks = _hooks_enabled(isa_data) if include_hooks is None else include_hooks

    cpu_core_extra_sources = f"    src/{cpu_name}_debug_abi.c"
    if has_hooks:
        cpu_core_extra_sources += f"\n    src/{cpu_name}_hooks.c"
    system_source_lines = [f"    {path}\n" for path in all_system_sources(isa_data, system_prefix)]
    system_sources = "".join(system_source_lines)

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
    include_paths = list(coding.get("include_paths", []))
    overlay_include_dir = Path("examples/hosts/include").resolve()
    if overlay_include_dir.exists():
        overlay_include_dir_str = str(overlay_include_dir)
        if overlay_include_dir_str not in include_paths:
            include_paths.append(overlay_include_dir_str)
    library_paths = coding.get("library_paths", [])
    linked_libraries = coding.get("linked_libraries", [])
    backend_target = _single_host_backend_target(isa_data)
    uses_sdl2_backend = backend_target == "sdl2"
    uses_glfw_backend = backend_target == "glfw"
    interactive_host_backend = backend_target in {"sdl2", "glfw"}
    vs_debugger_args = "--run" if interactive_host_backend else "--test basic"

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
            target_include_directories({cpu_core_target} PRIVATE "${{PASM_SDL2_INCLUDE_DIR}}")
            target_include_directories({system_target} PRIVATE "${{PASM_SDL2_INCLUDE_DIR}}")
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
endif()

if(NOT TARGET glfw AND NOT TARGET glfw::glfw)
    find_package(glfw3 CONFIG QUIET)
endif()
if(NOT TARGET glfw AND NOT TARGET glfw::glfw)
    find_package(glfw3 QUIET)
endif()
find_package(OpenGL REQUIRED)

set(PASM_GLFW_LINK_TARGET glfw)
if(TARGET glfw::glfw)
    set(PASM_GLFW_LINK_TARGET glfw::glfw)
elseif(TARGET glfw)
    set(PASM_GLFW_LINK_TARGET glfw)
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
        find_path(PASM_GLFW_INCLUDE_DIR GLFW/glfw3.h
            HINTS "${{PASM_VCPKG_BASE}}/include"
        )
        if(PASM_GLFW_INCLUDE_DIR)
            target_include_directories({project_name}_test PRIVATE "${{PASM_GLFW_INCLUDE_DIR}}")
            target_include_directories({cpu_core_target} PRIVATE "${{PASM_GLFW_INCLUDE_DIR}}")
            target_include_directories({system_target} PRIVATE "${{PASM_GLFW_INCLUDE_DIR}}")
        endif()

        find_library(PASM_GLFW_LIBRARY NAMES glfw3dll glfw3 glfw
            HINTS "${{PASM_VCPKG_BASE}}/lib" "${{PASM_VCPKG_BASE}}/debug/lib"
        )
        if(PASM_GLFW_LIBRARY)
            set(PASM_GLFW_LINK_TARGET "${{PASM_GLFW_LIBRARY}}")
        endif()
    endif()

    if(PASM_GLFW_LINK_TARGET STREQUAL "glfw")
        message(FATAL_ERROR "GLFW backend selected, but GLFW was not found. Install it with D:/Development/vcpkg/vcpkg.exe install glfw3:${{PASM_VCPKG_TRIPLET}} or pass -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake.")
    endif()
endif()
set(PASM_OPENGL_LINK_TARGET OpenGL::GL)
set(PASM_ALSA_LINK_TARGET "")
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    find_path(PASM_ALSA_INCLUDE_DIR alsa/asoundlib.h)
    find_library(PASM_ALSA_LIBRARY NAMES asound)
    if(NOT PASM_ALSA_INCLUDE_DIR OR NOT PASM_ALSA_LIBRARY)
        message(FATAL_ERROR "GLFW backend audio on Linux requires ALSA development files. Install libasound2-dev on Debian/Ubuntu or alsa-lib-devel on Fedora/RHEL.")
    endif()
    target_include_directories({project_name}_test PRIVATE "${{PASM_ALSA_INCLUDE_DIR}}")
    target_include_directories({system_target} PRIVATE "${{PASM_ALSA_INCLUDE_DIR}}")
    set(PASM_ALSA_LINK_TARGET "${{PASM_ALSA_LIBRARY}}")
endif()
find_package(Threads REQUIRED)
"""

    extra_include_dirs = ""
    if include_paths:
        extra_include_dirs = (
            f"target_include_directories({project_name}_test PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in include_paths)
            + "\n)\n"
            + f"target_include_directories({cpu_core_target} PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in include_paths)
            + "\n)\n"
            + f"target_include_directories({system_target} PRIVATE\n"
            + "\n".join(f'    "{_cmake_path(path)}"' for path in include_paths)
            + "\n)\n"
        )

    extra_link_dirs = ""
    if library_paths:
        extra_link_dirs = (
            f"target_link_directories({project_name}_test PRIVATE\n"
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
    if uses_glfw_backend and not has_explicit_sdl2_link:
        cmake_lib_entries.append("${PASM_SDL2_LINK_TARGET}")
    if uses_glfw_backend:
        cmake_lib_entries.append("${PASM_OPENGL_LINK_TARGET}")
        cmake_lib_entries.append("Threads::Threads")
        cmake_lib_entries.append("$<$<PLATFORM_ID:Windows>:winmm>")
        cmake_lib_entries.append("$<$<PLATFORM_ID:Linux>:${PASM_ALSA_LINK_TARGET}>")
    extra_link_libs = ""
    if cmake_lib_entries:
        extra_link_libs = (
            f"target_link_libraries({system_target} PRIVATE\n"
            + "\n".join(f"    {entry}" for entry in cmake_lib_entries)
            + "\n)\n"
            + f"target_link_libraries({project_name}_test PRIVATE\n"
            + "\n".join(f"    {entry}" for entry in cmake_lib_entries)
            + "\n)\n"
        )

    vs_debugger_setup = f"""
if(WIN32)
    if(NOT DEFINED PASM_VCPKG_TRIPLET OR PASM_VCPKG_TRIPLET STREQUAL "")
        if(DEFINED ENV{{VCPKG_TARGET_TRIPLET}} AND NOT "$ENV{{VCPKG_TARGET_TRIPLET}}" STREQUAL "")
            set(PASM_VCPKG_TRIPLET "$ENV{{VCPKG_TARGET_TRIPLET}}")
        else()
            set(PASM_VCPKG_TRIPLET "x64-windows")
        endif()
    endif()

    set(PASM_VS_VCPKG_ROOT_HINT "")
    if(DEFINED ENV{{VCPKG_ROOT}} AND NOT "$ENV{{VCPKG_ROOT}}" STREQUAL "")
        set(PASM_VS_VCPKG_ROOT_HINT "$ENV{{VCPKG_ROOT}}")
    elseif(EXISTS "D:/Development/vcpkg")
        set(PASM_VS_VCPKG_ROOT_HINT "D:/Development/vcpkg")
    elseif(EXISTS "C:/vcpkg")
        set(PASM_VS_VCPKG_ROOT_HINT "C:/vcpkg")
    endif()

    set(PASM_VS_DEBUGGER_ENVIRONMENT "PATH=$ENV{{PATH}}")
    if(NOT PASM_VS_VCPKG_ROOT_HINT STREQUAL "")
        set(PASM_VS_DEBUGGER_ENVIRONMENT
            "PATH=${{PASM_VS_VCPKG_ROOT_HINT}}/installed/${{PASM_VCPKG_TRIPLET}}/debug/bin\\;${{PASM_VS_VCPKG_ROOT_HINT}}/installed/${{PASM_VCPKG_TRIPLET}}/bin\\;$ENV{{PATH}}"
        )
    endif()

    set_target_properties({project_name}_test PROPERTIES
        VS_DEBUGGER_COMMAND_ARGUMENTS "{_cmake_escape_string(vs_debugger_args)}"
        VS_DEBUGGER_WORKING_DIRECTORY "${{CMAKE_CURRENT_SOURCE_DIR}}"
        VS_DEBUGGER_ENVIRONMENT "${{PASM_VS_DEBUGGER_ENVIRONMENT}}"
    )
endif()
"""

    return template.format(
        project_name=project_name,
        cpu_name=cpu_name,
        cpu_core_target=cpu_core_target,
        system_target=system_target,
        system_sources=system_sources,
        cpu_core_extra_sources=cpu_core_extra_sources,
        dispatch_cmake=dispatch_cmake,
        auto_dependency_setup=auto_dependency_setup,
        extra_include_dirs=extra_include_dirs,
        extra_link_dirs=extra_link_dirs,
        extra_link_libs=extra_link_libs,
        vs_debugger_setup=vs_debugger_setup,
    )


def generate_makefile(
    isa_data: Dict[str, Any],
    cpu_name: str,
    include_hooks: Optional[bool] = None,
    dispatch_mode: str = "switch",
) -> str:
    """Generate Makefile."""

    cpu_prefix = cpu_name.lower()
    system_prefix = system_ident(
        isa_data.get("system", {}).get("metadata", {}).get("name", "system"), cpu_prefix
    )

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
        link_lib_flags_parts.append("$(PASM_GLFW_LIB)")
    if uses_glfw_backend and not has_explicit_sdl2_link:
        link_lib_flags_parts.append("$(PASM_SDL2_LIB)")
    if uses_glfw_backend:
        link_lib_flags_parts.append("$(PASM_OPENGL_LIB)")
        link_lib_flags_parts.append("$(PASM_PTHREAD_LIB)")
        link_lib_flags_parts.append("$(PASM_WINMM_LIB)")
        link_lib_flags_parts.append("$(PASM_ALSA_LIB)")
    link_lib_flags = " ".join(link_lib_flags_parts)
    opengl_make = ""
    if uses_glfw_backend:
        opengl_make = "ifeq ($(OS),Windows_NT)\nPASM_GLFW_LIB = -lglfw3dll\nPASM_SDL2_LIB = -lSDL2\nPASM_OPENGL_LIB = -lopengl32\nPASM_WINMM_LIB = -lwinmm\nPASM_ALSA_LIB =\nPASM_PTHREAD_LIB =\nelse\nPASM_GLFW_LIB = -lglfw\nPASM_SDL2_LIB = -lSDL2\nPASM_OPENGL_LIB = -lGL\nPASM_WINMM_LIB =\nPASM_ALSA_LIB = -lasound\nPASM_PTHREAD_LIB = -pthread\nendif\n"

    system_source_lines = " \\\n    ".join(all_system_sources(isa_data, system_prefix))
    return f"""# Auto-generated Makefile
# Generated by PASM

CC = gcc
AR = ar
CFLAGS = -Wall -Wextra {std_flag} -O2 {include_flags}
LDFLAGS = {link_dir_flags} {link_lib_flags}
{opengl_make}
{dispatch_make}

SRC_DIR = src
BUILD_DIR = build
TARGET = {cpu_prefix}_test
CPU_CORE_LIB = lib{cpu_prefix}_cpu_core.a
SYSTEM_LIB = lib{system_prefix}_system.a

CPU_CORE_SOURCES = $(SRC_DIR)/{cpu_name}_core.c \\
    $(SRC_DIR)/{cpu_name}_decoder.c \\
    $(SRC_DIR)/{cpu_name}_debug_abi.c{f" \\\\\\n    $(SRC_DIR)/{cpu_name}_hooks.c" if has_hooks else ""}

SYSTEM_SOURCES = {system_source_lines}

CPU_CORE_OBJECTS = $(CPU_CORE_SOURCES:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)
SYSTEM_OBJECTS = $(SYSTEM_SOURCES:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)
MAIN_OBJ = $(BUILD_DIR)/main.o

.PHONY: all clean run test

all: $(TARGET)

$(TARGET): $(MAIN_OBJ) $(SYSTEM_LIB) $(CPU_CORE_LIB)
\t$(CC) $(LDFLAGS) -o $@ $(MAIN_OBJ) $(CPU_CORE_LIB) $(SYSTEM_LIB) $(CPU_CORE_LIB)

$(CPU_CORE_LIB): $(CPU_CORE_OBJECTS)
\t$(AR) rcs $@ $^

$(SYSTEM_LIB): $(SYSTEM_OBJECTS)
\t$(AR) rcs $@ $^

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c
\t@mkdir -p $(dir $@)
\t$(CC) $(CFLAGS) -c -o $@ $<

run: $(TARGET)
\t./$(TARGET)

test: $(TARGET)
\t./$(TARGET) --test basic

clean:
\trm -rf $(BUILD_DIR) $(TARGET) $(CPU_CORE_LIB) $(SYSTEM_LIB)
"""
