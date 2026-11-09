QT += core gui quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = stress_m2
TEMPLATE = app

# Strict compiler hygiene & warning flags
QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h \
    ../src/translator.h \
    ../src/models.h \
    ../src/backend.h

SOURCES += \
    stress_m2.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp \
    ../src/models.cpp \
    ../src/backend.cpp

RESOURCES += ../src/resources.qrc
