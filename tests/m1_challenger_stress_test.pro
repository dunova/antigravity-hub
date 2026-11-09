QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = m1_challenger_stress_test
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h \
    ../src/translator.h

SOURCES += \
    m1_challenger_stress_test.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp

RESOURCES += ../src/resources.qrc
