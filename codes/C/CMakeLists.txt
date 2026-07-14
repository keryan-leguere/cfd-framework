cmake_minimum_required(VERSION 3.16)
project(compile_course C)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Always emit compile_commands.json — needed for clangd to see the real
# flags used to build each file (see earlier debugging: without this,
# clangd falls back to a generic guess and warnings silently disappear).
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ------------------------------------------------------------------
# Default build type if none specified on the command line
# ------------------------------------------------------------------
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Dev" CACHE STRING "Build type" FORCE)
endif()

set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS
    "Debug" "Dev" "Release" "ReleaseHardened")

# ------------------------------------------------------------------
# DEBUG — chasing a specific bug (sanitizers on, clean stack traces)
# ------------------------------------------------------------------
set(CMAKE_C_FLAGS_DEBUG
    "-g3 -Og -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer"
)
set(CMAKE_EXE_LINKER_FLAGS_DEBUG
    "-fsanitize=address,undefined"
)

# ------------------------------------------------------------------
# DEV — everyday coding, fast rebuilds, warnings treated as errors
# ------------------------------------------------------------------
set(CMAKE_C_FLAGS_DEV
    "-g -O0 -Wall -Wextra -Wpedantic -Werror"
)

# ------------------------------------------------------------------
# RELEASE — maximum speed, ship-on-this-exact-machine
# ------------------------------------------------------------------
set(CMAKE_C_FLAGS_RELEASE
    "-O3 -march=native -flto -DNDEBUG -Wall -Wextra"
)
set(CMAKE_EXE_LINKER_FLAGS_RELEASE
    "-flto"
)

# ------------------------------------------------------------------
# RELEASEHARDENED — production binary facing untrusted input
# ------------------------------------------------------------------
set(CMAKE_C_FLAGS_RELEASEHARDENED
    "-O2 -DNDEBUG -Wall -Wextra -D_FORTIFY_SOURCE=2 -fstack-protector-strong"
)

# ------------------------------------------------------------------
# Target — this is the two-file example from the compilation course:
#   main.c        -> uses printf + calls square()
#   math_utils.c  -> defines square()
#   math_utils.h  -> declares square(), included by both
# ------------------------------------------------------------------
add_executable(program
    main.c
    math_utils.c
)

# math_utils.h lives in the same directory as the sources, so the default
# include search already finds it via #include "math_utils.h" — this line
# is only needed if you move headers into a separate include/ folder later.
target_include_directories(program PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
