cmake_minimum_required(VERSION 3.16)
project(rockbox_zencrypt_check LANGUAGES C CXX)

set(ROCKBOX_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../rockbox" CACHE PATH "Rockbox source tree")
get_filename_component(ZENUTILS "${ROCKBOX_ROOT}/utils/zenutils" ABSOLUTE)
if(NOT EXISTS "${ZENUTILS}/source/zen_crypt/main.cpp")
    message(FATAL_ERROR "Cannot find zenutils in ROCKBOX_ROOT=${ROCKBOX_ROOT}")
endif()

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 98)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")

include(TestBigEndian)
test_big_endian(BIG_ENDIAN_HOST)
if(BIG_ENDIAN_HOST)
    set(BEECRYPT_BIG_ENDIAN 1)
else()
    set(BEECRYPT_BIG_ENDIAN 0)
endif()

set(BEECRYPT "${ZENUTILS}/libraries/beecrypt-4.1.2")
add_library(rockbox_beecrypt STATIC
    "${BEECRYPT}/beecrypt/blockmode.c"
    "${BEECRYPT}/beecrypt/blowfish.c"
    "${BEECRYPT}/beecrypt/endianness.c"
    "${BEECRYPT}/beecrypt/hmac.c"
    "${BEECRYPT}/beecrypt/hmacsha1.c"
    "${BEECRYPT}/beecrypt/mp.c"
    "${BEECRYPT}/beecrypt/sha1.c"
)
target_include_directories(rockbox_beecrypt PUBLIC "${BEECRYPT}")
# Portable C implementation; no assembly whose word-size assumptions might differ.
target_compile_definitions(rockbox_beecrypt PUBLIC
    MP_WBITS=32 HAVE_UINT64_T=1 HAVE_INLINE=1 WORDS_BIGENDIAN=${BEECRYPT_BIG_ENDIAN}
)

set(ZLIB "${ZENUTILS}/libraries/zlib123")
add_library(rockbox_zlib STATIC
    "${ZLIB}/zlib/adler32.c"
    "${ZLIB}/zlib/compress.c"
    "${ZLIB}/zlib/crc32.c"
    "${ZLIB}/zlib/deflate.c"
    "${ZLIB}/zlib/gzio.c"
    "${ZLIB}/zlib/infback.c"
    "${ZLIB}/zlib/inffast.c"
    "${ZLIB}/zlib/inflate.c"
    "${ZLIB}/zlib/inftrees.c"
    "${ZLIB}/zlib/trees.c"
    "${ZLIB}/zlib/uncompr.c"
    "${ZLIB}/zlib/zutil.c"
)
target_include_directories(rockbox_zlib PUBLIC "${ZLIB}")

add_library(rockbox_shared STATIC
    "${ZENUTILS}/source/shared/cenc.cpp"
    "${ZENUTILS}/source/shared/crypt.cpp"
    "${ZENUTILS}/source/shared/file.cpp"
    "${ZENUTILS}/source/shared/firmware.cpp"
    "${ZENUTILS}/source/shared/utils.cpp"
)
target_include_directories(rockbox_shared PUBLIC
    "${ZENUTILS}/source/shared"
    "${ZENUTILS}/libraries/getpot-c++-1.1.18"
    "${ZENUTILS}/libraries/pelib-0.9"
)
target_link_libraries(rockbox_shared PUBLIC rockbox_beecrypt rockbox_zlib)

add_executable(zen_crypt "${ZENUTILS}/source/zen_crypt/main.cpp")
target_link_libraries(zen_crypt PRIVATE rockbox_shared)
add_executable(firmware_extract "${ZENUTILS}/source/firmware_extract/main.cpp")
target_link_libraries(firmware_extract PRIVATE rockbox_shared)

set(PELIB "${ZENUTILS}/libraries/pelib-0.9")
add_library(rockbox_pelib STATIC
    "${PELIB}/pelib/BoundImportDirectory.cpp"
    "${PELIB}/pelib/ComHeaderDirectory.cpp"
    "${PELIB}/pelib/DebugDirectory.cpp"
    "${PELIB}/pelib/ExportDirectory.cpp"
    "${PELIB}/pelib/IatDirectory.cpp"
    "${PELIB}/pelib/MzHeader.cpp"
    "${PELIB}/pelib/PeFile.cpp"
    "${PELIB}/pelib/PeHeader.cpp"
    "${PELIB}/pelib/PeLibAux.cpp"
    "${PELIB}/pelib/RelocationsDirectory.cpp"
    "${PELIB}/pelib/ResourceDirectory.cpp"
    "${PELIB}/pelib/buffer/InputBuffer.cpp"
    "${PELIB}/pelib/buffer/OutputBuffer.cpp"
)
target_include_directories(rockbox_pelib PUBLIC "${PELIB}")
add_library(rockbox_updater STATIC
    "${ZENUTILS}/source/shared/pe.cpp"
    "${ZENUTILS}/source/shared/updater.cpp"
)
target_link_libraries(rockbox_updater PUBLIC rockbox_shared rockbox_pelib)
add_executable(update_extract "${ZENUTILS}/source/update_extract/main.cpp")
target_link_libraries(update_extract PRIVATE rockbox_updater)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(rockbox_beecrypt PRIVATE -fno-strict-aliasing)
    # Bundled zconf.h has its configure-time unistd include disabled.
    target_compile_options(rockbox_zlib PRIVATE -fno-strict-aliasing "SHELL:-include unistd.h")
endif()
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    foreach(target rockbox_shared zen_crypt firmware_extract rockbox_pelib rockbox_updater update_extract)
        target_compile_options(${target} PRIVATE
            -fno-strict-aliasing -Wno-multichar
            "SHELL:-include cstring" "SHELL:-include cstdlib"
            "SHELL:-include cctype" "SHELL:-include strings.h"
        )
    endforeach()
endif()
