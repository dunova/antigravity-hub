import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls.impl 2.15

Rectangle {
    id: headerBarRoot
    height: 48
    radius: 0
    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
    border.width: 1
    color: (theme && theme.mode === "light") ?
           ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#FFFFFF") :
           ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c")

    signal openSettings()
    signal openAddAccount()

    readonly property string currentActiveEmail: (accountModel && accountModel.activeEmail && accountModel.activeEmail.length > 0) ?
                                                 accountModel.activeEmail :
                                                 (backend ? backend.activeEmail : "")

    AddAccountDialog {
        id: addAccountDialog
        objectName: "addAccountDialog"
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 7

        // =====================================================================
        // LEFT GROUP: Logo + Title + ACTIVE Account Badge + Version Tag
        // =====================================================================

        // 1. Dynamic Accent Monochrome Logo
        IconImage {
            id: logoIcon
            source: "qrc:/assets/logo.svg"
            color: (theme && theme.accent) ? theme.accent : "#7daea3"
            width: 24
            height: 24
            sourceSize: Qt.size(24, 24)
            Layout.alignment: Qt.AlignVCenter

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Antigravity Hub")
                onClicked: {
                    if (backend) backend.refreshQuota(false);
                }
            }
        }

        // 2. Application Title
        Text {
            id: titleLabel
            text: qsTr("Antigravity Hub")
            font.family: theme.uiFont
            font.weight: Font.DemiBold
            font.pixelSize: 15
            renderType: Text.NativeRendering
            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#dfede5"
            Layout.alignment: Qt.AlignVCenter
        }

        // 3. Current ACTIVE Account Highlight Badge (Static, no blinking animation)
        Rectangle {
            id: activeBadge
            height: 28
            implicitWidth: activeContentRow.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            readonly property color lockColor: (theme && theme.mode === "light") ? "#D97706" : "#F59E0B"
            readonly property color activeColor: (theme && theme.accent) ? theme.accent : "#7daea3"

            // Adaptive coloring: warm amber for manual lock, crisp accent for active
            color: (backend && backend.isManualLocked) ?
                   Qt.alpha(lockColor, 0.15) :
                   Qt.alpha(activeColor, 0.15)
            border.color: (backend && backend.isManualLocked) ? lockColor : activeColor
            border.width: 1

            RowLayout {
                id: activeContentRow
                anchors.centerIn: parent
                spacing: 5

                // Static Solid Indicator Dot (No blinking/breathing)
                Rectangle {
                    id: breathingDot
                    width: 6
                    height: 6
                    radius: 0
                    color: (backend && backend.isManualLocked) ? activeBadge.lockColor : activeBadge.activeColor
                }

                // Badge Status Tag
                Text {
                    text: {
                        if (backend && backend.isManualLocked) {
                            var mins = Math.ceil(backend.manualLockRemaining / 60);
                            return qsTr("🔒 %1m").arg(mins > 0 ? mins : 1);
                        }
                        if (headerBarRoot.currentActiveEmail && headerBarRoot.currentActiveEmail.length > 0) {
                            return qsTr("ACTIVE");
                        }
                        return qsTr("Not Active");
                    }
                    font.weight: Font.DemiBold
                    font.pixelSize: 11
                    renderType: Text.NativeRendering
                    color: (backend && backend.isManualLocked) ?
                           activeBadge.lockColor :
                           ((theme && theme.accentText) ? theme.accentText : activeBadge.activeColor)
                }

                // Active Account Handle (Masked if masking enabled)
                Text {
                    text: {
                        var isM = (accountModel && accountModel.isMasked);
                        var rawEmail = headerBarRoot.currentActiveEmail;
                        if (!rawEmail || rawEmail.length === 0) return qsTr("None");
                        var atIdx = rawEmail.indexOf('@');
                        var uname = (atIdx > 0) ? rawEmail.substring(0, atIdx) : rawEmail;
                        if (isM && accountModel) {
                            return accountModel.maskName(uname);
                        }
                        return uname;
                    }
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    font.family: theme.monoFont
                    renderType: Text.NativeRendering
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    elide: Text.ElideRight
                    Layout.maximumWidth: 130
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: (backend && backend.isManualLocked) ? Qt.PointingHandCursor : Qt.ArrowCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: {
                    if (backend && backend.isManualLocked) {
                        return qsTr("Unlock Protection");
                    }
                    return qsTr("Current active account") + (headerBarRoot.currentActiveEmail ? (": " + headerBarRoot.currentActiveEmail) : "");
                }
                onClicked: {
                    if (backend && backend.isManualLocked) {
                        backend.unlockManualOverride();
                    }
                }
            }
        }

        // 4. Semantic Version Tag
        Rectangle {
            id: versionBadge
            height: 22
            implicitWidth: verText.implicitWidth + 12
            radius: 0
            color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : ((theme && theme.surface2) ? theme.surface2 : "#1a2c26")
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
            border.width: 1
            Layout.alignment: Qt.AlignVCenter

            Text {
                id: verText
                anchors.centerIn: parent
                text: qsTr("v%1").arg("2.51.6")
                font.family: theme.monoFont
                font.pixelSize: 11
                renderType: Text.NativeRendering
                color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#64887b"
            }
        }

        // Elastic Spacer pushing action capsules to the right
        Item {
            Layout.fillWidth: true
        }

        // =====================================================================
        // RIGHT GROUP: 6 Action Capsules
        // =====================================================================

        // 0. Add Account Capsule (+ 添加账户)
        Rectangle {
            id: addAccountCapsule
            height: 30
            implicitWidth: addAccountRow.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            color: addAccountMouse.containsMouse ?
                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                   Qt.alpha((theme && theme.accent) ? theme.accent : "#7daea3", 0.16)
            border.color: (theme && theme.accent) ? theme.accent : "#7daea3"
            border.width: 1

            RowLayout {
                id: addAccountRow
                anchors.centerIn: parent
                spacing: 6

                Text {
                    id: addAccountLabel
                    text: qsTr("+ Add Account")
                    font.family: theme.uiFont
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    renderType: Text.NativeRendering
                    color: (theme && theme.accentText) ? theme.accentText : ((theme && theme.text1) ? theme.text1 : "#FFFFFF")
                }
            }

            MouseArea {
                id: addAccountMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Import accounts or sync from keychain")
                onClicked: {
                    headerBarRoot.openAddAccount();
                    addAccountDialog.open();
                }
            }
        }

        // 1. Mask Capsule (打码/明文)
        Rectangle {
            id: maskCapsule
            height: 30
            implicitWidth: maskText.implicitWidth + 16
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            color: (backend && backend.masked) ?
                   ((theme && theme.selection && theme.selection.charAt(0) === '#') ? theme.selection : "#2b5147") :
                   (maskMouse.containsMouse ?
                       ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                       ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c"))
            border.color: (backend && backend.masked) ?
                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff")
            border.width: 1

            Text {
                id: maskText
                anchors.centerIn: parent
                text: (backend && backend.masked) ? qsTr("Unmask") : qsTr("Mask")
                font.family: theme.uiFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
            }

            MouseArea {
                id: maskMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Toggle masking (M)")
                onClicked: {
                    if (backend) backend.masked = !backend.masked;
                }
            }
        }

        // 2. Settings Capsule (设置 - 纯文本跟随系统)
        Rectangle {
            id: settingsCapsule
            height: 30
            implicitWidth: settText.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            color: settMouse.containsMouse ?
                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                   ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c")
            border.color: settMouse.containsMouse ?
                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff")
            border.width: 1

            Text {
                id: settText
                anchors.centerIn: parent
                text: qsTr("Settings")
                font.family: theme.uiFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
            }

            MouseArea {
                id: settMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Console settings (S)")
                onClicked: headerBarRoot.openSettings()
            }
        }

        // 3. TopG Capsule (纯文本跟随系统，无小图标)
        Rectangle {
            id: topgCapsule
            height: 30
            implicitWidth: topgText.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            color: topgMouse.containsMouse ?
                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                   ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c")
            border.color: topgMouse.containsMouse ?
                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff")
            border.width: 1

            Text {
                id: topgText
                anchors.centerIn: parent
                text: "TopG"
                font.family: theme.uiFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
            }

            MouseArea {
                id: topgMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Switch to top Gemini account (G)")
                onClicked: {
                    if (backend) backend.switchTopGemini();
                }
            }
        }

        // 4. Gemini Rotation Mode Capsule
        Rectangle {
            id: rotationCapsule
            height: 30
            implicitWidth: geminiText.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            property string currentMode: backend ? backend.rotationMode : "gemini"

            color: rotMouse.containsMouse ?
                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                   ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c")
            border.color: {
                if (currentMode === "gemini") return (theme && theme.accent) ? theme.accent : "#7daea3";
                if (currentMode === "claude") return "#bb9af7";
                return (theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff";
            }
            border.width: 1

            Text {
                id: geminiText
                anchors.centerIn: parent
                text: {
                    if (rotationCapsule.currentMode === "gemini") return qsTr("Gemini");
                    if (rotationCapsule.currentMode === "claude") return qsTr("Claude");
                    return qsTr("Off");
                }
                font.family: theme.uiFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
                color: (rotationCapsule.currentMode === "gemini") ?
                       ((theme && theme.accentText) ? theme.accentText : ((theme && theme.text1) ? theme.text1 : "#FFFFFF")) :
                       ((theme && theme.text1) ? theme.text1 : "#FFFFFF")
            }

            MouseArea {
                id: rotMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Auto-rotation mode: %1").arg(rotationCapsule.currentMode)
                onClicked: {
                    if (backend) backend.toggleRotation();
                }
            }
        }

        // 5. Prewarm Capsule (预热 - 纯文本跟随系统，无小图标)
        Rectangle {
            id: prewarmCapsule
            height: 30
            implicitWidth: prewarmRow.implicitWidth + 14
            radius: 0
            Layout.alignment: Qt.AlignVCenter

            color: prewarmMouse.containsMouse ?
                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                   ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c")
            border.color: (backend && backend.busy) ?
                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                          (prewarmMouse.containsMouse ?
                              ((theme && theme.accent) ? theme.accent : "#7daea3") :
                              ((theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff"))
            border.width: 1

            RowLayout {
                id: prewarmRow
                anchors.centerIn: parent
                spacing: 6

                BusyIndicator {
                    width: 14
                    height: 14
                    running: backend ? backend.busy : false
                    visible: backend ? backend.busy : false
                }

                Text {
                    id: prewarmLabel
                    text: qsTr("Prewarm")
                    font.family: theme.uiFont
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    renderType: Text.NativeRendering
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                }
            }

            MouseArea {
                id: prewarmMouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                ToolTip.visible: containsMouse
                ToolTip.text: qsTr("Prewarm fleet (W)")
                onClicked: {
                    if (backend) backend.triggerPrewarm();
                }
            }
        }
    }
}
