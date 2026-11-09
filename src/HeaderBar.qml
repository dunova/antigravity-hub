import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls.impl 2.15

Rectangle {
    id: headerBarRoot
    height: 48
    radius: theme ? theme.panelRadius : 8
    border.color: (theme && theme.hairline) ? theme.hairline : "rgba(255, 255, 255, 0.12)"
    border.width: 1
    gradient: Gradient {
        GradientStop { position: 0; color: (theme && theme.surfaceTop) ? theme.surfaceTop : "#172c25" }
        GradientStop { position: 1; color: (theme && theme.surfaceBottom) ? theme.surfaceBottom : "#11201b" }
    }

    signal openSettings()

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 10

        // =====================================================================
        // LEFT GROUP: Logo + Title + ACTIVE Account Badge + Version Tag
        // =====================================================================

        // 1. Dynamic Accent Monochrome Logo
        IconImage {
            id: logoIcon
            source: "qrc:/assets/logo.svg"
            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A"
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
            font.bold: true
            font.pixelSize: 15
            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#dfede5"
            Layout.alignment: Qt.AlignVCenter
        }

        // 3. Current ACTIVE Account Highlight Badge (Static, no blinking animation)
        Rectangle {
            id: activeBadge
            height: 28
            implicitWidth: activeContentRow.implicitWidth + 16
            radius: Math.max((theme ? theme.radius : 0) - 4, 4)
            Layout.alignment: Qt.AlignVCenter

            // Adaptive coloring based on manual protection lock
            color: (backend && backend.isManualLocked) ?
                   Qt.alpha((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B", 0.15) :
                   Qt.alpha((theme && theme.goodText) ? theme.goodText : "#4ADE80", 0.15)
            border.color: (backend && backend.isManualLocked) ?
                          ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                          ((theme && theme.goodText) ? theme.goodText : "#4ADE80")
            border.width: 1

            RowLayout {
                id: activeContentRow
                anchors.centerIn: parent
                spacing: 6

                // Static Solid Indicator Dot (No blinking/breathing)
                Rectangle {
                    id: breathingDot
                    width: 8
                    height: 8
                    radius: 4
                    color: (backend && backend.isManualLocked) ?
                           ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                           ((theme && theme.goodText) ? theme.goodText : "#4ADE80")
                }

                // Badge Status Tag
                Text {
                    text: {
                        if (backend && backend.isManualLocked) {
                            var mins = Math.ceil(backend.manualLockRemaining / 60);
                            return qsTr("Manual Protection") + (mins > 0 ? (" " + mins + "m") : "");
                        }
                        if (backend && backend.activeEmail && backend.activeEmail.length > 0) {
                            return qsTr("ACTIVE");
                        }
                        return qsTr("Not Active");
                    }
                    font.bold: true
                    font.pixelSize: 11
                    color: (backend && backend.isManualLocked) ?
                           ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                           ((theme && theme.goodText) ? theme.goodText : "#4ADE80")
                }

                // Active Account Handle (Masked if masking enabled)
                Text {
                    text: {
                        var isM = (accountModel && accountModel.isMasked);
                        var rawEmail = backend ? backend.activeEmail : "";
                        if (!rawEmail || rawEmail.length === 0) return qsTr("None");
                        var atIdx = rawEmail.indexOf('@');
                        var uname = (atIdx > 0) ? rawEmail.substring(0, atIdx) : rawEmail;
                        if (isM && accountModel) {
                            return accountModel.maskName(uname);
                        }
                        return uname;
                    }
                    font.pixelSize: 12
                    font.bold: true
                    font.family: "Monospace"
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    elide: Text.ElideRight
                    Layout.maximumWidth: 180
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
                    return qsTr("Current active account") + (backend ? (": " + backend.activeEmail) : "");
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
            radius: 4
            color: "#0dffffff"
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
            border.width: 1
            Layout.alignment: Qt.AlignVCenter

            Text {
                id: verText
                anchors.centerIn: parent
                text: qsTr("v%1").arg("2.48.0")
                font.family: "Monospace"
                font.pixelSize: 11
                color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#64887b"
            }
        }

        // Elastic Spacer pushing action capsules to the right
        Item {
            Layout.fillWidth: true
        }

        // =====================================================================
        // RIGHT GROUP: 5 Action Capsules
        // =====================================================================

        // 1. Mask Capsule (打码/明文)
        Rectangle {
            id: maskCapsule
            height: 30
            implicitWidth: maskText.implicitWidth + 22
            radius: theme ? theme.controlRadius : 6
            Layout.alignment: Qt.AlignVCenter

            color: (backend && backend.masked) ?
                   ((theme && theme.selection && theme.selection.charAt(0) === '#') ? theme.selection : "#2b5147") :
                   (maskMouse.containsMouse ?
                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                       ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26"))
            border.color: (backend && backend.masked) ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")
            border.width: 1

            Text {
                id: maskText
                anchors.centerIn: parent
                text: (backend && backend.masked) ? qsTr("Unmask") : qsTr("Mask")
                font.pixelSize: 12
                font.bold: true
                color: (backend && backend.masked) ?
                       ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                       ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
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
            implicitWidth: settText.implicitWidth + 24
            radius: theme ? theme.controlRadius : 6
            Layout.alignment: Qt.AlignVCenter

            color: settMouse.containsMouse ?
                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#203b31") :
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#142620")
            border.color: settMouse.containsMouse ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")
            border.width: 1

            Text {
                id: settText
                anchors.centerIn: parent
                text: qsTr("Settings")
                font.pixelSize: 12
                font.bold: true
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
            implicitWidth: topgText.implicitWidth + 24
            radius: theme ? theme.controlRadius : 6
            Layout.alignment: Qt.AlignVCenter

            color: topgMouse.containsMouse ?
                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#203b31") :
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#142620")
            border.color: topgMouse.containsMouse ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")
            border.width: 1

            Text {
                id: topgText
                anchors.centerIn: parent
                text: "TopG"
                font.pixelSize: 12
                font.bold: true
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
            implicitWidth: geminiText.implicitWidth + 22
            radius: theme ? theme.controlRadius : 6
            Layout.alignment: Qt.AlignVCenter

            property string currentMode: backend ? backend.rotationMode : "gemini"

            color: rotMouse.containsMouse ?
                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26")
            border.color: {
                if (currentMode === "gemini") return (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1";
                if (currentMode === "claude") return "#bb9af7";
                return (theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)";
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
                font.pixelSize: 12
                font.bold: true
                color: {
                    if (rotationCapsule.currentMode === "gemini") return (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1";
                    if (rotationCapsule.currentMode === "claude") return "#bb9af7";
                    return (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#64887b";
                }
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
            implicitWidth: prewarmRow.implicitWidth + 24
            radius: theme ? theme.controlRadius : 6
            Layout.alignment: Qt.AlignVCenter

            color: prewarmMouse.containsMouse ?
                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26")
            border.color: (backend && backend.busy) ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          (prewarmMouse.containsMouse ?
                              ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                              ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)"))
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
                    font.pixelSize: 12
                    font.bold: true
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
