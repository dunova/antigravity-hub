#include "theme.h"

#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMap>
#include <QRegularExpression>
#include <QStandardPaths>
#include <cmath>

Theme::Theme(const QString &directory, QObject *parent, const QString &hyprctl)
    : QObject(parent),
      m_directory(directory.isEmpty() ? QDir::homePath() + "/.local/state/omarchy/current" : directory) {

    // 80ms single-shot debounce timer
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(80);
    connect(&m_watcher, &QFileSystemWatcher::directoryChanged, this, [this] { m_debounce.start(); });
    connect(&m_watcher, &QFileSystemWatcher::fileChanged, this, [this] { m_debounce.start(); });
    connect(&m_debounce, &QTimer::timeout, this, &Theme::reload);

    // Hyprland rounding process setup
    m_hyprctl = !hyprctl.isEmpty() ? hyprctl
              : directory.isEmpty() && !qEnvironmentVariableIsEmpty("HYPRLAND_INSTANCE_SIGNATURE")
                  ? QStandardPaths::findExecutable("hyprctl") : QString();

    m_roundingTimeout.setSingleShot(true);
    m_roundingTimeout.setInterval(500);
    connect(&m_roundingTimeout, &QTimer::timeout, &m_roundingProcess, &QProcess::kill);
    connect(&m_roundingProcess, &QProcess::errorOccurred, this, [this] { m_roundingTimeout.stop(); });
    connect(&m_roundingProcess, &QProcess::finished, this, [this](int code, QProcess::ExitStatus status) {
        m_roundingTimeout.stop();
        if (code != 0 || status != QProcess::NormalExit)
            return;
        const auto doc = QJsonDocument::fromJson(m_roundingProcess.readAllStandardOutput());
        const auto val = doc.object().value("int");
        if (val.isDouble() && val.toInt(-1) >= 0) {
            const int newRadius = val.toInt();
            if (newRadius != m_radius) {
                m_radius = newRadius;
                emit changed();
            }
        }
    });

    m_roundingPoll.setInterval(1000);
    connect(&m_roundingPoll, &QTimer::timeout, this, &Theme::refreshRounding);
    if (!m_hyprctl.isEmpty())
        m_roundingPoll.start();

    reload();
}

Theme::~Theme() {
    if (m_roundingProcess.state() != QProcess::NotRunning) {
        m_roundingProcess.kill();
        m_roundingProcess.waitForFinished(1000);
    }
}

void Theme::refreshRounding() {
    if (m_hyprctl.isEmpty() || m_roundingProcess.state() != QProcess::NotRunning)
        return;
    m_roundingProcess.start(m_hyprctl, {"-j", "getoption", "decoration:rounding"});
    m_roundingTimeout.start();
}

QString Theme::accentForeground() const {
    const QColor c(m_accent);
    if (!c.isValid())
        return "black";

    auto linear = [](double v) {
        return v <= 0.04045 ? v / 12.92 : std::pow((v + 0.055) / 1.055, 2.4);
    };

    const double luminance = 0.2126 * linear(c.redF()) +
                             0.7152 * linear(c.greenF()) +
                             0.0722 * linear(c.blueF());

    return luminance > 0.179 ? "black" : "white";
}

void Theme::parsePalette(const QString &path,
                         QString &mode, QString &accent, QString &selection, QString &muted,
                         QString &background, QString &surface1, QString &surface2, QString &surface3,
                         QString &text1, QString &text2, QString &text3, QString &text4, QString &border) {
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return;

    QMap<QString, QString> raw;
    const QRegularExpression re(R"(^\s*([a-zA-Z0-9_-]+)\s*=\s*["']([^"']+)["'])");
    while (!file.atEnd()) {
        const QString line = QString::fromUtf8(file.readLine()).trimmed();
        if (line.isEmpty() || line.startsWith('#'))
            continue;
        const auto match = re.match(line);
        if (match.hasMatch()) {
            raw[match.captured(1)] = match.captured(2);
        }
    }

    if (raw.contains("mode")) mode = raw["mode"];
    if (raw.contains("accent")) accent = raw["accent"];
    if (raw.contains("selection")) selection = raw["selection"];
    if (raw.contains("muted")) muted = raw["muted"];

    // Canvas Background: darker_background (preferred base) -> background
    if (raw.contains("darker_background")) background = raw["darker_background"];
    else if (raw.contains("background")) background = raw["background"];

    // Surface 1 (Cards, list rows): dark_background
    if (raw.contains("surface1")) surface1 = raw["surface1"];
    else if (raw.contains("dark_background")) surface1 = raw["dark_background"];
    else surface1 = background;

    // Surface 2 (Headers, search box, active items): background
    if (raw.contains("surface2")) surface2 = raw["surface2"];
    else if (raw.contains("background")) surface2 = raw["background"];
    else surface2 = surface1;

    // Surface 3 (Elevated hover, popovers, dialogs): lighter_background
    if (raw.contains("surface3")) surface3 = raw["surface3"];
    else if (raw.contains("lighter_background")) surface3 = raw["lighter_background"];
    else surface3 = surface2;

    // Text 1 (High-contrast, headings, quota values): bright_foreground
    if (raw.contains("text1")) text1 = raw["text1"];
    else if (raw.contains("bright_foreground")) text1 = raw["bright_foreground"];
    else if (raw.contains("foreground")) text1 = raw["foreground"];

    // Text 2 (Standard body text, column headers): foreground
    if (raw.contains("text2")) text2 = raw["text2"];
    else if (raw.contains("foreground")) text2 = raw["foreground"];

    // Text 3 (Secondary text, reset countdowns): light_foreground
    if (raw.contains("text3")) text3 = raw["text3"];
    else if (raw.contains("light_foreground")) text3 = raw["light_foreground"];
    else text3 = text2;

    // Text 4 (Tertiary text, muted, disabled, placeholders): dark_foreground / muted
    if (raw.contains("text4")) text4 = raw["text4"];
    else if (raw.contains("dark_foreground")) text4 = raw["dark_foreground"];
    else if (raw.contains("muted")) text4 = raw["muted"];
    else text4 = text3;

    // Border: explicit 'border' or subtle rgba separator
    if (raw.contains("border")) border = raw["border"];
    else border = (mode == "light") ? "rgba(0, 0, 0, 0.08)" : "rgba(255, 255, 255, 0.08)";
}

void Theme::reload() {
    refreshRounding();

    // 1. Unload stale inotify watches
    const auto paths = m_watcher.files() + m_watcher.directories();
    if (!paths.isEmpty())
        m_watcher.removePaths(paths);

    // 2. Walk up to nearest existing ancestor directory
    QString ancestor = m_directory;
    while (!QFileInfo::exists(ancestor) && ancestor != "/")
        ancestor = QFileInfo(ancestor).absolutePath();

    // 3. Register watch candidates
    QStringList candidates{
        ancestor,
        QFileInfo(ancestor).absolutePath(),
        m_directory,
        m_directory + "/theme",
        m_directory + "/theme/colors.toml",
        m_directory + "/theme.generation"
    };
    candidates.removeDuplicates();
    for (const auto &path : candidates) {
        if (QFileInfo::exists(path))
            m_watcher.addPath(path);
    }

    // 4. Parse colors.toml
    const QString colorsPath = m_directory + "/theme/colors.toml";
    QString mode = m_mode, accent = m_accent, selection = m_selection, muted = m_muted;
    QString background = m_background, surface1 = m_surface1, surface2 = m_surface2, surface3 = m_surface3;
    QString text1 = m_text1, text2 = m_text2, text3 = m_text3, text4 = m_text4, border = m_border;

    parsePalette(colorsPath, mode, accent, selection, muted,
                 background, surface1, surface2, surface3,
                 text1, text2, text3, text4, border);

    bool hasChanged = (mode != m_mode || accent != m_accent || selection != m_selection || muted != m_muted ||
                       background != m_background || surface1 != m_surface1 || surface2 != m_surface2 || surface3 != m_surface3 ||
                       text1 != m_text1 || text2 != m_text2 || text3 != m_text3 || text4 != m_text4 || border != m_border);

    if (hasChanged) {
        m_mode = mode;
        m_accent = accent;
        m_selection = selection;
        m_muted = muted;
        m_background = background;
        m_surface1 = surface1;
        m_surface2 = surface2;
        m_surface3 = surface3;
        m_text1 = text1;
        m_text2 = text2;
        m_text3 = text3;
        m_text4 = text4;
        m_border = border;
        emit changed();
    }
}
