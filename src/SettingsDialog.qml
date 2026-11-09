import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

Dialog {
    id: root

    title: ""
    header: null
    footer: null
    modal: true
    focus: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    x: Math.round(((parent ? parent.width : 540) - width) / 2)
    y: Math.round(((parent ? parent.height : 540) - height) / 2)
    width: Math.min(parent ? parent.width - 32 : 540, 520)

    signal settingsSaved(var settings)

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
        color: "#a6000000"
        Behavior on opacity { NumberAnimation { duration: 150 } }
    }

    onAboutToShow: loadCurrentSettings()

    function loadCurrentSettings() {
        var s = (backend && backend.settings) ? backend.settings : {};

        // 1. Rotation Strategy
        var strat = s.rotation_strategy || "highest-quota";
        for (var i = 0; i < strategyCombo.model.length; ++i) {
            if (strategyCombo.model[i].value === strat) {
                strategyCombo.currentIndex = i;
                break;
            }
        }

        // 2. Thresholds
        geminiSlider.value = (s.gemini_threshold !== undefined) ? s.gemini_threshold : 0.15;
        claudeSlider.value = (s.claude_threshold !== undefined) ? s.claude_threshold : 0.15;

        // 3. Switches
        prewarmSwitch.checked = (s.hourly_warmup !== undefined) ? s.hourly_warmup : true;
        notificationSwitch.checked = (s.notifications_enabled !== undefined) ? s.notifications_enabled : true;

        // 4. Language
        var lang = s.language || "system";
        for (var j = 0; j < languageCombo.model.length; ++j) {
            if (languageCombo.model[j].value === lang) {
                languageCombo.currentIndex = j;
                break;
            }
        }

        // 5. Theme Mode
        var thMode = s.theme_mode || (backend ? backend.themeMode : "system");
        for (var k = 0; k < themeModeCombo.model.length; ++k) {
            if (themeModeCombo.model[k].value === thMode) {
                themeModeCombo.currentIndex = k;
                break;
            }
        }

        // 6. Account Mask
        maskSwitch.checked = (backend ? backend.masked : false);
    }

    function saveAndApply() {
        var payload = {
            "rotation_strategy": strategyCombo.model[strategyCombo.currentIndex].value,
            "gemini_threshold": Number(geminiSlider.value.toFixed(2)),
            "claude_threshold": Number(claudeSlider.value.toFixed(2)),
            "hourly_warmup": prewarmSwitch.checked,
            "notifications_enabled": notificationSwitch.checked,
            "account_mask": maskSwitch.checked,
            "theme_mode": themeModeCombo.model[themeModeCombo.currentIndex].value,
            "language": languageCombo.model[languageCombo.currentIndex].value
        };

        if (backend) {
            backend.saveSettings(payload);
        }

        settingsSaved(payload);
        root.accept();
    }

    contentItem: ColumnLayout {
        spacing: 0

        // Dialog Header
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 48

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 12

                Text {
                    text: qsTr("Preferences")
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    Layout.fillWidth: true
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
                    onClicked: root.reject()
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                radius: 0
            }
        }

        // Form Body
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(formLayout.implicitHeight + 24, 460)
            clip: true

            ColumnLayout {
                id: formLayout
                width: parent.width - 24
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 16

                Item { Layout.preferredHeight: 4 }

                // 1. Rotation Strategy
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: qsTr("Auto-Rotation Strategy")
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }

                    ComboBox {
                        id: strategyCombo
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        textRole: "text"
                        valueRole: "value"
                        model: [
                            { text: qsTr("Highest Quota First"), value: "highest-quota" },
                            { text: qsTr("Round-Robin"), value: "round-robin" },
                            { text: qsTr("Least-Used"), value: "least-used" },
                            { text: qsTr("Sticky Current"), value: "sticky" }
                        ]

                        background: Rectangle {
                            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                            radius: 0
                            border.color: parent.activeFocus ?
                                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                          ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")
                            border.width: 1
                        }

                        contentItem: Text {
                            leftPadding: 10
                            rightPadding: 24
                            text: strategyCombo.displayText
                            font.pixelSize: 12
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }
                }

                // 2. Gemini Threshold
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: qsTr("Gemini Depletion Threshold")
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            Layout.fillWidth: true
                        }
                        Rectangle {
                            Layout.preferredWidth: 46
                            Layout.preferredHeight: 22
                            radius: 0
                            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                            border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: Math.round(geminiSlider.value * 100) + "%"
                                font.pixelSize: 11
                                font.family: "Monospace"
                                font.weight: Font.DemiBold
                                color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            }
                        }
                    }

                    Slider {
                        id: geminiSlider
                        Layout.fillWidth: true
                        from: 0.01
                        to: 0.50
                        stepSize: 0.01
                        value: 0.15

                        background: Rectangle {
                            x: geminiSlider.leftPadding
                            y: geminiSlider.topPadding + geminiSlider.availableHeight / 2 - height / 2
                            width: geminiSlider.availableWidth
                            height: 4
                            radius: 0
                            color: (theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b"

                            Rectangle {
                                width: geminiSlider.visualPosition * parent.width
                                height: parent.height
                                radius: 0
                                color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            }
                        }

                        handle: Rectangle {
                            x: geminiSlider.leftPadding + geminiSlider.visualPosition * (geminiSlider.availableWidth - width)
                            y: geminiSlider.topPadding + geminiSlider.availableHeight / 2 - height / 2
                            width: 14
                            height: 14
                            radius: 0
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            border.color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
                            border.width: 1
                        }
                    }
                }

                // 3. Claude Threshold
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: qsTr("Claude Depletion Threshold")
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            Layout.fillWidth: true
                        }
                        Rectangle {
                            Layout.preferredWidth: 46
                            Layout.preferredHeight: 22
                            radius: 0
                            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                            border.width: 1
                            Text {
                                anchors.centerIn: parent
                                text: Math.round(claudeSlider.value * 100) + "%"
                                font.pixelSize: 11
                                font.family: "Monospace"
                                font.weight: Font.DemiBold
                                color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            }
                        }
                    }

                    Slider {
                        id: claudeSlider
                        Layout.fillWidth: true
                        from: 0.01
                        to: 0.50
                        stepSize: 0.01
                        value: 0.15

                        background: Rectangle {
                            x: claudeSlider.leftPadding
                            y: claudeSlider.topPadding + claudeSlider.availableHeight / 2 - height / 2
                            width: claudeSlider.availableWidth
                            height: 4
                            radius: 0
                            color: (theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b"

                            Rectangle {
                                width: claudeSlider.visualPosition * parent.width
                                height: parent.height
                                radius: 0
                                color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            }
                        }

                        handle: Rectangle {
                            x: claudeSlider.leftPadding + claudeSlider.visualPosition * (claudeSlider.availableWidth - width)
                            y: claudeSlider.topPadding + claudeSlider.availableHeight / 2 - height / 2
                            width: 14
                            height: 14
                            radius: 0
                            color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                            border.color: (theme && theme.surface1 && theme.surface1.charAt(0) === '#') ? theme.surface1 : "#13141c"
                            border.width: 1
                        }
                    }
                }

                // 4. Hourly Fleet Prewarm Switch
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: qsTr("Hourly Fleet Prewarm")
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        }
                        Text {
                            text: qsTr("Keep dual-machine 16-channel warmup pipeline running hourly")
                            font.pixelSize: 11
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Switch {
                        id: prewarmSwitch
                        checked: true

                        indicator: Rectangle {
                            implicitWidth: 38
                            implicitHeight: 22
                            radius: 0
                            color: prewarmSwitch.checked ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b")
                            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                            border.width: 1

                            Rectangle {
                                x: prewarmSwitch.checked ? parent.width - width - 4 : 4
                                y: 4
                                width: 14
                                height: 14
                                radius: 0
                                color: prewarmSwitch.checked ?
                                       ((theme && theme.accentForeground && theme.accentForeground.charAt(0) === '#') ? theme.accentForeground : "#000000") :
                                       ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                Behavior on x { NumberAnimation { duration: 120 } }
                            }
                        }
                    }
                }

                // 5. Desktop Notifications Switch
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: qsTr("Desktop Notifications")
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        }
                        Text {
                            text: qsTr("Show system toast on account switch and quota depletion")
                            font.pixelSize: 11
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Switch {
                        id: notificationSwitch
                        checked: true

                        indicator: Rectangle {
                            implicitWidth: 38
                            implicitHeight: 22
                            radius: 0
                            color: notificationSwitch.checked ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#24283b")
                            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                            border.width: 1

                            Rectangle {
                                x: notificationSwitch.checked ? parent.width - width - 4 : 4
                                y: 4
                                width: 14
                                height: 14
                                radius: 0
                                color: notificationSwitch.checked ?
                                       ((theme && theme.accentForeground && theme.accentForeground.charAt(0) === '#') ? theme.accentForeground : "#000000") :
                                       ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                Behavior on x { NumberAnimation { duration: 120 } }
                            }
                        }
                    }
                }

                // 6. Mask Account Identifiers Switch (账号脱敏选项，默认关闭)
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: qsTr("Mask Account Identifiers")
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                        }
                        Text {
                            text: qsTr("Mask account usernames into c***8 format in table view")
                            font.pixelSize: 11
                            color: (theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1"
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Switch {
                        id: maskSwitch
                        checked: backend ? backend.masked : false
                        onToggled: {
                            if (backend) backend.setMasked(checked);
                        }

                        indicator: Rectangle {
                            implicitWidth: 38
                            implicitHeight: 22
                            radius: 0
                            color: maskSwitch.checked ?
                                   ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                   ((theme && theme.surface3 && theme.surface3.charAt(0) === '#') ? theme.surface3 : "#203b31")
                            border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                            border.width: 1

                            Rectangle {
                                x: maskSwitch.checked ? parent.width - width - 4 : 4
                                y: 4
                                width: 14
                                height: 14
                                radius: 0
                                color: maskSwitch.checked ?
                                       ((theme && theme.accentForeground && theme.accentForeground.charAt(0) === '#') ? theme.accentForeground : "#000000") :
                                       ((theme && theme.text3 && theme.text3.charAt(0) === '#') ? theme.text3 : "#CBD5E1")
                                Behavior on x { NumberAnimation { duration: 120 } }
                            }
                        }
                    }
                }

                // 7. Theme Mode Selection
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: qsTr("Theme")
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }

                    ComboBox {
                        id: themeModeCombo
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        textRole: "text"
                        valueRole: "value"
                        model: [
                            { text: qsTr("Follow System"), value: "system" },
                            { text: qsTr("Dark Mode"), value: "dark" },
                            { text: qsTr("Light Mode (White Theme)"), value: "light" }
                        ]

                        currentIndex: {
                            var m = backend ? backend.themeMode : "system";
                            if (m === "dark") return 1;
                            if (m === "light") return 2;
                            return 0;
                        }

                        onActivated: {
                            var val = model[currentIndex].value;
                            if (theme) theme.setThemeMode(val);
                        }

                        background: Rectangle {
                            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#142620"
                            radius: 0
                            border.color: parent.activeFocus ?
                                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                          ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")
                            border.width: 1
                        }

                        contentItem: Text {
                            leftPadding: 10
                            rightPadding: 24
                            text: themeModeCombo.displayText
                            font.pixelSize: 12
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }
                }

                // 8. Language Selection
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4

                    Text {
                        text: qsTr("Language")
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                    }

                    ComboBox {
                        id: languageCombo
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        textRole: "text"
                        valueRole: "value"
                        model: [
                            { text: qsTr("Follow System"), value: "system" },
                            { text: "English", value: "en" },
                            { text: "简体中文", value: "zh-CN" }
                        ]

                        background: Rectangle {
                            color: (theme && theme.surface2 && theme.surface2.charAt(0) === '#') ? theme.surface2 : "#1a1b26"
                            radius: 0
                            border.color: parent.activeFocus ?
                                          ((theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1") :
                                          ((theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff")
                            border.width: 1
                        }

                        contentItem: Text {
                            leftPadding: 10
                            rightPadding: 24
                            text: languageCombo.displayText
                            font.pixelSize: 12
                            color: (theme && theme.text1 && theme.text1.charAt(0) === '#') ? theme.text1 : "#FFFFFF"
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }
                }

                Item { Layout.preferredHeight: 4 }
            }
        }

        // Dialog Footer
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 52

            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: 1
                color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                radius: 0
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                Item { Layout.fillWidth: true }

                Button {
                    text: qsTr("Cancel")
                    Layout.preferredHeight: 32
                    flat: true
                    background: Rectangle {
                        color: parent.hovered ? "#0fffffff" : "transparent"
                        radius: 0
                        border.color: (theme && theme.border && theme.border.charAt(0) === '#') ? theme.border : "#14ffffff"
                        border.width: 1
                    }
                    contentItem: Text {
                        text: parent.text
                        color: (theme && theme.text2 && theme.text2.charAt(0) === '#') ? theme.text2 : "#F3F4F6"
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: root.reject()
                }

                Button {
                    text: qsTr("Save & Apply")
                    Layout.preferredHeight: 32
                    background: Rectangle {
                        color: (theme && theme.accent && theme.accent.charAt(0) === '#') ? theme.accent : "#8bcbb1"
                        radius: 0
                        opacity: parent.pressed ? 0.85 : (parent.hovered ? 0.95 : 1.0)
                    }
                    contentItem: Text {
                        text: parent.text
                        color: (theme && theme.accentForeground && theme.accentForeground.charAt(0) === '#') ? theme.accentForeground : "#000000"
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: root.saveAndApply()
                }
            }
        }
    }
}
