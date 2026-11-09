import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: appWindow
    visible: true
    width: 1080
    height: 720
    minimumWidth: 880
    minimumHeight: 540
    title: qsTr("Antigravity Hub")

    // Dynamic Material Dark/Light Theme following Omarchy & Hyprland
    color: (theme && theme.background && theme.background.charAt(0) === '#') ? theme.background : "#142620"
    Material.theme: (theme && theme.mode === "light") ? Material.Light : Material.Dark
    Material.accent: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
    Material.background: (theme && theme.background && theme.background.charAt(0) === '#') ? theme.background : "#142620"
    Material.foreground: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#f0faf4"
    Material.roundedScale: theme ? theme.radius : 0

    // Focus guard: prevents single-character shortcuts from intercepting text input
    property bool isInputFocused: {
        var item = appWindow.activeFocusItem;
        return item !== null &&
               ("cursorPosition" in item) &&
               !item.readOnly;
    }

    // Modal guard: suppresses background shortcuts when a modal dialog or popup is active
    property bool isModalOpen: (helpOverlay && helpOverlay.visible) ||
                               (settingsDialog && settingsDialog.visible)

    // =========================================================================
    // GLOBAL KEYBOARD SHORTCUT DISPATCH
    // =========================================================================

    // / -> Focus Search Bar
    Shortcut {
        sequence: "/"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (filterBar && typeof filterBar.focusSearch === "function") {
                filterBar.focusSearch();
            }
        }
    }

    // j / Down -> Navigate to Next Row
    Shortcut {
        sequences: ["j", "Down"]
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (accountListView && typeof accountListView.selectNext === "function") {
                accountListView.selectNext();
            }
        }
    }

    // k / Up -> Navigate to Previous Row
    Shortcut {
        sequences: ["k", "Up"]
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (accountListView && typeof accountListView.selectPrevious === "function") {
                accountListView.selectPrevious();
            }
        }
    }

    // Enter / Return -> Switch to Selected Account
    Shortcut {
        sequences: ["Return", "Enter"]
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (accountListView && typeof accountListView.activateCurrent === "function") {
                accountListView.activateCurrent();
            }
        }
    }

    // m / M -> Toggle Sensitive Handle Masking
    Shortcut {
        sequence: "m"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (backend) backend.masked = !backend.masked;
        }
    }

    // r / R -> Asynchronously Refresh All Quotas
    Shortcut {
        sequence: "r"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (backend) backend.refreshQuota(true);
        }
    }

    // s / S -> Open Preferences / Settings Dialog
    Shortcut {
        sequence: "s"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (settingsDialog && typeof settingsDialog.open === "function") {
                settingsDialog.open();
            }
        }
    }

    // g / G -> TopG Auto-Switch
    Shortcut {
        sequence: "g"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (backend) backend.switchTopGemini();
        }
    }

    // w / W -> Prewarm Fleet
    Shortcut {
        sequence: "w"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: {
            if (backend) backend.triggerPrewarm();
        }
    }

    // ? & Shift+/ & F1 -> Show Keyboard Shortcut Help Overlay
    Shortcut {
        sequences: ["?", "Shift+/", "F1"]
        enabled: !appWindow.isInputFocused && !(settingsDialog && settingsDialog.visible)
        context: Qt.ApplicationShortcut
        onActivated: {
            if (helpOverlay) {
                if (typeof helpOverlay.toggle === "function") {
                    helpOverlay.toggle();
                } else if (typeof helpOverlay.open === "function") {
                    if (helpOverlay.visible) helpOverlay.close();
                    else helpOverlay.open();
                }
            }
        }
    }

    // q / Q -> Clean Application Quit
    Shortcut {
        sequence: "q"
        enabled: !appWindow.isInputFocused && !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: Qt.quit()
    }

    // Esc -> Unfocus Search / Dismiss Dialogs
    Shortcut {
        sequence: "Escape"
        context: Qt.ApplicationShortcut
        onActivated: {
            if (helpOverlay && helpOverlay.visible && typeof helpOverlay.close === "function") {
                helpOverlay.close();
            } else if (settingsDialog && settingsDialog.visible && typeof settingsDialog.close === "function") {
                settingsDialog.close();
            } else if (filterBar && typeof filterBar.clearOrUnfocus === "function") {
                filterBar.clearOrUnfocus();
            }
        }
    }

    // =========================================================================
    // ROOT MIRRORED CONTAINER (RTL Internationalization Support)
    // =========================================================================
    Item {
        id: rootContainer
        anchors.fill: parent
        LayoutMirroring.enabled: Qt.application.layoutDirection === Qt.RightToLeft
        LayoutMirroring.childrenInherit: true

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            // 1. Header Bar
            HeaderBar {
                id: headerBar
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                onOpenSettings: {
                    if (settingsDialog && typeof settingsDialog.open === "function") {
                        settingsDialog.open();
                    }
                }
            }

            // 2. Control & Filter Bar
            FilterBar {
                id: filterBar
                Layout.fillWidth: true
                Layout.preferredHeight: 42
            }

            // 3. Account Quota Matrix Table View
            AccountListView {
                id: accountListView
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // =====================================================================
        // MODALS & OVERLAYS
        // =====================================================================

        // Settings Dialog Modal
        SettingsDialog {
            id: settingsDialog
            anchors.centerIn: parent
        }

        // Shortcut Help Overlay
        HelpOverlay {
            id: helpOverlay
            anchors.centerIn: parent
        }

        // Floating Toast Notification
        Rectangle {
            id: toastNotification
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 24
            z: 999
            visible: opacity > 0
            opacity: 0.0
            radius: Math.max((theme ? theme.radius : 0) - 2, 6)
            height: 38
            implicitWidth: toastContentRow.implicitWidth + 28
            color: isErrorToast ? "#26EF4444" : "#2622C55E"
            border.color: isErrorToast ? "#EF4444" : "#22C55E"
            border.width: 1

            property bool isErrorToast: false
            property string toastTitle: ""
            property string toastMessage: ""

            RowLayout {
                id: toastContentRow
                anchors.centerIn: parent
                spacing: 8

                AppIcon {
                    name: toastNotification.isErrorToast ? "warning" : "check"
                    size: 14
                    tint: toastNotification.isErrorToast ? "#EF4444" : "#22C55E"
                }

                Text {
                    text: {
                        if (toastNotification.toastTitle.length > 0) {
                            return toastNotification.toastTitle + ": " + toastNotification.toastMessage;
                        }
                        return toastNotification.toastMessage;
                    }
                    font.pixelSize: 12
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#dfede5"
                }
            }

            Timer {
                id: toastTimer
                interval: 3200
                onTriggered: toastFadeOut.start()
            }

            NumberAnimation {
                id: toastFadeIn
                target: toastNotification
                property: "opacity"
                from: 0.0; to: 1.0; duration: 180
                easing.type: Easing.OutCubic
            }
            NumberAnimation {
                id: toastFadeOut
                target: toastNotification
                property: "opacity"
                from: 1.0; to: 0.0; duration: 250
                easing.type: Easing.InCubic
            }

            function show(title, msg, isErr) {
                toastTitle = title || "";
                toastMessage = msg || "";
                isErrorToast = !!isErr;
                toastTimer.stop();
                toastFadeIn.start();
                toastTimer.start();
            }
        }

        // Backend Signal Connections for UI Notifications
        Connections {
            target: backend
            ignoreUnknownSignals: true
            function onNotificationRequested(title, message, isError) {
                toastNotification.show(title, message, isError);
            }
            function onOperationCompleted(operation, success, message) {
                toastNotification.show(operation, message, !success);
            }
        }
    }
}
