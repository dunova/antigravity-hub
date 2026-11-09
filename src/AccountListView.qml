import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: accountListView

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
        if (ratio === undefined || ratio === null || isNaN(ratio)) return (theme && theme.text3) ? theme.text3 : "#CBD5E1";
        if (ratio <= 0.0001) return (theme && theme.dangerText) ? theme.dangerText : "#FF6B6B"; // 枯竭归零高对比红标告警
        if (ratio >= 0.50) return (theme && theme.goodText) ? theme.goodText : "#4ADE80";       // 充足 (高对比亮绿)
        if (ratio >= 0.15) return (theme && theme.warningText) ? theme.warningText : "#FFD166"; // 告急 (高对比金橙)
        return (theme && theme.dangerText) ? theme.dangerText : "#FF6B6B";                      // 危险 (高对比亮珊瑚红)
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
            radius: theme ? theme.controlRadius : 6
            gradient: Gradient {
                GradientStop { position: 0; color: (theme && theme.surfaceTop) ? theme.surfaceTop : "#172c25" }
                GradientStop { position: 1; color: (theme && theme.surfaceBottom) ? theme.surfaceBottom : "#11201b" }
            }
            border.width: 1
            border.color: (theme && theme.hairline) ? theme.hairline : "rgba(255, 255, 255, 0.12)"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 8

                // Col 1: 全选复选框
                Item {
                    Layout.preferredWidth: 34
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
                    Layout.preferredWidth: 36
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
                    Layout.preferredWidth: 88
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
                    Layout.preferredWidth: 170
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

                // Col 5: Gemini 4 (用户最高铁律门禁：严格命名为 Gemini 4，彻底切除周标签)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 160
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
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
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A"
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

                // Col 6: Gemini 3.8 双维配额表头
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 175
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
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

                // Col 7: Claude 双维配额表头
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 175
                    Layout.fillHeight: true
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
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

                // Col 8: 操作
                Item {
                    Layout.preferredWidth: 145
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Actions")
                        font.pixelSize: 12
                        font.bold: true
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#ffffff"
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

                // 25 项 QML Role 绑定的直接消费
                property bool isRowActive: model.isActive || false
                property bool isRowBlocked: model.isBlocked || false
                property bool isRowSelected: listView.currentIndex === index
                property bool isRowChecked: accountListView.selectedEmails[model.email] === true

                // 行背景与高亮逻辑 (加重奇偶斑马纹，提高行条目可视率与辨识度)
                color: isRowActive ?
                       ((theme && theme.mode === "light") ?
                           Qt.alpha((theme && theme.goodText) ? theme.goodText : "#16A34A", 0.15) :
                           Qt.alpha((theme && theme.goodText) ? theme.goodText : "#4ADE80", 0.18)) :
                       (isRowSelected ?
                           ((theme && theme.mode === "light") ?
                               Qt.alpha((theme && theme.accent) ? theme.accent : "#0284C7", 0.20) :
                               Qt.alpha((theme && theme.accent) ? theme.accent : "#8bcbb1", 0.25)) :
                           (rowMouse.containsMouse ?
                               ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#243c34") :
                               ((theme && theme.mode === "light") ?
                                   (index % 2 === 0 ? "#FFFFFF" : "#F1F5F9") :
                                   (index % 2 === 0 ?
                                       ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#0f1e19") :
                                       Qt.tint(((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#0f1e19"), "rgba(255, 255, 255, 0.08)")))))

                border.width: isRowSelected ? 1 : 0
                border.color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: (theme && theme.hairline) ? theme.hairline : "rgba(255, 255, 255, 0.08)"
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
                    spacing: 8

                    // -------------------------------------------------
                    // Col 1: 行复选框
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 34
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
                        Layout.preferredWidth: 36
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
                    // Col 3: 状态胶囊 (ACTIVE / STANDBY / BLOCKED / EXHAUSTED - 静态无多余动画)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 88
                        Layout.fillHeight: true

                        Rectangle {
                            anchors.centerIn: parent
                            width: 82
                            height: 24
                            radius: 12

                            color: model.isActive ?
                                   Qt.alpha((theme && theme.goodText) ? theme.goodText : "#4ADE80", 0.18) :
                                   (model.isBlocked ?
                                       Qt.alpha((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B", 0.18) :
                                       (model.status === "EXHAUSTED" ?
                                           Qt.alpha((theme && theme.text4) ? theme.text4 : "#6B7280", 0.15) :
                                           ((theme && theme.mode === "light") ? "#0a000000" : "#14ffffff")))

                            border.width: 1
                            border.color: model.isActive ? ((theme && theme.goodText) ? theme.goodText : "#4ADE80") :
                                          (model.isBlocked ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                              (model.status === "EXHAUSTED" ? ((theme && theme.text4) ? theme.text4 : "#6B7280") :
                                                  ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")))

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
                                    color: model.isActive ? ((theme && theme.goodText) ? theme.goodText : "#4ADE80") :
                                           (model.isBlocked ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                               (model.status === "EXHAUSTED" ? ((theme && theme.text3) ? theme.text3 : "#CBD5E1") :
                                                   ((theme && theme.text2) ? theme.text2 : "#F3F4F6")))
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
                        Layout.preferredWidth: 170
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
                                // 复制完整真实邮箱至系统剪贴板
                                if (backend && typeof backend.copyToClipboard === "function") {
                                    backend.copyToClipboard(model.email);
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 5: Gemini 4 配额单元格 (彻底移除 周 徽标，仅保留原生进度条、数值与倒计时)
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 160
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
                            visible: model.gemini4Valid
                            spacing: 6

                            // 1. 原生平滑进度条 (无任何 '周' 徽标前缀)
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 6
                                radius: 3
                                color: "#14ffffff"

                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    radius: 3
                                    width: Math.min(parent.width, Math.max(0, parent.width * (model.gemini4Quota || 0.0)))
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

                            // 3. 重置倒计时槽位
                            Text {
                                Layout.preferredWidth: 48
                                text: model.gemini4Reset || "--"
                                font.family: "Monospace"
                                font.pixelSize: 11
                                color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                elide: Text.ElideRight
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 6: Gemini 3.8 双维配额单元格 (带周耗尽 0.0% 熔断)
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 175
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            spacing: 3

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 18
                                    height: 14
                                    radius: 3
                                    color: "#14ffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5h"
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 4
                                    radius: 2
                                    color: "#14ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 2
                                        width: (model.gemini38QuotaW <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(0, parent.width * (model.gemini38Quota5h || 0.0)))
                                        color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
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
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                           accountListView.getQuotaColor(model.gemini38Quota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: (model.gemini38QuotaW <= 0.0001) ? qsTr("Weekly Depleted") : (model.gemini38Reset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 11
                                    color: (model.gemini38QuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                           ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                    elide: Text.ElideRight
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 18
                                    height: 14
                                    radius: 3
                                    color: "#14ffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: qsTr("Weekly")
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 4
                                    radius: 2
                                    color: "#14ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 2
                                        width: Math.min(parent.width, Math.max(0, parent.width * (model.gemini38QuotaW || 0.0)))
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
                                    Layout.preferredWidth: 46
                                    text: model.gemini38ResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 11
                                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 7: Claude 双维配额单元格
                    // -------------------------------------------------
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 175
                        Layout.fillHeight: true

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.topMargin: 4
                            anchors.bottomMargin: 4
                            spacing: 3

                            // 上轨: 5小时滑动窗口
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 18
                                    height: 14
                                    radius: 3
                                    color: "#14ffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: "5h"
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 4
                                    radius: 2
                                    color: "#14ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 2
                                        width: (model.claudeQuotaW <= 0.0001) ? 0 :
                                               Math.min(parent.width, Math.max(0, parent.width * (model.claudeQuota5h || 0.0)))
                                        color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
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
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                           accountListView.getQuotaColor(model.claudeQuota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: (model.claudeQuotaW <= 0.0001) ? qsTr("Weekly Depleted") : (model.claudeReset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 11
                                    color: (model.claudeQuotaW <= 0.0001) ? ((theme && theme.dangerText) ? theme.dangerText : "#FF6B6B") :
                                           ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                    elide: Text.ElideRight
                                }
                            }

                            // 下轨: 周度总配额
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 5

                                Rectangle {
                                    width: 18
                                    height: 14
                                    radius: 3
                                    color: "#14ffffff"
                                    Text {
                                        anchors.centerIn: parent
                                        text: qsTr("Weekly")
                                        font.pixelSize: 10
                                        font.bold: true
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 4
                                    radius: 2
                                    color: "#14ffffff"

                                    Rectangle {
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        radius: 2
                                        width: Math.min(parent.width, Math.max(0, parent.width * (model.claudeQuotaW || 0.0)))
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
                                    Layout.preferredWidth: 46
                                    text: model.claudeResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 11
                                    color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 8: 快速操作按钮组
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 145
                        Layout.fillHeight: true

                        RowLayout {
                            anchors.centerIn: parent
                            spacing: 6

                            // 1. 在用徽章 (ACTIVE 状态)
                            Rectangle {
                                visible: model.isActive
                                width: 56
                                height: 26
                                radius: theme ? theme.controlRadius : 6
                                color: Qt.alpha((theme && theme.goodText) ? theme.goodText : "#4ADE80", 0.15)
                                border.width: 1
                                border.color: (theme && theme.goodText) ? theme.goodText : "#4ADE80"

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("In Use")
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: (theme && theme.goodText) ? theme.goodText : "#4ADE80"
                                }
                            }

                            // 2. 解封按钮 (BLOCKED 状态)
                            Rectangle {
                                visible: !model.isActive && model.isBlocked
                                width: 56
                                height: 26
                                radius: theme ? theme.controlRadius : 6
                                color: (theme && theme.mode === "light") ? "#14DC2626" : "#26FF6B6B"
                                border.width: 1
                                border.color: (theme && theme.dangerText) ? theme.dangerText : "#FF6B6B"

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("Unblock")
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: (theme && theme.dangerText) ? theme.dangerText : "#FF6B6B"
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (backend) backend.unblockAccount(model.email);
                                    }
                                }
                            }

                            // 3. 切换按钮 (STANDBY 状态)
                            Rectangle {
                                id: btnSwitch
                                visible: !model.isActive && !model.isBlocked
                                width: 58
                                height: 28
                                radius: theme ? theme.controlRadius : 6
                                color: btnSwitchMouse.containsMouse ?
                                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                                       ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26")
                                border.width: 1
                                border.color: btnSwitchMouse.containsMouse ?
                                              ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                              ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")

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
                                        if (backend) backend.switchAccount(model.email);
                                    }
                                }
                            }

                            // 4. 错峰预热图标按钮
                            Rectangle {
                                id: btnWarmup
                                width: 28
                                height: 28
                                radius: theme ? theme.controlRadius : 6
                                color: warmupMouse.containsMouse ?
                                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") : "transparent"
                                border.width: 1
                                border.color: warmupMouse.containsMouse ?
                                              ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                              ((theme && theme.controlBorder) ? theme.controlBorder : "rgba(255, 255, 255, 0.24)")

                                AppIcon {
                                    anchors.centerIn: parent
                                    name: "sparkle"
                                    size: 14
                                    tint: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                                }

                                ToolTip.visible: warmupMouse.containsMouse
                                ToolTip.text: qsTr("Warmup")

                                MouseArea {
                                    id: warmupMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (backend) backend.triggerPrewarm();
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // =============================================================
        // 4. 底部状态与分页控制条 (Bottom Status & Pagination Bar)
        // =============================================================
        Rectangle {
            id: bottomBar
            Layout.fillWidth: true
            Layout.preferredHeight: 32
            color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
            border.width: 1
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 8

                // 统计信息
                RowLayout {
                    spacing: 6
                    Text {
                        text: qsTr("15 / page")
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                    Text {
                        text: "·"
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                    Text {
                        text: qsTr("%1 / %2 pages").arg(1).arg(Math.max(1, Math.ceil((proxyModel ? proxyModel.filteredCount : 0) / 15)))
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                    }
                    Text {
                        text: "·"
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                    }
                    Text {
                        text: qsTr("%n item(s)", "", (proxyModel ? proxyModel.filteredCount : 0))
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }
                }

                Item {
                    Layout.fillWidth: true
                }

                // 简易分页按钮
                RowLayout {
                    spacing: 6

                    Rectangle {
                        width: 70
                        height: 22
                        radius: 3
                        color: "transparent"
                        border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                        opacity: 0.5 // 单页模式置灰

                        Text {
                            anchors.centerIn: parent
                            text: qsTr("Previous")
                            font.pixelSize: 10
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                        }
                    }

                    Rectangle {
                        width: 70
                        height: 22
                        radius: 3
                        color: "transparent"
                        border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                        opacity: 0.5 // 单页模式置灰

                        Text {
                            anchors.centerIn: parent
                            text: qsTr("Next")
                            font.pixelSize: 10
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#9CA3AF"
                        }
                    }
                }
            }
        }
    }
}
