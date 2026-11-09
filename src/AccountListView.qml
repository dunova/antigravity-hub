import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: accountListView

    // =========================================================================
    // 0. 共享列几何常数 (Strict Header-Data Row Synchronization)
    // =========================================================================
    readonly property int colCheckWidth: 28
    readonly property int colIndexWidth: 30
    readonly property int colStatusWidth: 80
    readonly property int colAccountWidth: 112
    readonly property real colG4Weight: 1.05
    readonly property real colG38Weight: 1.35
    readonly property real colClaudeWeight: 1.35
    readonly property int colActionWidth: 74

    // 选中的账号集合 (维护当前勾选账号列表)
    property var selectedEmails: ({})
    property int selectedCount: Object.keys(selectedEmails).length

    signal selectionChanged(int count)

    function selectAllVisible() {
        if (!proxyModel) return;
        var count = proxyModel.rowCount();
        var newSelected = {};
        for (var i = 0; i < count; ++i) {
            var acc = proxyModel.getFilteredAccount(i);
            if (acc && acc.email) {
                newSelected[acc.email] = true;
            }
        }
        selectedEmails = newSelected;
        selectionChanged(Object.keys(selectedEmails).length);
    }

    function clearSelection() {
        selectedEmails = ({});
        selectionChanged(0);
    }

    function toggleSelectRow(email) {
        var cur = Object.assign({}, selectedEmails);
        if (cur[email]) {
            delete cur[email];
        } else {
            cur[email] = true;
        }
        selectedEmails = cur;
        selectionChanged(Object.keys(selectedEmails).length);
    }

    // 快捷键列表导航方法 (供 Main.qml 全局快捷键调用)
    function selectNext() {
        if (listView.count === 0) return;
        var nextIdx = Math.min(listView.currentIndex + 1, listView.count - 1);
        listView.currentIndex = nextIdx;
        listView.positionViewAtIndex(nextIdx, ListView.Contain);
    }

    function selectPrevious() {
        if (listView.count === 0) return;
        var prevIdx = Math.max(listView.currentIndex - 1, 0);
        listView.currentIndex = prevIdx;
        listView.positionViewAtIndex(prevIdx, ListView.Contain);
    }

    function activateCurrent() {
        if (listView.currentIndex >= 0 && listView.currentIndex < listView.count) {
            var acc = proxyModel.getFilteredAccount(listView.currentIndex);
            if (acc && acc.email && !acc.isActive && backend) {
                backend.switchAccount(acc.email);
            }
        }
    }

    // Compatibility aliases
    function selectNextRow() { selectNext(); }
    function selectPrevRow() { selectPrevious(); }
    function switchSelectedRow() { activateCurrent(); }

    // 配额颜色判定阈值逻辑 (Omarchy High-Contrast WCAG 规范)
    function getQuotaColor(ratio) {
        if (ratio === undefined || ratio === null || isNaN(ratio)) return (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1";
        if (ratio <= 0.0001) return (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a";
        if (ratio >= 0.50) return (theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f";
        if (ratio >= 0.15) return (theme && theme.warningText && theme.warningText.charAt(0) === '#') ? theme.warningText : "#ffc27a";
        return (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a";
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // =============================================================
        // 1. 固定表格表头行 (Table Header Row)
        // =============================================================
        Rectangle {
            id: headerRow
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            radius: 0
            gradient: Gradient {
                GradientStop { position: 0; color: (theme && theme.surfaceTop && theme.surfaceTop.charAt(0) === '#') ? theme.surfaceTop : "#172c25" }
                GradientStop { position: 1; color: (theme && theme.surfaceBottom && theme.surfaceBottom.charAt(0) === '#') ? theme.surfaceBottom : "#11201b" }
            }
            border.width: 1
            border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 6

                // Col 1: 全选复选框
                Item {
                    Layout.preferredWidth: colCheckWidth
                    Layout.fillHeight: true
                    CheckBox {
                        anchors.centerIn: parent
                        checked: accountListView.selectedCount > 0 &&
                                 proxyModel && (accountListView.selectedCount === proxyModel.rowCount())
                        onToggled: {
                            if (checked) {
                                accountListView.selectAllVisible();
                            } else {
                                accountListView.clearSelection();
                            }
                        }
                    }
                }

                // Col 2: # 序号 (支持点击按序号排序)
                Rectangle {
                    Layout.preferredWidth: colIndexWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            text: "#"
                            font.family: "Monospace"
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "index") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "index") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 10
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "index") {
                                proxyModel.setSortRule("index", Qt.AscendingOrder);
                            } else if (proxyModel.sortOrder === Qt.AscendingOrder) {
                                proxyModel.setSortRule("index", Qt.DescendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Col 3: 状态 (支持点击按状态排序)
                Rectangle {
                    Layout.preferredWidth: colStatusWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            text: qsTr("Status")
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "status") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "status") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 10
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "status") {
                                proxyModel.setSortRule("status", Qt.AscendingOrder);
                            } else if (proxyModel.sortOrder === Qt.AscendingOrder) {
                                proxyModel.setSortRule("status", Qt.DescendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Col 4: 账号 (支持点击按账号字母序排序)
                Rectangle {
                    Layout.preferredWidth: colAccountWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 4
                        spacing: 2

                        Text {
                            text: qsTr("Account")
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && (proxyModel.sortField === "account" || proxyModel.sortField === "username")) ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "account" || proxyModel.sortField === "username") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 10
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "account") {
                                proxyModel.setSortRule("account", Qt.AscendingOrder);
                            } else if (proxyModel.sortOrder === Qt.AscendingOrder) {
                                proxyModel.setSortRule("account", Qt.DescendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Hairline between Col 4 and Col 5
                Rectangle {
                    width: 1
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 4
                    Layout.bottomMargin: 4
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 5: Gemini 4 (用户最高铁律门禁：严格命名为 Gemini 4，彻底切除周标签)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: Math.round(100 * colG4Weight)
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Gemini 4") // MANDATORY: STRICTLY "Gemini 4"
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "gemini4") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "gemini4") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "gemini4") {
                                proxyModel.setSortRule("gemini4", Qt.DescendingOrder);
                            } else if (proxyModel.sortOrder === Qt.DescendingOrder) {
                                proxyModel.setSortRule("gemini4", Qt.AscendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Hairline between Col 5 and Col 6
                Rectangle {
                    width: 1
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 4
                    Layout.bottomMargin: 4
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 6: Gemini 3.8 双维配额表头
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: Math.round(100 * colG38Weight)
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Gemini 3.8")
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "gemini38_w") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "gemini38_w") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "gemini38_w") {
                                proxyModel.setSortRule("gemini38_w", Qt.DescendingOrder);
                            } else if (proxyModel.sortOrder === Qt.DescendingOrder) {
                                proxyModel.setSortRule("gemini38_w", Qt.AscendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Hairline between Col 6 and Col 7
                Rectangle {
                    width: 1
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 4
                    Layout.bottomMargin: 4
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 7: Claude 双维配额表头
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: Math.round(100 * colClaudeWeight)
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Claude")
                            font.pixelSize: 12
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "claude_w") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "claude_w") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (!proxyModel) return;
                            if (proxyModel.sortField !== "claude_w") {
                                proxyModel.setSortRule("claude_w", Qt.DescendingOrder);
                            } else if (proxyModel.sortOrder === Qt.DescendingOrder) {
                                proxyModel.setSortRule("claude_w", Qt.AscendingOrder);
                            } else {
                                proxyModel.setSortRule("default", Qt.DescendingOrder);
                            }
                        }
                    }
                }

                // Hairline between Col 7 and Col 8
                Rectangle {
                    width: 1
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 4
                    Layout.bottomMargin: 4
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 8: 操作
                Item {
                    Layout.preferredWidth: colActionWidth
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Actions")
                        font.pixelSize: 12
                        font.bold: true
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                }
            }
        }

        // =============================================================
        // 1.5. 渐进式批量操作工具栏 (Batch Action Bar - selectedCount > 0 时显式展开)
        // =============================================================
        Rectangle {
            id: batchActionBar
            visible: accountListView.selectedCount > 0
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 36 : 0
            radius: 0
            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26"
            border.width: 1
            border.color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
            clip: true

            Behavior on Layout.preferredHeight { NumberAnimation { duration: 120 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                // 选计数量提示
                RowLayout {
                    spacing: 6
                    Rectangle {
                        width: 6
                        height: 6
                        radius: 0
                        color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                    }
                    Text {
                        text: qsTr("%n account(s) selected", "", accountListView.selectedCount)
                        font.pixelSize: 12
                        font.bold: true
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                }

                Item { Layout.fillWidth: true }

                // [批量预热]
                Rectangle {
                    height: 26
                    implicitWidth: btnWarmupText.implicitWidth + 20
                    radius: 0
                    color: warmupMouse.containsMouse ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                           ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620")
                    border.width: 1
                    border.color: (theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff"

                    Text {
                        id: btnWarmupText
                        anchors.centerIn: parent
                        text: qsTr("Prewarm")
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                    MouseArea {
                        id: warmupMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: {
                            var emails = Object.keys(accountListView.selectedEmails);
                            if (backend && typeof backend.batchWarmup === "function") {
                                backend.batchWarmup(emails);
                            } else if (backend) {
                                backend.triggerPrewarm();
                            }
                        }
                    }
                }

                // [导出所选]
                Rectangle {
                    height: 26
                    implicitWidth: btnExportText.implicitWidth + 20
                    radius: 0
                    color: exportMouse.containsMouse ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                           ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620")
                    border.width: 1
                    border.color: (theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff"

                    Text {
                        id: btnExportText
                        anchors.centerIn: parent
                        text: qsTr("Export Selected")
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                    MouseArea {
                        id: exportMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: {
                            var emails = Object.keys(accountListView.selectedEmails);
                            if (backend && typeof backend.exportSelectedAccounts === "function") {
                                backend.exportSelectedAccounts(emails);
                            } else if (backend && typeof backend.exportSelected === "function") {
                                backend.exportSelected(emails);
                            }
                        }
                    }
                }

                // [删除账号] (Danger 赤陶警示色)
                Rectangle {
                    height: 26
                    implicitWidth: btnDeleteText.implicitWidth + 20
                    radius: 0
                    color: deleteMouse.containsMouse ?
                           Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.25) :
                           Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.15)
                    border.width: 1
                    border.color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"

                    Text {
                        id: btnDeleteText
                        anchors.centerIn: parent
                        text: qsTr("Delete Selected")
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"
                    }
                    MouseArea {
                        id: deleteMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: deleteConfirmDialog.open()
                    }
                }

                // [取消选择]
                Rectangle {
                    height: 26
                    implicitWidth: btnCancelText.implicitWidth + 18
                    radius: 0
                    color: cancelMouse.containsMouse ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") : "transparent"
                    border.width: 1
                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"

                    Text {
                        id: btnCancelText
                        anchors.centerIn: parent
                        text: qsTr("Clear Selection")
                        font.pixelSize: 11
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#CBD5E1"
                    }
                    MouseArea {
                        id: cancelMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: accountListView.clearSelection()
                    }
                }
            }
        }

        // =============================================================
        // 2. 账号列表数据视图 (ListView bound to proxyModel)
        // =============================================================
        ListView {
            id: listView
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: proxyModel
            boundsBehavior: Flickable.StopAtBounds

            ScrollBar.vertical: ScrollBar {
                id: listScrollBar
                policy: ScrollBar.AsNeeded
                width: 6
                contentItem: Rectangle {
                    implicitWidth: 6
                    radius: 0
                    color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"
                }
                background: Item {}
            }

            // 空列表状态提示
            Item {
                anchors.centerIn: parent
                visible: listView.count === 0
                width: 260
                height: 120

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 8

                    AppIcon {
                        Layout.alignment: Qt.AlignHCenter
                        name: "help"
                        size: 32
                        tint: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#bed6c9"
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("No matching accounts found")
                        font.pixelSize: 13
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#bed6c9"
                    }
                }
            }

            // ---------------------------------------------------------
            // 3. 账号行委托 (Account Row Delegate)
            // ---------------------------------------------------------
            delegate: Rectangle {
                id: rowDelegate
                width: listView.width
                height: 56
                radius: 0

                // 25 项 QML Role 绑定的直接消费
                property bool isRowActive: model.isActive || false
                property bool isRowBlocked: model.isBlocked || false
                property bool isRowSelected: listView.currentIndex === index
                property bool isRowChecked: accountListView.selectedEmails[model.email] === true

                // 行背景与高亮逻辑 (通过 theme.rowEven / theme.rowOdd 计算带主题色的斑马纹)
                color: isRowActive ?
                       Qt.alpha((theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f", 0.18) :
                       (isRowSelected ?
                           Qt.alpha((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1", 0.22) :
                           (rowMouse.containsMouse ?
                               ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                               (index % 2 === 0 ?
                                   ((theme && theme.rowEven && theme.rowEven.charAt(0) === '#') ? theme.rowEven : "#0a0a0f") :
                                   ((theme && theme.rowOdd && theme.rowOdd.charAt(0) === '#') ? theme.rowOdd : "#1a1b26"))))

                border.width: isRowSelected ? 1 : 0
                border.color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    radius: 0
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        listView.currentIndex = index;
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 6

                    // -------------------------------------------------
                    // Col 1: 行复选框
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colCheckWidth
                        Layout.fillHeight: true
                        CheckBox {
                            anchors.centerIn: parent
                            checked: rowDelegate.isRowChecked
                            onToggled: accountListView.toggleSelectRow(model.email)
                        }
                    }

                    // -------------------------------------------------
                    // Col 2: # 序号 (1-based, 纯白高对比)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colIndexWidth
                        Layout.fillHeight: true
                        Text {
                            anchors.centerIn: parent
                            text: model.index
                            font.family: "Monospace"
                            font.pixelSize: 12
                            font.bold: true
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        }
                    }

                    // -------------------------------------------------
                    // Col 3: 状态胶囊 (全直角长方形)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colStatusWidth
                        Layout.fillHeight: true

                        Rectangle {
                            anchors.centerIn: parent
                            width: 74
                            height: 24
                            radius: 0

                            color: model.isActive ?
                                   Qt.alpha((theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f", 0.18) :
                                   (model.isBlocked ?
                                       Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.18) :
                                       (model.status === "EXHAUSTED" ?
                                           Qt.alpha((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#6B7280", 0.15) :
                                           ((theme && theme.mode === "light") ? "#0a000000" : "#14ffffff")))

                            border.width: 1
                            border.color: model.isActive ? ((theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f") :
                                          (model.isBlocked ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                              (model.status === "EXHAUSTED" ? ((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#6B7280") :
                                                  ((theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff")))

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 3

                                Text {
                                    text: model.isActive ? qsTr("ACTIVE") :
                                          (model.isBlocked ? qsTr("Blocked") :
                                              (model.status === "EXHAUSTED" ? qsTr("Exhausted") : qsTr("STANDBY")))
                                    font.family: "Monospace"
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: model.isActive ? ((theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f") :
                                           (model.isBlocked ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                               (model.status === "EXHAUSTED" ? ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1") :
                                                   ((theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6")))
                                }

                                // 人工保护倒计时标签
                                RowLayout {
                                    visible: model.isActive && (model.manualLockRemaining > 0)
                                    spacing: 2
                                    AppIcon {
                                        name: "lock"
                                        size: 10
                                        tint: "#F59E0B"
                                    }
                                    Text {
                                        text: model.manualLockRemainingStr || ""
                                        font.family: "Monospace"
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: "#F59E0B"
                                    }
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 4: 账号名称 (纯净用户名，剥离 @gmail.com，默认不脱敏)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colAccountWidth
                        Layout.fillHeight: true

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.displayUsername || ""
                            font.family: (theme && theme.uiFont) ? theme.uiFont : "sans-serif"
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                            color: model.isActive ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")

                            ToolTip.visible: nameMouse.containsMouse
                            ToolTip.text: (model.email || "") + " (" + qsTr("Click to copy") + ")"
                        }

                        MouseArea {
                            id: nameMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (backend && typeof backend.copyToClipboard === "function") {
                                    backend.copyToClipboard(model.email);
                                }
                            }
                        }
                    }

                    // Hairline between Col 4 and Col 5
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 5: Gemini 4 配额单元格 (彻底移除 周 徽标，原生进度条、数值与倒计时)
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Math.round(100 * colG4Weight)
                        Layout.fillHeight: true

                        // 账号无 Gemini 4 权限：优雅呈现中线 —
                        Text {
                            anchors.centerIn: parent
                            visible: !model.gemini4Valid
                            text: "—"
                            font.family: "Monospace"
                            font.pixelSize: 14
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                            ToolTip.visible: g4EmptyMouse.containsMouse
                            ToolTip.text: qsTr("No Gemini 4 access")

                            MouseArea {
                                id: g4EmptyMouse
                                anchors.fill: parent
                                hoverEnabled: true
                            }
                        }

                        // 账号具备 Gemini 4 额度：单轨纯净进度条 (零 周 徽标)
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            visible: model.gemini4Valid
                            spacing: 6

                            // 1. 原生平滑进度条 (高对比纯直角长方形)
                            Rectangle {
                                Layout.fillWidth: true
                                implicitWidth: 64
                                Layout.minimumWidth: 48
                                Layout.preferredHeight: 6
                                height: 6
                                radius: 0
                                color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    radius: 0
                                    width: (model.gemini4Quota <= 0.0001) ? 0 :
                                           Math.min(parent.width, Math.max(4, parent.width * (model.gemini4Quota || 0.0)))
                                    color: accountListView.getQuotaColor(model.gemini4Quota)

                                    Behavior on width { NumberAnimation { duration: 250 } }
                                }
                            }

                            // 2. Monospace 百分比数值
                            Text {
                                Layout.preferredWidth: 44
                                text: ((model.gemini4Quota || 0.0) * 100).toFixed(1) + "%"
                                font.family: "Monospace"
                                font.pixelSize: 12
                                font.bold: true
                                horizontalAlignment: Text.AlignRight
                                color: accountListView.getQuotaColor(model.gemini4Quota)
                            }

                            // 3. 重置倒计时槽位 (52px 零截断)
                            Text {
                                Layout.preferredWidth: 52
                                text: model.gemini4Reset || "--"
                                font.family: "Monospace"
                                font.pixelSize: 11
                                color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideNone
                            }
                        }
                    }

                    // Hairline between Col 5 and Col 6
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 6: Gemini 3.8 双维配额单元格 (带周耗尽 0.0% 熔断)
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Math.round(100 * colG38Weight)
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            spacing: 3

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 24
                                    height: 16
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5h"
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 6
                                    height: 6
                                    radius: 0
                                    color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 0
                                        width: (model.gemini38QuotaW <= 0.0001 || model.gemini38Quota5h <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(4, parent.width * (model.gemini38Quota5h || 0.0)))
                                        color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                               accountListView.getQuotaColor(model.gemini38Quota5h)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: (model.gemini38QuotaW <= 0.0001) ? "0.0%" :
                                          (((model.gemini38Quota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: "Monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           accountListView.getQuotaColor(model.gemini38Quota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: (model.gemini38QuotaW <= 0.0001) ? qsTr("周耗尽") : (model.gemini38Reset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 24
                                    height: 16
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: qsTr("Weekly")
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 6
                                    height: 6
                                    radius: 0
                                    color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 0
                                        width: (model.gemini38QuotaW <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(4, parent.width * (model.gemini38QuotaW || 0.0)))
                                        color: accountListView.getQuotaColor(model.gemini38QuotaW)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: ((model.gemini38QuotaW || 0.0) * 100).toFixed(1) + "%"
                                    font.family: "Monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.gemini38QuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 52
                                    text: model.gemini38ResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideNone
                                }
                            }
                        }
                    }

                    // Hairline between Col 6 and Col 7
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 7: Claude 双维配额单元格
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: Math.round(100 * colClaudeWeight)
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            spacing: 3

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 24
                                    height: 16
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5h"
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 6
                                    height: 6
                                    radius: 0
                                    color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 0
                                        width: (model.claudeQuotaW <= 0.0001 || model.claudeQuota5h <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(4, parent.width * (model.claudeQuota5h || 0.0)))
                                        color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                               accountListView.getQuotaColor(model.claudeQuota5h)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: (model.claudeQuotaW <= 0.0001) ? "0.0%" :
                                          (((model.claudeQuota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: "Monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           accountListView.getQuotaColor(model.claudeQuota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: (model.claudeQuotaW <= 0.0001) ? qsTr("周耗尽") : (model.claudeReset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 24
                                    height: 16
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: qsTr("Weekly")
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 6
                                    height: 6
                                    radius: 0
                                    color: (theme && theme.trackBg && theme.trackBg.charAt(0) === '#') ? theme.trackBg : "#29ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 0
                                        width: (model.claudeQuotaW <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(4, parent.width * (model.claudeQuotaW || 0.0)))
                                        color: accountListView.getQuotaColor(model.claudeQuotaW)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: ((model.claudeQuotaW || 0.0) * 100).toFixed(1) + "%"
                                    font.family: "Monospace"
                                    font.pixelSize: 12
                                    font.bold: true
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.claudeQuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 52
                                    text: model.claudeResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideNone
                                }
                            }
                        }
                    }

                    // Hairline between Col 7 and Col 8
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 8: 快速操作按钮组 (收紧至 74px，纯直角长方形)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colActionWidth
                        Layout.fillHeight: true

                        // 1. 在用徽章 (ACTIVE 状态)
                        Rectangle {
                            anchors.centerIn: parent
                            visible: model.isActive
                            width: 58
                            height: 28
                            radius: 0
                            color: Qt.alpha((theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f", 0.15)
                            border.width: 1
                            border.color: (theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f"

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("In Use")
                                font.pixelSize: 11
                                font.bold: true
                                color: (theme && theme.goodText && theme.goodText.charAt(0) === '#') ? theme.goodText : "#5fc97f"
                            }
                        }

                        // 2. 解封按钮 (BLOCKED 状态)
                        Rectangle {
                            anchors.centerIn: parent
                            visible: !model.isActive && model.isBlocked
                            width: 58
                            height: 28
                            radius: 0
                            color: Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.15)
                            border.width: 1
                            border.color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("Unblock")
                                font.pixelSize: 11
                                font.bold: true
                                color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (backend && typeof backend.unblockAccount === "function") {
                                        backend.unblockAccount(model.email);
                                    }
                                }
                            }
                        }

                        // 3. 切换按钮 (STANDBY 状态)
                        Rectangle {
                            id: btnSwitch
                            anchors.centerIn: parent
                            visible: !model.isActive && !model.isBlocked
                            width: 58
                            height: 28
                            radius: 0
                            color: btnSwitchMouse.containsMouse ?
                                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26")
                            border.width: 1
                            border.color: btnSwitchMouse.containsMouse ?
                                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                          ((theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff")

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("Switch")
                                font.pixelSize: 12
                                font.bold: true
                                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            }

                            MouseArea {
                                id: btnSwitchMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (backend && typeof backend.switchAccount === "function") {
                                        backend.switchAccount(model.email);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // =============================================================
        // 4. 底部极简状态与快捷键导航栏 (26px Omarchy Standard Footer Bar)
        // =============================================================
        Rectangle {
            id: bottomBar
            Layout.fillWidth: true
            Layout.preferredHeight: 26
            radius: 0
            color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
            border.width: 1
            border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                // 统计信息
                RowLayout {
                    spacing: 6
                    Text {
                        text: "Accounts: " + (proxyModel ? proxyModel.rowCount() : 0)
                        font.pixelSize: 11
                        font.family: "Monospace"
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                    }
                    Text {
                        text: "·"
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                    Text {
                        text: "Filtered: " + (proxyModel ? proxyModel.filteredCount : 0)
                        font.pixelSize: 11
                        font.family: "Monospace"
                        color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                // 键盘快捷键提示
                RowLayout {
                    spacing: 8
                    Text {
                        text: "j/k: Navigate · Enter: Switch · r: Refresh · /: Search · ?: Help"
                        font.pixelSize: 10
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                }
            }
        }
    }

    // =========================================================================
    // 彻底删除账号二次确认弹窗 (Omarchy ConfirmDialog)
    // =========================================================================
    Dialog {
        id: deleteConfirmDialog
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape
        anchors.centerIn: Overlay.overlay
        width: 400
        header: null
        footer: null

        background: Rectangle {
            color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#142620"
            border.color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"
            border.width: 1
            radius: 0
        }

        Overlay.modal: Rectangle {
            color: "#a6000000"
        }

        contentItem: ColumnLayout {
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppIcon {
                    name: "warning"
                    size: 18
                    tint: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"
                }
                Text {
                    text: qsTr("Operation Confirmation")
                    font.pixelSize: 14
                    font.bold: true
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    Layout.fillWidth: true
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Are you sure you want to delete %n account(s)?", "", accountListView.selectedCount)
                font.pixelSize: 12
                color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#CBD5E1"
                wrapMode: Text.WordWrap
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                radius: 0
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Item { Layout.fillWidth: true }

                Rectangle {
                    height: 30
                    implicitWidth: 80
                    radius: 0
                    color: cancelDlgMouse.containsMouse ?
                           ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") : "transparent"
                    border.width: 1
                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Cancel")
                        font.pixelSize: 12
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#CBD5E1"
                    }
                    MouseArea {
                        id: cancelDlgMouse
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: deleteConfirmDialog.close()
                    }
                }

                Rectangle {
                    height: 30
                    implicitWidth: 90
                    radius: 0
                    color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Delete")
                        font.pixelSize: 12
                        font.bold: true
                        color: "#FFFFFF"
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        hoverEnabled: true
                        onClicked: {
                            var emails = Object.keys(accountListView.selectedEmails);
                            if (backend && typeof backend.deleteAccounts === "function") {
                                backend.deleteAccounts(emails);
                            }
                            accountListView.clearSelection();
                            deleteConfirmDialog.close();
                        }
                    }
                }
            }
        }
    }
}
