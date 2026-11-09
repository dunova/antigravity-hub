QT += core gui quick quickcontrols2 testlib dbus network svg

CONFIG += c++17 testcase
CONFIG -= debug
TARGET = m2_adversarial_challenger
TEMPLATE = app

QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

INCLUDEPATH += ../src
DEPENDPATH += ../src

HEADERS += \
    ../src/theme.h \
    ../src/translator.h \
    ../src/models.h \
    ../src/backend.h \
    ../src/iconprovider.h

SOURCES += \
    m2_adversarial_challenger.cpp \
    ../src/theme.cpp \
    ../src/translator.cpp \
    ../src/models.cpp \
    ../src/backend.cpp \
    ../src/iconprovider.cpp

RESOURCES += ../src/resources.qrc
