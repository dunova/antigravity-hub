import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: filterBar
    height: 40

    // Public API for external shortcut focus & clearing
    function focusSearch() {
        searchInput.forceActiveFocus();
        searchInput.selectAll();
    }

    function clearSearch() {
        searchInput.text = "";
        if (proxyModel) proxyModel.filterText = "";
    }

    function clearOrUnfocus() {
        if (searchInput.activeFocus || searchInput.text.length > 0) {
            clearSearch();
            searchInput.focus = false;
        }
    }

    property int selectionCount: 0
    signal batchExportRequested()
    signal batchDeleteRequested()
    signal clearSelectionRequested()

    RowLayout {
        anchors.fill: parent
        spacing: 8

        // -------------------------------------------------------------
        // 1. 实时搜索输入框 (支持快捷键 / 聚焦)
        // -------------------------------------------------------------
        Rectangle {
            id: searchBox
            Layout.preferredWidth: 230
            Layout.preferredHeight: 32
            radius: Math.max((theme ? theme.radius : 0) - 4, 4)
            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
            border.width: searchInput.activeFocus ? 1.5 : 1
            border.color: searchInput.activeFocus ?
                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                          ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")

            Behavior on border.color { ColorAnimation { duration: 150 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 6
                spacing: 6

                // 搜索矢量图标
                AppIcon {
                    name: "search"
                    size: 14
                    tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#bed6c9"
                }

                TextInput {
                    id: searchInput
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    verticalAlignment: TextInput.AlignVCenter
                    font.family: "Monospace"
                    font.pixelSize: 12
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#c0caf5"
                    selectByMouse: true
                    clip: true

                    // Placeholder Text
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        text: qsTr("Search accounts...")
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                        font.family: "Monospace"
                        font.pixelSize: 12
                        visible: !searchInput.text && !searchInput.activeFocus
                    }

                    onTextChanged: {
                        if (proxyModel) proxyModel.filterText = text;
                    }

                    Keys.onEscapePressed: {
                        searchInput.text = "";
                        if (proxyModel) proxyModel.filterText = "";
                        searchInput.focus = false;
                    }
                }

                // 清空搜索按钮
                Rectangle {
                    id: btnClear
                    visible: searchInput.text.length > 0
                    width: 16
                    height: 16
                    radius: 8
                    color: clearMouse.containsMouse ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#203b31") : "transparent"

                    AppIcon {
                        anchors.centerIn: parent
                        name: "close"
                        size: 11
                        tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#bed6c9"
                    }

                    MouseArea {
                        id: clearMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            filterBar.clearSearch();
                            searchInput.forceActiveFocus();
                        }
                    }
                }

                // 快捷键提示徽章 '/'
                Rectangle {
                    visible: !searchInput.activeFocus && searchInput.text.length === 0
                    width: 16
                    height: 16
                    radius: 3
                    color: (theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b"
                    border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "/"
                        font.family: "Monospace"
                        font.pixelSize: 10
                        font.bold: true
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // 2. 五大状态过滤胶囊标签组 (全部、可用、充足、告急、枯竭)
        // -------------------------------------------------------------
        RowLayout {
            spacing: 4

            Repeater {
                model: [
                    { key: "all", label: qsTr("All"), dot: "" },
                    { key: "usable", label: qsTr("Usable"), dot: "#3B82F6" },
                    { key: "plentiful", label: qsTr("Plentiful"), dot: "#22C55E" },
                    { key: "warning", label: qsTr("Warning"), dot: "#F59E0B" },
                    { key: "exhausted", label: qsTr("Exhausted"), dot: "#EF4444" }
                ]

                delegate: Rectangle {
                    id: tabCapsule
                    required property var modelData
                    property bool isActive: proxyModel ? (proxyModel.statusTab === modelData.key) : (modelData.key === "all")

                    implicitWidth: tabRow.implicitWidth + 16
                    implicitHeight: 28
                    radius: Math.max((theme ? theme.radius : 0) - 4, 4)

                    color: isActive ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                           (tabMouse.containsMouse ?
                               ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26") : "transparent")
                    border.width: 1
                    border.color: isActive ?
                                  ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                  ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")

                    Behavior on color { ColorAnimation { duration: 120 } }
                    Behavior on border.color { ColorAnimation { duration: 120 } }

                    RowLayout {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 5

                        // 状态色标小圆点
                        Rectangle {
                            visible: modelData.dot !== ""
                            width: 6
                            height: 6
                            radius: 3
                            color: modelData.dot !== "" ? modelData.dot : "transparent"
                        }

                        Text {
                            text: modelData.label
                            font.pixelSize: 11
                            font.bold: tabCapsule.isActive
                            color: tabCapsule.isActive ?
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#ffffff") :
                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6")
                        }
                    }

                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (proxyModel) proxyModel.statusTab = modelData.key;
                        }
                    }
                }
            }
        }

        // 弹性占位空间
        Item {
            Layout.fillWidth: true
        }

        // -------------------------------------------------------------
        // 3. 动态过滤数量徽章 (filteredCount / totalCount)
        // -------------------------------------------------------------
        Rectangle {
            visible: filterBar.selectionCount === 0
            implicitWidth: counterText.implicitWidth + 14
            implicitHeight: 26
            radius: Math.max((theme ? theme.radius : 0) - 4, 4)
            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
            border.width: 1
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

            RowLayout {
                id: counterText
                anchors.centerIn: parent
                spacing: 2

                Text {
                    text: proxyModel ? proxyModel.filteredCount : 0
                    font.family: "Monospace"
                    font.pixelSize: 11
                    font.bold: true
                    color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A"
                }
                Text {
                    text: " / " + (proxyModel ? proxyModel.totalCount : 0)
                    font.family: "Monospace"
                    font.pixelSize: 11
                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                }
            }
        }

        // -------------------------------------------------------------
        // 4. 渐进式批量操作栏 (勾选时滑出)
        // -------------------------------------------------------------
        RowLayout {
            visible: filterBar.selectionCount > 0
            spacing: 6

            Text {
                text: qsTr("%n account(s) selected", "", filterBar.selectionCount)
                font.family: "Monospace"
                font.pixelSize: 11
                color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A"
            }

            Rectangle {
                implicitWidth: btnExportText.implicitWidth + 14
                implicitHeight: 26
                radius: 4
                color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

                Text {
                    id: btnExportText
                    anchors.centerIn: parent
                    text: qsTr("Export")
                    font.pixelSize: 11
                    color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#dfede5"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: filterBar.batchExportRequested()
                }
            }

            Rectangle {
                implicitWidth: btnDeleteText.implicitWidth + 14
                implicitHeight: 26
                radius: 4
                color: "#26EF4444"
                border.color: "#EF4444"

                Text {
                    id: btnDeleteText
                    anchors.centerIn: parent
                    text: qsTr("Delete")
                    font.pixelSize: 11
                    color: "#EF4444"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: filterBar.batchDeleteRequested()
                }
            }

            Rectangle {
                implicitWidth: btnCancelText.implicitWidth + 14
                implicitHeight: 26
                radius: 4
                color: "transparent"
                border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

                Text {
                    id: btnCancelText
                    anchors.centerIn: parent
                    text: qsTr("Cancel")
                    font.pixelSize: 11
                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: filterBar.clearSelectionRequested()
                }
            }
        }
    }
}
