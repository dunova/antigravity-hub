import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root

    modal: true
    focus: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    x: Math.round(((parent ? parent.width : 640) - width) / 2)
    y: Math.round(((parent ? parent.height : 640) - height) / 2)
    width: Math.min(parent ? parent.width - 40 : 640, 620)

    function toggle() {
        if (visible) close();
        else open();
    }

    background: Rectangle {
        color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
        radius: 0
        border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
        border.width: 1

        Rectangle {
            anchors.fill: parent
            radius: 0
            color: "transparent"
            border.color: "#0affffff"
            border.width: 1
        }
    }

    Overlay.modal: Rectangle {
        color: "#b3000000"
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }

    contentItem: ColumnLayout {
        spacing: 16

        // Header
        RowLayout {
            Layout.fillWidth: true

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: qsTr("Keyboard Shortcuts")
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                }

                Text {
                    text: qsTr("Quick reference for keyboard navigation and actions")
                    font.pixelSize: 11
                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                }
            }

            Button {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                flat: true
                background: Rectangle {
                    color: parent.hovered ? "#14ffffff" : "transparent"
                    radius: 0
                }
                contentItem: AppIcon {
                    name: "close"
                    size: 13
                    tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                }
                onClicked: root.close()
            }
        }

        // Horizontal Separator
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
            radius: 0
        }

        // Two-Column Cheatsheet Body
        RowLayout {
            Layout.fillWidth: true
            spacing: 24

            // Left Column: Navigation
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 10

                Text {
                    text: qsTr("Navigation")
                    font.pixelSize: 11
                    font.weight: Font.Bold
                    font.capitalization: Font.AllUppercase
                    color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                    Layout.bottomMargin: 2
                }

                Repeater {
                    model: [
                        { keys: ["j", "↓"], desc: qsTr("Next account") },
                        { keys: ["k", "↑"], desc: qsTr("Previous account") },
                        { keys: ["Enter"], desc: qsTr("Switch to account") },
                        { keys: ["/"], desc: qsTr("Focus search") },
                        { keys: ["Esc"], desc: qsTr("Close / Cancel") }
                    ]
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Row {
                            spacing: 4
                            Repeater {
                                model: modelData.keys
                                delegate: Rectangle {
                                    width: Math.max(kTxt.implicitWidth + 12, 26)
                                    height: 24
                                    radius: 0
                                    color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    border.width: 1

                                    Text {
                                        id: kTxt
                                        anchors.centerIn: parent
                                        text: modelData
                                        font.pixelSize: 11
                                        font.family: (theme && theme.uiFont) ? theme.uiFont : "Monospace"
                                        font.weight: Font.DemiBold
                                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.desc
                            font.pixelSize: 12
                            color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // Vertical Divider
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredHeight: 180
                width: 1
                color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                radius: 0
            }

            // Right Column: Actions
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 10

                Text {
                    text: qsTr("Actions")
                    font.pixelSize: 11
                    font.weight: Font.Bold
                    font.capitalization: Font.AllUppercase
                    color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                    Layout.bottomMargin: 2
                }

                Repeater {
                    model: [
                        { keys: ["m"], desc: qsTr("Toggle masking") },
                        { keys: ["r"], desc: qsTr("Refresh quotas") },
                        { keys: ["s"], desc: qsTr("Open settings") },
                        { keys: ["g"], desc: qsTr("Switch to TopG") },
                        { keys: ["w"], desc: qsTr("Fleet prewarm") },
                        { keys: ["?", "F1"], desc: qsTr("Help overlay") }
                    ]
                    delegate: RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        Row {
                            spacing: 4
                            Repeater {
                                model: modelData.keys
                                delegate: Rectangle {
                                    width: Math.max(kTxt2.implicitWidth + 12, 26)
                                    height: 24
                                    radius: 0
                                    color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    border.width: 1

                                    Text {
                                        id: kTxt2
                                        anchors.centerIn: parent
                                        text: modelData
                                        font.pixelSize: 11
                                        font.family: (theme && theme.uiFont) ? theme.uiFont : "Monospace"
                                        font.weight: Font.DemiBold
                                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                                    }
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData.desc
                            font.pixelSize: 12
                            color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        // Bottom Hint
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
            radius: 0
        }

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: qsTr("Press Esc or ? to close")
            font.pixelSize: 11
            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
        }
    }
}
