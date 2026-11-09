#include "theme.h"

#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFontDatabase>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMap>
#include <QRegularExpression>
#include <QStandardPaths>
#include <cmath>

static QString mixColors(const QString &from, const QString &to, double amount) {
    const QColor a(from), b(to);
    return QColor::fromRgbF(a.redF() + (b.redF() - a.redF()) * amount,
                            a.greenF() + (b.greenF() - a.greenF()) * amount,
                            a.blueF() + (b.blueF() - a.blueF()) * amount).name();
}

static QString withAlphaColor(const QString &color, double alpha) {
    QColor c(color);
    c.setAlphaF(alpha);
    return c.name(QColor::HexArgb);
}

Theme::Theme(const QString &directory, QObject *parent, const QString &hyprctl)
    : QObject(parent),
      m_directory(directory.isEmpty() ? QDir::homePath() + "/.local/state/omarchy/current" : directory) {

    // Load InterVariable font directly for authentic Omarchy typography
    const int fontId = QFontDatabase::addApplicationFont(":/fonts/InterVariable.ttf");
    const QStringList families = fontId >= 0 ? QFontDatabase::applicationFontFamilies(fontId) : QStringList();
    m_uiFont = families.isEmpty() ? QStringLiteral("sans-serif") : families.first();

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

    // Canvas Background: strictly background from Omarchy theme spec (e.g. Jade Horse: #142620)
    if (raw.contains("background")) background = raw["background"];
    else if (raw.contains("darker_background")) background = raw["darker_background"];

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

void Theme::setThemeMode(const QString &mode) {
    if (m_themeMode != mode) {
        m_themeMode = mode;
        emit themeModeChanged();
        reload();
    }
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
        m_directory + "/theme.generation",
        m_directory + "/theme.name"
    };
    candidates.removeDuplicates();
    for (const auto &path : candidates) {
        if (QFileInfo::exists(path))
            m_watcher.addPath(path);
    }

    // 4. Parse colors.toml
    const QString colorsPath = m_directory + "/theme/colors.toml";
    QString parsedMode = "dark", accent = m_accent, selection = m_selection, muted = m_muted;
    QString background = m_background, surface1 = m_surface1, surface2 = m_surface2, surface3 = m_surface3;
    QString text1 = m_text1, text2 = m_text2, text3 = m_text3, text4 = m_text4, border = m_border;

    parsePalette(colorsPath, parsedMode, accent, selection, muted,
                 background, surface1, surface2, surface3,
                 text1, text2, text3, text4, border);

    m_detectedMode = parsedMode;
    QString effectiveMode = m_themeMode;
    if (effectiveMode != "light" && effectiveMode != "dark") {
        effectiveMode = m_detectedMode;
    }

    QString mode = effectiveMode;
    QString surfaceTop, surfaceBottom, hairline, controlBorder;
    QString dangerText, goodText, warningText, accentText;

    if (effectiveMode == "light") {
        // Pure White Theme (白色主题)
        mode = "light";
        background = "#FFFFFF";
        surface1 = "#F8FAFC"; // Slate 50
        surface2 = "#F1F5F9"; // Slate 100
        surface3 = "#E2E8F0"; // Slate 200
        text1 = "#0F172A";    // Slate 900 (Maximum Contrast Deep Ink)
        text2 = "#1E293B";    // Slate 800 (Crisp Body)
        text3 = "#475569";    // Slate 600 (Secondary Text / Countdowns)
        text4 = "#64748B";    // Slate 500 (Muted Hints)
        border = "rgba(0, 0, 0, 0.08)";
        selection = "#E2E8F0";
        if (accent.isEmpty() || accent == "#798186" || accent == "#cacccc") {
            accent = "#0284C7"; // Vibrant Sky
        }
        surfaceTop = "#F8FAFC";
        surfaceBottom = "#F1F5F9";
        hairline = "rgba(0, 0, 0, 0.08)";
        controlBorder = "rgba(0, 0, 0, 0.16)";
        dangerText = "#DC2626";
        goodText = "#16A34A";
        warningText = "#D97706";
        accentText = accent;
    } else {
        // Dark Mode: Aligned with Omarchy Control (Pure White text for crystal-clear readability)
        mode = "dark";
        if (background.isEmpty() || background == "#FFFFFF") background = "#142620";
        if (surface1.isEmpty() || surface1 == "#F8FAFC") surface1 = "#0f1e19";
        if (surface2.isEmpty() || surface2 == "#F1F5F9") surface2 = "#142620";
        if (surface3.isEmpty() || surface3 == "#E2E8F0") surface3 = "#203b31";

        // Pure white & high-contrast text invariants
        text1 = "#FFFFFF";    // Pure White (Headings, titles, account names, badges)
        text2 = "#F3F4F6";    // Crisp near-white
        text3 = "#CBD5E1";    // Legible silver-gray (countdowns, column secondary)
        text4 = "#94A3B8";    // Legible muted gray
        border = "rgba(255, 255, 255, 0.08)";
        if (accent.isEmpty()) accent = "#8bcbb1";

        surfaceTop = mixColors(background, "#FFFFFF", 0.055);
        surfaceBottom = mixColors(background, "#FFFFFF", 0.025);
        hairline = withAlphaColor(text1, 0.12);
        controlBorder = withAlphaColor(text1, 0.24);
        dangerText = "#FF6B6B";
        goodText = "#4ADE80";
        warningText = "#FFD166";
        accentText = accent;
    }

    bool hasChanged = (mode != m_mode || accent != m_accent || selection != m_selection || muted != m_muted ||
                       background != m_background || surface1 != m_surface1 || surface2 != m_surface2 || surface3 != m_surface3 ||
                       text1 != m_text1 || text2 != m_text2 || text3 != m_text3 || text4 != m_text4 || border != m_border ||
                       surfaceTop != m_surfaceTop || surfaceBottom != m_surfaceBottom || hairline != m_hairline ||
                       controlBorder != m_controlBorder || dangerText != m_dangerText || goodText != m_goodText ||
                       warningText != m_warningText || accentText != m_accentText);

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
        m_surfaceTop = surfaceTop;
        m_surfaceBottom = surfaceBottom;
        m_hairline = hairline;
        m_controlBorder = controlBorder;
        m_dangerText = dangerText;
        m_goodText = goodText;
        m_warningText = warningText;
        m_accentText = accentText;
        emit changed();
    }
}
