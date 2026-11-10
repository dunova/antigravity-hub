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
            radius: 0
            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
            border.width: searchInput.activeFocus ? 1.5 : 1
            border.color: searchInput.activeFocus ?
                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                          ((theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff")

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
                    tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                }

                TextInput {
                    id: searchInput
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    verticalAlignment: TextInput.AlignVCenter
                    font.family: theme.uiFont
                    font.pixelSize: 12
                    renderType: Text.NativeRendering
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    selectByMouse: true
                    clip: true

                    // Placeholder Text
                    Text {
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        text: qsTr("Search accounts...")
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                        font.family: theme.uiFont
                        font.pixelSize: 12
                        renderType: Text.NativeRendering
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
                    radius: 0
                    color: clearMouse.containsMouse ?
                           ((theme && theme.surface3) ? theme.surface3 : "#3c3836") : "transparent"

                    AppIcon {
                        anchors.centerIn: parent
                        name: "close"
                        size: 11
                        tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
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
                    radius: 0
                    color: (theme && theme.surface3) ? theme.surface3 : "#3c3836"
                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "/"
                        font.family: theme.monoFont
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        renderType: Text.NativeRendering
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
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
                    { key: "usable", label: qsTr("Usable"), dot: (theme && theme.accent) ? theme.accent : "#7daea3" },
                    { key: "plentiful", label: qsTr("Plentiful"), dot: (theme && theme.goodText) ? theme.goodText : "#5fc97f" },
                    { key: "warning", label: qsTr("Warning"), dot: (theme && theme.warningText) ? theme.warningText : "#ffc27a" },
                    { key: "exhausted", label: qsTr("Exhausted"), dot: (theme && theme.dangerText) ? theme.dangerText : "#ff5f4a" }
                ]

                delegate: Rectangle {
                    id: tabCapsule
                    required property var modelData
                    property bool isActive: proxyModel ? (proxyModel.statusTab === modelData.key) : (modelData.key === "all")

                    implicitWidth: tabRow.implicitWidth + 24
                    implicitHeight: 30
                    radius: 0

                    color: isActive ?
                           ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                           (tabMouse.containsMouse ?
                               ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c") : "transparent")
                    border.width: 1
                    border.color: isActive ?
                                  ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                  ((theme && theme.controlBorder) ? theme.controlBorder : "#3dffffff")

                    Behavior on color { ColorAnimation { duration: 120 } }
                    Behavior on border.color { ColorAnimation { duration: 120 } }

                    RowLayout {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 5

                        // 状态色标小方块 (Marker 4: 全部在激活时显示 theme.accent 小方块)
                        Rectangle {
                            visible: (modelData.dot !== "") || (tabCapsule.isActive && modelData.key === "all")
                            width: 6
                            height: 6
                            radius: 0
                            color: (modelData.key === "all" && tabCapsule.isActive) ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   (modelData.dot !== "" ? modelData.dot : "transparent")
                        }

                        Text {
                            text: modelData.label
                            font.family: theme.uiFont
                            font.pixelSize: 11
                            font.bold: tabCapsule.isActive
                            renderType: Text.NativeRendering
                            color: tabCapsule.isActive ?
                                   ((theme && theme.accentText) ? theme.accentText : ((theme && theme.text1) ? theme.text1 : "#FFFFFF")) :
                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
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
            implicitWidth: counterText.implicitWidth + 14
            Layout.preferredHeight: 28
            radius: 0
            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
            border.width: 1
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

            RowLayout {
                id: counterText
                anchors.centerIn: parent
                spacing: 2

                Text {
                    text: proxyModel ? proxyModel.filteredCount : 0
                    font.family: theme.monoFont
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    renderType: Text.NativeRendering
                    color: (theme && theme.accent) ? theme.accent : "#7daea3"
                }
                Text {
                    text: " / " + (proxyModel ? proxyModel.totalCount : 0)
                    font.family: theme.monoFont
                    font.pixelSize: 11
                    renderType: Text.NativeRendering
                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                }
            }
        }
    }
}
