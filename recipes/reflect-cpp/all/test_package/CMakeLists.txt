cmake_minimum_required(VERSION 3.12)
project(test_package LANGUAGES CXX)

find_package(reflect-cpp REQUIRED CONFIG)

add_executable(${PROJECT_NAME} test_package.cpp)
target_link_libraries(${PROJECT_NAME} PRIVATE reflect-cpp::reflect-cpp)
target_compile_features(${PROJECT_NAME} PRIVATE cxx_std_20)

if(CONAN_TEST_WITH_MSGPACK)
  target_compile_definitions(${PROJECT_NAME} PRIVATE CONAN_TEST_WITH_MSGPACK)
endif()
