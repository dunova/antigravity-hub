QT += core gui qml quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = m5_challenger_e2e_test
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
    m5_challenger_e2e_test.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp \
    ../src/models.cpp \
    ../src/backend.cpp

RESOURCES += ../src/resources.qrc
