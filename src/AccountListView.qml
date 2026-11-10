import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: accountListView

    // =========================================================================
    // 0. 共享列几何常数 (Strict Header-Data Row Synchronization - Tiled 896px Geometry)
    // =========================================================================
    readonly property int colCheckWidth: 24
    readonly property int colIndexWidth: 26
    readonly property int colStatusWidth: 66
    readonly property int colAccountWidth: 106
    readonly property int colG4Width: 150
    readonly property int colG38Width: 218
    readonly property int colClaudeWidth: 218
    readonly property int rowHeight: 40
    readonly property int pageSize: 15
    readonly property int pageCount: Math.max(1, Math.ceil(listView.count / pageSize))
    readonly property int currentPage: Math.min(pageCount - 1, Math.floor((listView.contentY + 1) / (rowHeight * pageSize)))
    function gotoPage(p) {
        var pg = Math.max(0, Math.min(pageCount - 1, p));
        listView.positionViewAtIndex(pg * pageSize, ListView.Beginning);
    }
    readonly property int colActionWidth: 65

    // 账号配额统计计数 (供底部状态栏与筛选器消费)
    readonly property int availableCount: {
        if (!accountModel) return 0;
        var count = 0;
        var total = (typeof accountModel.rowCount === "function") ? accountModel.rowCount() : (accountModel.count || 0);
        for (var i = 0; i < total; ++i) {
            var acc = (typeof accountModel.getAccount === "function") ? accountModel.getAccount(i) : (accountModel.get ? accountModel.get(i) : null);
            if (acc && !acc.isBlocked && (acc.gemini38QuotaW > 0.0001 || acc.claudeQuotaW > 0.0001 || acc.gemini4Quota > 0.0001)) {
                count++;
            }
        }
        return count;
    }
    readonly property int displayedCount: proxyModel ? proxyModel.filteredCount : listView.count

    // 自定义账号排序: 一键置顶操作
    function moveAccountToTop(email) {
        if (!email) return;
        var emails = [];
        emails.push(email);
        var total = (accountModel && typeof accountModel.count !== "undefined") ? accountModel.count :
                    (accountModel ? (typeof accountModel.rowCount === "function" ? accountModel.rowCount() : accountModel.totalAccounts) : 0);
        for (var i = 0; i < total; ++i) {
            var acc = (typeof accountModel.get === "function") ? accountModel.get(i) : accountModel.getAccount(i);
            var e = acc ? acc.email : "";
            if (e && e !== email) emails.push(e);
        }
        if (typeof backendController !== "undefined" && backendController) {
            backendController.reorderAccounts(emails);
        } else if (typeof backend !== "undefined" && backend) {
            backend.reorderAccounts(emails);
        }
    }

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
            Layout.preferredHeight: 30
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
                spacing: 0

                // Col 1: 全选复选框
                Item {
                    Layout.preferredWidth: colCheckWidth
                    Layout.minimumWidth: colCheckWidth
                    Layout.maximumWidth: colCheckWidth
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
                    Layout.minimumWidth: colIndexWidth
                    Layout.maximumWidth: colIndexWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            text: "#"
                            font.family: theme.monoFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && proxyModel.sortField === "index") ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "index") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: colStatusWidth
                    Layout.maximumWidth: colStatusWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            text: qsTr("Status")
                            font.family: theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && proxyModel.sortField === "status") ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "status") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: colAccountWidth
                    Layout.maximumWidth: colAccountWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 4
                        spacing: 2

                        Text {
                            text: qsTr("Account")
                            font.family: theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && (proxyModel.sortField === "account" || proxyModel.sortField === "username")) ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "account" || proxyModel.sortField === "username") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: 1
                    Layout.maximumWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 6
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 5: Gemini 4 (用户最高铁律门禁：严格命名为 Gemini 4，彻底切除周标签)
                Rectangle {
                    Layout.preferredWidth: colG4Width
                    Layout.minimumWidth: colG4Width
                    Layout.maximumWidth: colG4Width
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Gemini 4") // MANDATORY: STRICTLY "Gemini 4"
                            font.family: theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && proxyModel.sortField === "gemini4") ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "gemini4") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: 1
                    Layout.maximumWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 6
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 6: Gemini 3.8 双维配额表头
                Rectangle {
                    Layout.preferredWidth: colG38Width
                    Layout.minimumWidth: colG38Width
                    Layout.maximumWidth: colG38Width
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Gemini 3.8")
                            font.family: theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && proxyModel.sortField === "gemini38_w") ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "gemini38_w") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: 1
                    Layout.maximumWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 6
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 7: Claude 双维配额表头
                Rectangle {
                    Layout.preferredWidth: colClaudeWidth
                    Layout.minimumWidth: colClaudeWidth
                    Layout.maximumWidth: colClaudeWidth
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        spacing: 4

                        Text {
                            text: qsTr("Claude")
                            font.family: theme.uiFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (proxyModel && proxyModel.sortField === "claude_w") ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "claude_w") : false
                            text: (proxyModel && proxyModel.sortOrder === Qt.DescendingOrder) ? "↓" : "↑"
                            font.pixelSize: 11
                            renderType: Text.NativeRendering
                            color: (theme && theme.accent) ? theme.accent : "#7daea3"
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
                    Layout.minimumWidth: 1
                    Layout.maximumWidth: 1
                    Layout.fillHeight: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 6
                    color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                }

                // Col 8: 操作
                Item {
                    Layout.preferredWidth: colActionWidth
                    Layout.minimumWidth: colActionWidth
                    Layout.maximumWidth: colActionWidth
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Actions")
                        font.family: theme.uiFont
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        renderType: Text.NativeRendering
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
            border.color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#7daea3"
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
                        color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#7daea3"
                    }
                    Text {
                        text: qsTr("%n account(s) selected", "", accountListView.selectedCount)
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
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
                        font.weight: Font.DemiBold
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
                        font.weight: Font.DemiBold
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
                        font.weight: Font.DemiBold
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
            snapMode: ListView.SnapToItem

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
                height: accountListView.rowHeight
                radius: 0

                // 25 项 QML Role 绑定的直接消费
                property bool isRowActive: model.isActive || false
                property bool isRowBlocked: model.isBlocked || false
                property bool isRowSelected: listView.currentIndex === index
                property bool isRowChecked: accountListView.selectedEmails[model.email] === true

                // Marker 7: 严格固定屏幕行交替斑马律 (index % 2 永恒交替，不受排序或激活行位置干扰)
                readonly property color rowBgColor: (index % 2 === 0) ?
                    ((theme && theme.rowEven) ? theme.rowEven : "#1c1c1c") :
                    ((theme && theme.rowOdd) ? theme.rowOdd : "#32302f")

                color: isRowSelected ?
                    Qt.alpha((theme && theme.accent) ? theme.accent : "#7daea3", 0.24) :
                    (rowMouse.containsMouse ?
                        ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                        (isRowActive ? Qt.tint(rowBgColor, Qt.alpha((theme && theme.accent) ? theme.accent : "#7daea3", 0.10)) : rowBgColor))

                border.width: isRowSelected ? 1 : 0
                border.color: (theme && theme.accent) ? theme.accent : "#7daea3"

                // Marker 7: 激活行左侧 3px 主题色指示竖条
                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 3
                    radius: 0
                    visible: isRowActive
                    color: (theme && theme.accent) ? theme.accent : "#7daea3"
                    z: 2
                }

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
                    spacing: 0

                    // -------------------------------------------------
                    // Col 1: 行复选框
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colCheckWidth
                        Layout.minimumWidth: colCheckWidth
                        Layout.maximumWidth: colCheckWidth
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
                        Layout.minimumWidth: colIndexWidth
                        Layout.maximumWidth: colIndexWidth
                        Layout.fillHeight: true
                        Text {
                            anchors.centerIn: parent
                            text: model.index
                            font.family: theme.monoFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        }
                    }

                    // -------------------------------------------------
                    // Col 3: 状态胶囊 (全直角长方形 74x20)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colStatusWidth
                        Layout.minimumWidth: colStatusWidth
                        Layout.maximumWidth: colStatusWidth
                        Layout.fillHeight: true

                        Rectangle {
                            anchors.centerIn: parent
                            width: 58
                            height: 20
                            radius: 0

                            // Marker 5: 行内 ACTIVE 状态徽章定锚 theme.accent，严禁 goodText 绿色
                            color: model.isActive ?
                                   Qt.alpha((theme && theme.accent) ? theme.accent : "#7daea3", 0.15) :
                                   (model.isBlocked ?
                                       Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.18) :
                                       (model.status === "EXHAUSTED" ?
                                           Qt.alpha((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#6B7280", 0.15) :
                                           ((theme && theme.mode === "light") ? "#0a000000" : "#14ffffff")))

                            border.width: 1
                            border.color: model.isActive ? ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                          (model.isBlocked ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                              (model.status === "EXHAUSTED" ? ((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#6B7280") :
                                                  ((theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff")))

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 3

                                // Marker 5: 呼吸指示方块 (breathing dot) 定锚 theme.accent
                                Rectangle {
                                    width: 5
                                    height: 5
                                    radius: 0
                                    visible: model.isActive
                                    color: (theme && theme.accent) ? theme.accent : "#7daea3"
                                }

                                Text {
                                    text: model.isActive ? qsTr("ACTIVE") :
                                          (model.isBlocked ? qsTr("Blocked") :
                                              (model.status === "EXHAUSTED" ? qsTr("Exhausted") : qsTr("STANDBY")))
                                    font.family: theme.monoFont
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: model.isActive ?
                                           ((theme && theme.accentText) ? theme.accentText : ((theme && theme.accent) ? theme.accent : "#7daea3")) :
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
                                        font.family: theme.monoFont
                                        font.pixelSize: 11
                                        font.weight: Font.DemiBold
                                        renderType: Text.NativeRendering
                                        color: "#F59E0B"
                                    }
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 4: 账号名称 (纯净用户名，拖拽手柄 ⠿ + 悬浮[置顶]按钮 + 点击复制邮箱)
                    // -------------------------------------------------
                    Item {
                        id: col4AccountItem
                        Layout.preferredWidth: colAccountWidth
                        Layout.minimumWidth: colAccountWidth
                        Layout.maximumWidth: colAccountWidth
                        Layout.fillHeight: true

                        // 1. 拖拽手柄图标 (⠿)
                        Item {
                            id: dragHandle
                            width: 14
                            height: parent.height
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter

                            Text {
                                anchors.centerIn: parent
                                text: "⠿"
                                font.family: theme.monoFont
                                font.pixelSize: 13
                                renderType: Text.NativeRendering
                                color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#64887b"
                            }

                            MouseArea {
                                id: dragMouse
                                anchors.fill: parent
                                cursorShape: Qt.SizeVerCursor
                                hoverEnabled: true
                            }
                        }

                        // 2. 账号纯净用户名 (截断与复制)
                        Text {
                            id: accountNameText
                            anchors.left: dragHandle.right
                            anchors.leftMargin: 2
                            anchors.right: (pinTopBtn.visible ? pinTopBtn.left : parent.right)
                            anchors.rightMargin: pinTopBtn.visible ? 4 : 2
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.displayUsername || ""
                            font.family: theme.uiFont
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            renderType: Text.NativeRendering
                            elide: Text.ElideRight
                            color: model.isActive ?
                                   ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF")

                            ToolTip.visible: nameMouse.containsMouse && !pinTopMouse.containsMouse && !dragMouse.containsMouse
                            ToolTip.text: (model.email || "") + " (" + qsTr("Click to copy") + ")"
                        }

                        MouseArea {
                            id: nameMouse
                            anchors.left: dragHandle.right
                            anchors.right: (pinTopBtn.visible ? pinTopBtn.left : parent.right)
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (backend && typeof backend.copyToClipboard === "function") {
                                    backend.copyToClipboard(model.email);
                                }
                            }
                        }

                        // 3. 悬浮 [置顶] 按钮 (非在用且非首行悬浮显现)
                        Rectangle {
                            id: pinTopBtn
                            anchors.right: parent.right
                            anchors.rightMargin: 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: 34
                            height: 18
                            radius: 0
                            visible: rowMouse.containsMouse && !model.isActive && index > 0
                            color: pinTopMouse.containsMouse ?
                                   ((theme && theme.surface3) ? theme.surface3 : "#3c3836") :
                                   ((theme && theme.surface2) ? theme.surface2 : "#1c1c1c")
                            border.width: 1
                            border.color: pinTopMouse.containsMouse ?
                                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                          ((theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#3c3836")

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("置顶")
                                font.family: theme.uiFont
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
                                color: pinTopMouse.containsMouse ?
                                       ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                       ((theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6")
                            }

                            MouseArea {
                                id: pinTopMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                ToolTip.visible: containsMouse
                                ToolTip.text: qsTr("Pin to top")
                                onClicked: {
                                    accountListView.moveAccountToTop(model.email);
                                }
                            }
                        }
                    }

                    // Hairline between Col 4 and Col 5
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 1
                        Layout.maximumWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 5: Gemini 4 配额单元格 (彻底移除 周 徽标，原生进度条、数值与倒计时)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colG4Width
                        Layout.minimumWidth: colG4Width
                        Layout.maximumWidth: colG4Width
                        Layout.fillHeight: true

                        // 账号无 Gemini 4 权限：优雅呈现中线 —
                        Text {
                            anchors.centerIn: parent
                            visible: !model.gemini4Valid
                            text: "—"
                            font.family: theme.monoFont
                            font.pixelSize: 14
                            renderType: Text.NativeRendering
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
                                Layout.preferredHeight: 5
                                height: 5
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
                                font.family: theme.monoFont
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
                                horizontalAlignment: Text.AlignRight
                                color: accountListView.getQuotaColor(model.gemini4Quota)
                            }

                            // 3. 重置倒计时槽位 (54px 零截断)
                            Text {
                                Layout.preferredWidth: 54
                                text: model.gemini4Reset || "—"
                                font.family: theme.monoFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
                                color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : ((theme && theme.mode === "light") ? "#0F172A" : "#FFFFFF")
                                horizontalAlignment: Text.AlignRight
                                elide: Text.ElideNone
                            }
                        }
                    }

                    // Hairline between Col 5 and Col 6
                    Rectangle {
                        width: 1
                        Layout.preferredWidth: 1
                        Layout.minimumWidth: 1
                        Layout.maximumWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 6: Gemini 3.8 双维配额单元格 (带周耗尽 0.0% 熔断)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colG38Width
                        Layout.minimumWidth: colG38Width
                        Layout.maximumWidth: colG38Width
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 10
                            anchors.topMargin: 2
                            anchors.bottomMargin: 2
                            spacing: 1

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 20
                                    height: 14
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5H"
                                        font.family: theme.monoFont
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        renderType: Text.NativeRendering
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : ((theme && theme.mode === "light") ? "#212121" : "#F3F4F6")
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 5
                                    height: 5
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
                                    Layout.preferredWidth: 44
                                    text: (model.gemini38QuotaW <= 0.0001) ? "0.0%" :
                                          (((model.gemini38Quota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           accountListView.getQuotaColor(model.gemini38Quota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: (model.gemini38QuotaW <= 0.0001) ? qsTr("周耗尽") : (model.gemini38Reset5h || "—")
                                    font.family: theme.monoFont
                                    font.pixelSize: 11
                                    font.weight: (model.gemini38QuotaW <= 0.0001) ? Font.Bold : Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : ((theme && theme.mode === "light") ? "#0F172A" : "#FFFFFF"))
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideNone
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 20
                                    height: 14
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "W"
                                        font.family: theme.monoFont
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        renderType: Text.NativeRendering
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : ((theme && theme.mode === "light") ? "#212121" : "#F3F4F6")
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 5
                                    height: 5
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
                                    Layout.preferredWidth: 44
                                    text: ((model.gemini38QuotaW || 0.0) * 100).toFixed(1) + "%"
                                    font.family: theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.gemini38QuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: model.gemini38ResetW || "—"
                                    font.family: theme.monoFont
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : ((theme && theme.mode === "light") ? "#0F172A" : "#FFFFFF")
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
                        Layout.minimumWidth: 1
                        Layout.maximumWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 7: Claude 双维配额单元格
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colClaudeWidth
                        Layout.minimumWidth: colClaudeWidth
                        Layout.maximumWidth: colClaudeWidth
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 10
                            anchors.topMargin: 2
                            anchors.bottomMargin: 2
                            spacing: 1

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 20
                                    height: 14
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5H"
                                        font.family: theme.monoFont
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        renderType: Text.NativeRendering
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : ((theme && theme.mode === "light") ? "#212121" : "#F3F4F6")
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 5
                                    height: 5
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
                                    Layout.preferredWidth: 44
                                    text: (model.claudeQuotaW <= 0.0001) ? "0.0%" :
                                          (((model.claudeQuota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           accountListView.getQuotaColor(model.claudeQuota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: (model.claudeQuotaW <= 0.0001) ? qsTr("周耗尽") : (model.claudeReset5h || "—")
                                    font.family: theme.monoFont
                                    font.pixelSize: 11
                                    font.weight: (model.claudeQuotaW <= 0.0001) ? Font.Bold : Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a") :
                                           ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : ((theme && theme.mode === "light") ? "#0F172A" : "#FFFFFF"))
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideNone
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 20
                                    height: 14
                                    radius: 0
                                    color: (theme && theme.pillBg && theme.pillBg.charAt(0) === '#') ? theme.pillBg : "#12ffffff"
                                    border.width: 1
                                    border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "W"
                                        font.family: theme.monoFont
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        renderType: Text.NativeRendering
                                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : ((theme && theme.mode === "light") ? "#212121" : "#F3F4F6")
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitWidth: 64
                                    Layout.minimumWidth: 48
                                    Layout.preferredHeight: 5
                                    height: 5
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
                                    Layout.preferredWidth: 44
                                    text: ((model.claudeQuotaW || 0.0) * 100).toFixed(1) + "%"
                                    font.family: theme.monoFont
                                    font.pixelSize: 12
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.claudeQuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 54
                                    text: model.claudeResetW || "—"
                                    font.family: theme.monoFont
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : ((theme && theme.mode === "light") ? "#0F172A" : "#FFFFFF")
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
                        Layout.minimumWidth: 1
                        Layout.maximumWidth: 1
                        Layout.fillHeight: true
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6
                        radius: 0
                        color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"
                    }

                    // -------------------------------------------------
                    // Col 8: 快速操作按钮组 (82px 纯直角长方形)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: colActionWidth
                        Layout.minimumWidth: colActionWidth
                        Layout.maximumWidth: colActionWidth
                        Layout.fillHeight: true

                        // 1. 在用徽章 (ACTIVE 状态) - Marker 6: theme.accent, 严禁 goodText 绿色
                        Rectangle {
                            anchors.centerIn: parent
                            visible: model.isActive
                            width: 52
                            height: 24
                            radius: 0
                            color: Qt.alpha((theme && theme.accent) ? theme.accent : "#7daea3", 0.15)
                            border.width: 1
                            border.color: (theme && theme.accent) ? theme.accent : "#7daea3"

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("In Use")
                                font.family: theme.uiFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
                                color: (theme && theme.accentText) ? theme.accentText : ((theme && theme.accent) ? theme.accent : "#7daea3")
                            }
                        }

                        // 2. 解封按钮 (BLOCKED 状态)
                        Rectangle {
                            anchors.centerIn: parent
                            visible: !model.isActive && model.isBlocked
                            width: 52
                            height: 24
                            radius: 0
                            color: Qt.alpha((theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a", 0.15)
                            border.width: 1
                            border.color: (theme && theme.dangerText && theme.dangerText.charAt(0) === '#') ? theme.dangerText : "#ff5f4a"

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("Unblock")
                                font.family: theme.uiFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
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
                            width: 52
                            height: 24
                            radius: 0
                            color: btnSwitchMouse.containsMouse ?
                                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                                   ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26")
                            border.width: 1
                            border.color: btnSwitchMouse.containsMouse ?
                                          ((theme && theme.accent) ? theme.accent : "#7daea3") :
                                          ((theme && theme.controlBorder && theme.controlBorder.charAt(0) === '#') ? theme.controlBorder : "#3dffffff")

                            Text {
                                anchors.centerIn: parent
                                text: qsTr("Switch")
                                font.family: theme.uiFont
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                renderType: Text.NativeRendering
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
        // 4. 底部极简状态与按键键帽导航栏 (Omarchy Full Chinese Footer Bar)
        // =============================================================
        Rectangle {
            id: bottomBar
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            radius: 0
            color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
            border.width: 1
            border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#1fffffff"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                // 左侧: 全池统计信息 (共 %1 个账号 · 可用 %2 · 显示 %3)
                Text {
                    text: qsTr("共 %1 个账号 · 可用 %2 · 显示 %3")
                          .arg((accountModel && typeof accountModel.count !== "undefined") ? accountModel.count : (accountModel ? accountModel.rowCount() : 0))
                          .arg(accountListView.availableCount)
                          .arg(accountListView.displayedCount)
                    font.family: theme.uiFont
                    font.pixelSize: 11
                    renderType: Text.NativeRendering
                    color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                }

                // 弹性推开间隔
                Item {
                    Layout.fillWidth: true
                }

                // 右侧: 直角按键键帽组 ([J/K] 移动选择  [Enter] 快速切换  [/] 搜索账号  [?] 快捷键帮助)
                RowLayout {
                    spacing: 12

                    Repeater {
                        model: [
                            { key: "J/K", label: qsTr("移动选择") },
                            { key: "Enter", label: qsTr("快速切换") },
                            { key: "/", label: qsTr("搜索账号") },
                            { key: "?", label: qsTr("快捷键帮助") }
                        ]

                        delegate: RowLayout {
                            spacing: 5

                            // 矩形直角键帽 (border: theme.hairline, background: theme.surface2, radius: 0)
                            Rectangle {
                                height: 16
                                implicitWidth: keycapText.implicitWidth + 8
                                radius: 0
                                color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a2c26"
                                border.width: 1
                                border.color: (theme && theme.hairline && theme.hairline.charAt(0) === '#') ? theme.hairline : "#3c3836"

                                Text {
                                    id: keycapText
                                    anchors.centerIn: parent
                                    text: modelData.key
                                    font.family: theme.monoFont
                                    font.pixelSize: 10
                                    font.weight: Font.DemiBold
                                    renderType: Text.NativeRendering
                                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                                }
                            }

                            // 快捷操作描述文本 (theme.uiFont, theme.text2)
                            Text {
                                text: modelData.label
                                font.family: theme.uiFont
                                font.pixelSize: 11
                                renderType: Text.NativeRendering
                                color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                            }
                        }
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
                    font.weight: Font.DemiBold
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
                        font.weight: Font.DemiBold
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
