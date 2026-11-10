import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: root
    modal: true
    focus: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: Overlay.overlay
    width: 480
    header: null
    footer: null

    property bool isJsonInputExpanded: false

    background: Rectangle {
        color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620"
        border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
        border.width: 1
        radius: 0
    }

    Overlay.modal: Rectangle {
        color: "#a6000000"
    }

    contentItem: ColumnLayout {
        spacing: 14

        // 1. 弹窗顶栏
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: qsTr("添加新账户")
                font.pixelSize: 15
                font.weight: Font.DemiBold
                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                Layout.fillWidth: true
            }

            Rectangle {
                width: 24
                height: 24
                radius: 0
                color: closeMouse.containsMouse ?
                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") : "transparent"

                AppIcon {
                    anchors.centerIn: parent
                    name: "close"
                    size: 12
                    tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                }

                MouseArea {
                    id: closeMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: root.close()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
            radius: 0
        }

        // 2. 选项 1: 一键吸纳当前系统凭据
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 56
            radius: 0
            color: opt1Mouse.containsMouse ?
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26") :
                   ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620")
            border.width: 1
            border.color: opt1Mouse.containsMouse ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff")

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 12

                AppIcon {
                    name: "shield"
                    size: 18
                    tint: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: qsTr("一键吸纳当前系统凭据")
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                    Text {
                        text: qsTr("从系统钥匙串/IDE 现存登录缓存中直接导入活跃 Google 凭据")
                        font.pixelSize: 11
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                    }
                }
            }

            MouseArea {
                id: opt1Mouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: {
                    if (backend && typeof backend.ingestActiveAccount === "function") {
                        backend.ingestActiveAccount();
                    }
                    root.close();
                }
            }
        }

        // 3. 选项 2: 浏览器授权登录添加
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 56
            radius: 0
            color: opt2Mouse.containsMouse ?
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26") :
                   ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620")
            border.width: 1
            border.color: opt2Mouse.containsMouse ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff")

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 12

                AppIcon {
                    name: "bolt"
                    size: 18
                    tint: (theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: qsTr("浏览器授权登录添加")
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                    Text {
                        text: qsTr("启动系统默认浏览器完成 Google OAuth 授权接管")
                        font.pixelSize: 11
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                    }
                }
            }

            MouseArea {
                id: opt2Mouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: {
                    if (backend && typeof backend.startOAuthLogin === "function") {
                        backend.startOAuthLogin();
                    }
                    root.close();
                }
            }
        }

        // 4. 选项 3: 导入 JSON 凭据备份
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 56
            radius: 0
            color: opt3Mouse.containsMouse ?
                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26") :
                   ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620")
            border.width: 1
            border.color: (root.isJsonInputExpanded || opt3Mouse.containsMouse) ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                          ((theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff")

            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 12

                AppIcon {
                    name: "clipboard"
                    size: 18
                    tint: (theme && theme.warningText && theme.warningText.charAt(0) === '#') ? theme.warningText : "#ffc27a"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    Text {
                        text: qsTr("导入 JSON 凭据备份")
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                    Text {
                        text: qsTr("粘贴来自其他 Hub 实例或备份文件的 JSON 凭据文本")
                        font.pixelSize: 11
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                    }
                }

                Text {
                    text: root.isJsonInputExpanded ? "▲" : "▼"
                    font.pixelSize: 11
                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                }
            }

            MouseArea {
                id: opt3Mouse
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                hoverEnabled: true
                onClicked: root.isJsonInputExpanded = !root.isJsonInputExpanded
            }
        }

        // 5. 展开的 JSON 粘贴与导入面板
        ColumnLayout {
            visible: root.isJsonInputExpanded
            Layout.fillWidth: true
            spacing: 8

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 110
                radius: 0
                color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26"
                border.width: 1
                border.color: jsonArea.activeFocus ?
                              ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                              ((theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff")

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 6
                    clip: true

                    TextArea {
                        id: jsonArea
                        font.family: (theme && theme.monoFont) ? theme.monoFont : "monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        placeholderText: qsTr("在此粘贴导出的 accounts_hub.json 或账号字典...")
                        wrapMode: TextEdit.WrapAnywhere
                        selectByMouse: true
                        background: Rectangle {
                            color: "transparent"
                            radius: 0
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Item { Layout.fillWidth: true }

                Rectangle {
                    height: 28
                    implicitWidth: 80
                    radius: 0
                    color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                    opacity: jsonArea.text.trim().length > 0 ? 1.0 : 0.5
                    enabled: jsonArea.text.trim().length > 0

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("确认导入")
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        color: (theme && theme.accentForeground) ? theme.accentForeground : "#000000"
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: parent.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: {
                            if (backend && typeof backend.importAccounts === "function" && jsonArea.text.trim().length > 0) {
                                backend.importAccounts(jsonArea.text.trim());
                                root.close();
                            }
                        }
                    }
                }
            }
        }
    }
}
