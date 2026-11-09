import QtQuick

// A bundled line icon, tinted with any theme color via IconProvider
Item {
    id: root
    property string name: ""
    property color tint: (typeof theme !== "undefined" && theme && theme.text1) ? theme.text1 : "#f5f5f7"
    property int size: 16
    property bool mirror: false

    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    Image {
        anchors.fill: parent
        sourceSize.width: root.size * 2
        sourceSize.height: root.size * 2
        smooth: true
        fillMode: Image.PreserveAspectFit
        mirror: root.mirror
        source: root.name.length ? "image://icons/" + root.name + "?color=" + root.tint.toString().replace("#", "") : ""
    }
}
