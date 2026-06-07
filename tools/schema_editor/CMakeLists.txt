cmake_minimum_required(VERSION 3.16)
project(schema_editor LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Dependencies via FetchContent ---
include(FetchContent)

# yaml-cpp
FetchContent_Declare(yaml-cpp
    GIT_REPOSITORY https://github.com/jbeder/yaml-cpp.git
    GIT_TAG yaml-cpp-0.9.0
)
set(YAML_CPP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_CONTRIB OFF CACHE BOOL "" FORCE)
set(YAML_CPP_BUILD_TOOLS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(yaml-cpp)

# nlohmann-json
FetchContent_Declare(nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG v3.11.3
)
FetchContent_MakeAvailable(nlohmann_json)

# --- SDL2 ---
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
    pkg_check_modules(SDL2 REQUIRED sdl2)
    pkg_check_modules(SDL2_IMAGE REQUIRED SDL2_image)
else()
    find_package(SDL2 REQUIRED)
    find_package(SDL2_image REQUIRED)
endif()

# --- Dear ImGui (vendored) ---
set(IMGUI_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/imgui)

# --- Sources ---
set(SOURCES
    src/main.cpp
    src/app.cpp
    src/schema_registry.cpp
    src/file_browser.cpp
    src/schema_parser.cpp
    src/yaml_loader.cpp
    src/form_renderer.cpp
    src/c_code_editor.cpp
    ${IMGUI_DIR}/imgui.cpp
    ${IMGUI_DIR}/imgui_demo.cpp
    ${IMGUI_DIR}/imgui_draw.cpp
    ${IMGUI_DIR}/imgui_tables.cpp
    ${IMGUI_DIR}/imgui_widgets.cpp
    ${IMGUI_DIR}/backends/imgui_impl_sdl2.cpp
    ${IMGUI_DIR}/backends/imgui_impl_sdlrenderer2.cpp
)

set(HEADERS
    src/app.h
    src/schema_registry.h
    src/file_browser.h
    src/schema_parser.h
    src/yaml_loader.h
    src/form_renderer.h
    src/c_code_editor.h
)

# --- Executable ---
add_executable(schema_editor ${SOURCES} ${HEADERS})

target_include_directories(schema_editor PRIVATE
    src
    ${IMGUI_DIR}
    ${IMGUI_DIR}/backends
)

if(PkgConfig_FOUND)
    target_include_directories(schema_editor PRIVATE
        ${SDL2_INCLUDE_DIRS}
        ${SDL2_IMAGE_INCLUDE_DIRS}
    )
    target_compile_options(schema_editor PRIVATE ${SDL2_CFLAGS_OTHER} ${SDL2_IMAGE_CFLAGS_OTHER})
    target_link_directories(schema_editor PRIVATE ${SDL2_LIBRARY_DIRS} ${SDL2_IMAGE_LIBRARY_DIRS})
    target_link_libraries(schema_editor PRIVATE ${SDL2_LIBRARIES} ${SDL2_IMAGE_LIBRARIES})
else()
    target_link_libraries(schema_editor PRIVATE SDL2::SDL2 SDL2_image::SDL2_image)
endif()

target_link_libraries(schema_editor PRIVATE
    yaml-cpp
    nlohmann_json::nlohmann_json
)

# --- Test executable (no ImGui, no SDL) ---
add_executable(test_roundtrip
    src/test_roundtrip.cpp
    src/schema_registry.cpp
    src/schema_parser.cpp
    src/yaml_loader.cpp
)
target_include_directories(test_roundtrip PRIVATE src)
target_link_libraries(test_roundtrip PRIVATE yaml-cpp nlohmann_json::nlohmann_json)

if(UNIX AND NOT APPLE)
    target_link_libraries(schema_editor PRIVATE dl pthread)
    target_link_libraries(test_roundtrip PRIVATE dl pthread)
endif()

# --- Testing ---
include(CTest)
get_filename_component(PROJECT_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../.. ABSOLUTE)
add_test(
    NAME roundtrip
    COMMAND test_roundtrip
    WORKING_DIRECTORY ${PROJECT_ROOT}
)
