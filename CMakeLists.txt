cmake_minimum_required(VERSION 3.15)
project(oksi_fingerprint CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(oksi_fingerprint src/fingerprint.cpp)

# Place runtime outputs under the bin tree
set_target_properties(oksi_fingerprint PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)

# Handle multi-config generators (e.g., MSVC)
foreach(OUTPUTCONFIG DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)
    string(TOUPPER ${OUTPUTCONFIG} OUTPUTCONFIG_UPPER)
    set_target_properties(oksi_fingerprint PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY_${OUTPUTCONFIG_UPPER} "${CMAKE_BINARY_DIR}/bin"
    )
endforeach()

# Provide an install target for system/user installs (e.g., /usr/local/bin)
install(TARGETS oksi_fingerprint RUNTIME DESTINATION bin)
