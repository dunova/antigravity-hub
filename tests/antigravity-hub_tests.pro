QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = antigravity-hub_tests
TEMPLATE = app

# Strict compiler hygiene & warning flags
QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

# Headers
HEADERS += \
    ../src/theme.h \
    ../src/translator.h \
    ../src/iconprovider.h

exists(../src/models.h):  HEADERS += ../src/models.h
exists(../src/backend.h): HEADERS += ../src/backend.h

# Sources
SOURCES += \
    antigravity-hub_tests.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp \
    ../src/iconprovider.cpp

exists(../src/models.cpp):  SOURCES += ../src/models.cpp
exists(../src/backend.cpp): SOURCES += ../src/backend.cpp

# Validate resource embedding in tests
RESOURCES += ../src/resources.qrc
