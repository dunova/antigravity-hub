QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = challenger2_m1_iter2_stress
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer
QMAKE_LFLAGS += -fsanitize=address,undefined

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h

SOURCES += \
    challenger2_m1_iter2_stress.cpp \
    ../src/theme.cpp

RESOURCES += ../src/resources.qrc
