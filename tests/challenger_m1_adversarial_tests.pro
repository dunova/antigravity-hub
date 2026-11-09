QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = challenger_m1_adversarial_tests
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h

SOURCES += \
    challenger_m1_adversarial_tests.cpp \
    ../src/theme.cpp

RESOURCES += ../src/resources.qrc
