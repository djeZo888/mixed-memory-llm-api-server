# Load with -DCMAKE_PROJECT_INCLUDE=/absolute/path/to/register-tests.cmake.
# Defer until the pinned upstream targets exist; keep its CMAKE_SOURCE_DIR intact.
if(CMAKE_CURRENT_SOURCE_DIR STREQUAL CMAKE_SOURCE_DIR AND PROJECT_NAME STREQUAL "llama.cpp")
    if(CMAKE_VERSION VERSION_LESS 3.19)
        message(FATAL_ERROR "D3P focused tests require CMake 3.19 or newer")
    endif()
    enable_testing()
    set_property(GLOBAL PROPERTY D3P_TEST_SOURCE_DIR "${CMAKE_CURRENT_LIST_DIR}")
    function(d3p_register_focused_tests)
        get_property(d3p_test_source GLOBAL PROPERTY D3P_TEST_SOURCE_DIR)
        include("${d3p_test_source}/CMakeLists.txt")
    endfunction()
    cmake_language(DEFER CALL d3p_register_focused_tests)
endif()
