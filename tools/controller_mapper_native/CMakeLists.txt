cmake_minimum_required(VERSION 3.16)
project(controller_mapper_native LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SDL2 REQUIRED sdl2)
pkg_check_modules(SDL2_IMAGE REQUIRED SDL2_image)

set(IMGUI_DIR ${CMAKE_SOURCE_DIR}/../../third_party/imgui)

add_executable(controller_mapper_native
  src/main.cpp
  ${IMGUI_DIR}/imgui.cpp
  ${IMGUI_DIR}/imgui_draw.cpp
  ${IMGUI_DIR}/imgui_tables.cpp
  ${IMGUI_DIR}/imgui_widgets.cpp
  ${IMGUI_DIR}/backends/imgui_impl_sdl2.cpp
  ${IMGUI_DIR}/backends/imgui_impl_sdlrenderer2.cpp
)

target_include_directories(controller_mapper_native PRIVATE
  ${SDL2_INCLUDE_DIRS}
  ${SDL2_IMAGE_INCLUDE_DIRS}
  ${IMGUI_DIR}
  ${IMGUI_DIR}/backends
)

target_compile_options(controller_mapper_native PRIVATE ${SDL2_CFLAGS_OTHER} ${SDL2_IMAGE_CFLAGS_OTHER})

target_link_directories(controller_mapper_native PRIVATE ${SDL2_LIBRARY_DIRS} ${SDL2_IMAGE_LIBRARY_DIRS})

target_link_libraries(controller_mapper_native PRIVATE ${SDL2_LIBRARIES} ${SDL2_IMAGE_LIBRARIES})

if (UNIX AND NOT APPLE)
  target_link_libraries(controller_mapper_native PRIVATE dl pthread)
endif()
