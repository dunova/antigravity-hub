QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = stress_challenge
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h \
    ../src/translator.h \
    ../src/models.h \
    ../src/backend.h

SOURCES += \
    stress_challenge.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp \
    ../src/models.cpp \
    ../src/backend.cpp

RESOURCES += ../src/resources.qrc
