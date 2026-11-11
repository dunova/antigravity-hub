# ==============================================================================
# Antigravity Hub — Native Omarchy Desktop Application Project File
# Architecture: C++17 + Qt Quick Controls 2 (Material Dark) + Flat src/ layout
# ==============================================================================

QT += core gui qml quick quickcontrols2 dbus network svg

CONFIG += c++17 release
CONFIG -= debug
TARGET = antigravity-hub
VERSION = 3.0.6
TEMPLATE = app

# Strict compiler hygiene & warning flags
QMAKE_CXXFLAGS += -Wall -Wextra -Wpedantic

# Flat directory inclusion
INCLUDEPATH += src
DEPENDPATH += src

# Headers
HEADERS += \
    src/theme.h \
    src/translator.h \
    src/iconprovider.h

exists(src/backend.h): HEADERS += src/backend.h
exists(src/models.h):  HEADERS += src/models.h

# Sources
SOURCES += \
    src/theme.cpp \
    src/translator.cpp \
    src/iconprovider.cpp

exists(src/main.cpp):    SOURCES += src/main.cpp
exists(src/backend.cpp): SOURCES += src/backend.cpp
exists(src/models.cpp):  SOURCES += src/models.cpp

# Embedded resource bundling (QML, Assets, i18n JSONs)
RESOURCES += src/resources.qrc

# Standard Linux / Arch XDG Installation Targets
isEmpty(PREFIX) {
    PREFIX = /usr
}

target.path = $$PREFIX/bin

desktop.path = $$PREFIX/share/applications
desktop.files = pkgbuild/antigravity-hub.desktop

icon.path = $$PREFIX/share/icons/hicolor/scalable/apps
icon.files = pkgbuild/antigravity-hub.svg

INSTALLS += target desktop icon
