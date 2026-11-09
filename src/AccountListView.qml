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

    // 配额颜色判定阈值逻辑 (Omarchy Material Dark 规范)
    function getQuotaColor(ratio) {
        if (ratio === undefined || ratio === null || isNaN(ratio)) return "#565f89";
        if (ratio <= 0.0001) return "#565f89"; // 枯竭归零
        if (ratio >= 0.50) return "#22C55E";   // 充足 (翠绿)
        if (ratio >= 0.15) return "#F59E0B";   // 告急 (琥珀橙)
        return "#EF4444";                      // 危险 (玫瑰红)
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
            color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
            border.width: 1
            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

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

                // Col 2: # 序号
                Item {
                    Layout.preferredWidth: 36
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: "#"
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                    }
                }

                // Col 3: 状态
                Item {
                    Layout.preferredWidth: 88
                    Layout.fillHeight: true
                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Status")
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
                    }
                }

                // Col 4: 账号 (严格切除额外标签)
                Item {
                    Layout.preferredWidth: 130
                    Layout.fillHeight: true
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Account")
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                            font.pixelSize: 11
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "gemini4") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6")
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
                            font.pixelSize: 11
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "gemini38_w") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "gemini38_w") : false
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
                            font.pixelSize: 11
                            font.bold: true
                            color: (proxyModel && proxyModel.sortField === "claude_w") ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6")
                        }

                        Text {
                            visible: proxyModel ? (proxyModel.sortField === "claude_w") : false
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
                        font.pixelSize: 11
                        font.bold: true
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "📭"
                        font.pixelSize: 28
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTr("No matching accounts found")
                        font.pixelSize: 13
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
                    }
                }
            }

            // ---------------------------------------------------------
            // 3. 账号行委托 (Account Row Delegate)
            // ---------------------------------------------------------
            delegate: Rectangle {
                id: rowDelegate
                width: listView.width
                height: 54

                // 25 项 QML Role 绑定的直接消费
                property bool isRowActive: model.isActive || false
                property bool isRowBlocked: model.isBlocked || false
                property bool isRowSelected: listView.currentIndex === index
                property bool isRowChecked: accountListView.selectedEmails[model.email] === true

                // 行背景与高亮逻辑
                color: isRowActive ? "#1422C55E" :
                       (isRowSelected ? "#15FFD60A" :
                           (rowMouse.containsMouse ?
                               ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26") :
                               (index % 2 === 0 ?
                                   ((theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c") :
                                   ((theme && theme.background && theme.background.charAt(0) === '#') ? theme.background : "#0e0e14"))))

                border.width: isRowSelected ? 1 : 0
                border.color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A"

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 1
                    color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#10ffffff"
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
                    // Col 2: # 序号 (1-based)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 36
                        Layout.fillHeight: true
                        Text {
                            anchors.centerIn: parent
                            text: model.index
                            font.family: "Monospace"
                            font.pixelSize: 11
                            color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                        }
                    }

                    // -------------------------------------------------
                    // Col 3: 状态胶囊 (ACTIVE / STANDBY / BLOCKED / EXHAUSTED)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 88
                        Layout.fillHeight: true

                        Rectangle {
                            anchors.centerIn: parent
                            width: 82
                            height: 24
                            radius: 12

                            color: model.isActive ? "#2622C55E" :
                                   (model.isBlocked ? "#26EF4444" :
                                       (model.status === "EXHAUSTED" ? "#266B7280" : "#26565f89"))

                            border.width: 1
                            border.color: model.isActive ? "#22C55E" :
                                          (model.isBlocked ? "#EF4444" :
                                              (model.status === "EXHAUSTED" ? "#6B7280" :
                                                  ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")))

                            // ACTIVE 绿色呼吸光效
                            SequentialAnimation on opacity {
                                running: model.isActive
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.65; duration: 900; easing.type: Easing.InOutQuad }
                                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutQuad }
                            }

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 3

                                Text {
                                    text: model.isActive ? qsTr("ACTIVE") :
                                          (model.isBlocked ? qsTr("Blocked") :
                                              (model.status === "EXHAUSTED" ? qsTr("Exhausted") : qsTr("STANDBY")))
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    font.bold: true
                                    color: model.isActive ? "#22C55E" :
                                           (model.isBlocked ? "#EF4444" :
                                               (model.status === "EXHAUSTED" ? "#9CA3AF" :
                                                   ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6")))
                                }

                                // 人工保护倒计时标签
                                Text {
                                    visible: model.isActive && (model.manualLockRemaining > 0)
                                    text: "🔒" + (model.manualLockRemainingStr || "")
                                    font.family: "Monospace"
                                    font.pixelSize: 9
                                    color: "#F59E0B"
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 4: 账号名称 (用户铁律：严禁出现多余版本标签！)
                    // -------------------------------------------------
                    Item {
                        Layout.preferredWidth: 130
                        Layout.fillHeight: true

                        Text {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.name || ""
                            font.family: "Monospace"
                            font.pixelSize: 12
                            font.bold: model.isActive
                            elide: Text.ElideRight
                            color: model.isActive ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                   ((theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#ffffff")

                            ToolTip.visible: nameMouse.containsMouse
                            ToolTip.text: (model.email || "") + " (" + qsTr("Click to copy") + ")"
                        }

                        MouseArea {
                            id: nameMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                // 复制邮箱至系统剪贴板
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
                            color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
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
                                font.pixelSize: 11
                                horizontalAlignment: Text.AlignRight
                                color: accountListView.getQuotaColor(model.gemini4Quota)
                            }

                            // 3. 重置倒计时槽位
                            Text {
                                Layout.preferredWidth: 48
                                text: model.gemini4Reset || "--"
                                font.family: "Monospace"
                                font.pixelSize: 10
                                color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                                        font.pixelSize: 9
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                                        color: (model.gemini38QuotaW <= 0.0001) ? "#EF4444" :
                                               accountListView.getQuotaColor(model.gemini38Quota5h)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: (model.gemini38QuotaW <= 0.0001) ? "0.0%" :
                                          (((model.gemini38Quota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.gemini38QuotaW <= 0.0001) ? "#EF4444" :
                                           accountListView.getQuotaColor(model.gemini38Quota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: (model.gemini38QuotaW <= 0.0001) ? qsTr("Weekly Depleted") : (model.gemini38Reset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 9
                                    color: (model.gemini38QuotaW <= 0.0001) ? "#EF4444" :
                                           ((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89")
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
                                        font.pixelSize: 9
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.gemini38QuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: model.gemini38ResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 9
                                    color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }

                    // -------------------------------------------------
                    // Col 7: Claude 双维配额单元格 (带周耗尽 0.0% 熔断)
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
                                        font.pixelSize: 9
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                                        color: (model.claudeQuotaW <= 0.0001) ? "#EF4444" :
                                               accountListView.getQuotaColor(model.claudeQuota5h)
                                    }
                                }

                                Text {
                                    Layout.preferredWidth: 42
                                    text: (model.claudeQuotaW <= 0.0001) ? "0.0%" :
                                          (((model.claudeQuota5h || 0.0) * 100).toFixed(1) + "%")
                                    font.family: "Monospace"
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    color: (model.claudeQuotaW <= 0.0001) ? "#EF4444" :
                                           accountListView.getQuotaColor(model.claudeQuota5h)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: (model.claudeQuotaW <= 0.0001) ? qsTr("Weekly Depleted") : (model.claudeReset5h || "--")
                                    font.family: "Monospace"
                                    font.pixelSize: 9
                                    color: (model.claudeQuotaW <= 0.0001) ? "#EF4444" :
                                           ((theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89")
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
                                        font.pixelSize: 9
                                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
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
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    color: accountListView.getQuotaColor(model.claudeQuotaW)
                                }

                                Text {
                                    Layout.preferredWidth: 46
                                    text: model.claudeResetW || "--"
                                    font.family: "Monospace"
                                    font.pixelSize: 9
                                    color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
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
                                radius: 4
                                color: "#2022C55E"
                                border.width: 1
                                border.color: "#22C55E"

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("In Use")
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: "#22C55E"
                                }
                            }

                            // 2. 解封按钮 (BLOCKED 状态)
                            Rectangle {
                                visible: !model.isActive && model.isBlocked
                                width: 56
                                height: 26
                                radius: 4
                                color: "#26EF4444"
                                border.width: 1
                                border.color: "#EF4444"

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("Unblock")
                                    font.pixelSize: 11
                                    font.bold: true
                                    color: "#EF4444"
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
                                width: 56
                                height: 26
                                radius: 4
                                color: btnSwitchMouse.containsMouse ?
                                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") :
                                       ((theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26")
                                border.width: 1
                                border.color: btnSwitchMouse.containsMouse ?
                                              ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#FFD60A") :
                                              ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")

                                Text {
                                    anchors.centerIn: parent
                                    text: qsTr("Switch")
                                    font.pixelSize: 11
                                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#ffffff"
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
                                width: 26
                                height: 26
                                radius: 4
                                color: warmupMouse.containsMouse ?
                                       ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b") : "transparent"
                                border.width: 1
                                border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"

                                Text {
                                    anchors.centerIn: parent
                                    text: "⚡"
                                    font.pixelSize: 11
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
                        color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                    }
                    Text {
                        text: "·"
                        color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                    }
                    Text {
                        text: qsTr("%1 / %2 pages").arg(1).arg(Math.max(1, Math.ceil((proxyModel ? proxyModel.filteredCount : 0) / 15)))
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#a9b1d6"
                    }
                    Text {
                        text: "·"
                        color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                    }
                    Text {
                        text: qsTr("%n item(s)", "", (proxyModel ? proxyModel.filteredCount : 0))
                        font.family: "Monospace"
                        font.pixelSize: 11
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#c0caf5"
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
                            color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
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
                            color: (theme && theme.text4 && theme.text4.charAt(0) === '#') ? theme.text4 : "#565f89"
                        }
                    }
                }
            }
        }
    }
}
