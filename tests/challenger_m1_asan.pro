QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = challenger_m1_asan
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer -fPIC
QMAKE_LFLAGS += -fsanitize=address,undefined

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h

SOURCES += \
    challenger_m1_adversarial_tests.cpp \
    ../src/theme.cpp

RESOURCES += ../src/resources.qrc
