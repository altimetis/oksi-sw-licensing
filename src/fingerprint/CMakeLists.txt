cmake_minimum_required(VERSION 3.15)
project(oksi_fingerprint CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(oksi_fingerprint fingerprint.cpp)

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

# Tests
include(CTest)
if(BUILD_TESTING)
    enable_testing()
    # Paths to test data files in source tree
    set(TEST_MID_ABCD "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/data/mid_abcd.txt")
    set(TEST_MID_TMID "${CMAKE_CURRENT_SOURCE_DIR}/../../tests/data/mid_test_machine_id.txt")

    # Helper to register a CLI test with expected output regex
    function(add_fp_test name expected)
        add_test(NAME ${name} COMMAND $<TARGET_FILE:oksi_fingerprint> ${ARGN})
        set_tests_properties(${name} PROPERTIES PASS_REGULAR_EXPRESSION "${expected}")
    endfunction()

    # Precomputed expected outputs (SHA-256 -> base64url w/o padding)
    # mid: abcd
    add_fp_test(fp_abcd_no_salt "yTsFgAbUO-EC-QOPPPGqz0WhmfqWMbIZARKwKWF9ldw" --machine-id-file "${TEST_MID_ABCD}")
    add_fp_test(fp_abcd_salt_s "OYGS4aIPb4PWsdsbF4c9GhkCp_6mFrugH7-4ufNR_-4" --machine-id-file "${TEST_MID_ABCD}" --salt s)
    add_fp_test(fp_abcd_salt_prod42 "65wHlLMSzCOIJAX310spHpZj0hVpklt-UQY3fq6cBGA" --machine-id-file "${TEST_MID_ABCD}" --salt prod-42)

    # mid: test-machine-id
    add_fp_test(fp_tmid_no_salt "sVZ6CUxvt-celxdj2bqMUFvzqNGQE9xZ8SGTNh_LU6o" --machine-id-file "${TEST_MID_TMID}")
    add_fp_test(fp_tmid_salt_s "yhj7m4amszguzHbxU9--PWsfRhmytmNEqB4u0Z4Vmk0" --machine-id-file "${TEST_MID_TMID}" --salt s)
    add_fp_test(fp_tmid_salt_prod42 "CLm2TxO-CbHvAaMX4uS6G4PqN28KVF4e-_wskFWLwHs" --machine-id-file "${TEST_MID_TMID}" --salt prod-42)
endif()
