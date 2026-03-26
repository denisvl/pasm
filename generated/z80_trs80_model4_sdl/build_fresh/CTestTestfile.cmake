# CMake generated Testfile for 
# Source directory: D:/Projects/pasm/generated/z80_trs80_model4_sdl
# Build directory: D:/Projects/pasm/generated/z80_trs80_model4_sdl/build_fresh
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
if(CTEST_CONFIGURATION_TYPE MATCHES "^([Dd][Ee][Bb][Uu][Gg])$")
  add_test(basic_test "D:/Projects/pasm/generated/z80_trs80_model4_sdl/build_fresh/Debug/z80_test.exe" "--test" "basic")
  set_tests_properties(basic_test PROPERTIES  _BACKTRACE_TRIPLES "D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;46;add_test;D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ee][Aa][Ss][Ee])$")
  add_test(basic_test "D:/Projects/pasm/generated/z80_trs80_model4_sdl/build_fresh/Release/z80_test.exe" "--test" "basic")
  set_tests_properties(basic_test PROPERTIES  _BACKTRACE_TRIPLES "D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;46;add_test;D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Mm][Ii][Nn][Ss][Ii][Zz][Ee][Rr][Ee][Ll])$")
  add_test(basic_test "D:/Projects/pasm/generated/z80_trs80_model4_sdl/build_fresh/MinSizeRel/z80_test.exe" "--test" "basic")
  set_tests_properties(basic_test PROPERTIES  _BACKTRACE_TRIPLES "D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;46;add_test;D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;0;")
elseif(CTEST_CONFIGURATION_TYPE MATCHES "^([Rr][Ee][Ll][Ww][Ii][Tt][Hh][Dd][Ee][Bb][Ii][Nn][Ff][Oo])$")
  add_test(basic_test "D:/Projects/pasm/generated/z80_trs80_model4_sdl/build_fresh/RelWithDebInfo/z80_test.exe" "--test" "basic")
  set_tests_properties(basic_test PROPERTIES  _BACKTRACE_TRIPLES "D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;46;add_test;D:/Projects/pasm/generated/z80_trs80_model4_sdl/CMakeLists.txt;0;")
else()
  add_test(basic_test NOT_AVAILABLE)
endif()
