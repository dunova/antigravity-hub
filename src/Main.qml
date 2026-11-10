import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: appWindow
    visible: true
    // 最佳默认宽度与内容锁定（内容 896 + 外边距 24 = 920），完美适配系统动态平铺分屏与极简防截断
    readonly property int contentWidth: 896
    width: 940
    minimumWidth: 920
    height: 800
    minimumHeight: 540
    title: qsTr("Antigravity Hub")

    // Dynamic Omarchy Design System & Typography
    color: (theme && theme.canvas) ? theme.canvas : ((theme && theme.background) ? theme.background : "#142620")
    font.family: (theme && theme.uiFont) ? theme.uiFont : "sans-serif"
    Material.theme: (theme && theme.mode === "light") ? Material.Light : Material.Dark
    Material.accent: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#7daea3"
    Material.background: (theme && theme.background && theme.background.charAt(0) === '#') ? theme.background : "#142620"
    Material.foreground: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
    Material.roundedScale: theme ? theme.controlRadius : 4

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

    // PgUp / PgDn -> 翻页（每页 15 个）
    Shortcut {
        sequence: "PgDown"
        enabled: !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: accountListView.gotoPage(accountListView.currentPage + 1)
    }
    Shortcut {
        sequence: "PgUp"
        enabled: !appWindow.isModalOpen
        context: Qt.ApplicationShortcut
        onActivated: accountListView.gotoPage(accountListView.currentPage - 1)
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

        ScrollView {
            id: mainScrollView
            anchors.fill: parent
            contentWidth: Math.max(rootContainer.width, appWindow.contentWidth + 24)
            contentHeight: rootContainer.height
            clip: true
            ScrollBar.horizontal.policy: (rootContainer.width < appWindow.contentWidth + 24) ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.leftMargin: Math.max(12, Math.round((mainScrollView.contentWidth - width) / 2))
                anchors.topMargin: 12
                anchors.bottomMargin: 12
                width: Math.max(appWindow.contentWidth, rootContainer.width - 24)
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
                    Layout.preferredHeight: 34
                }

                // 3. Account Quota Matrix Table View
                AccountListView {
                    id: accountListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                }
            }
        }

        // =====================================================================
        // MODALS & OVERLAYS
        // =====================================================================

        // Settings Dialog Modal
        SettingsDialog {
            id: settingsDialog
            objectName: "settingsDialog"
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
            radius: 0
            height: 38
            implicitWidth: toastContentRow.implicitWidth + 28
            color: isErrorToast ?
                   Qt.alpha((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B", 0.15) :
                   Qt.alpha((theme && theme.goodText) ? theme.goodText : "#4ADE80", 0.15)
            border.color: isErrorToast ?
                          ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                          ((theme && theme.goodText) ? theme.goodText : "#4ADE80")
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
                    tint: toastNotification.isErrorToast ?
                          ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                          ((theme && theme.goodText) ? theme.goodText : "#4ADE80")
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
