#include "theme.h"

#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFontDatabase>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QStandardPaths>
#include <cmath>

static double relativeLuminance(const QColor &c) {
    if (!c.isValid())
        return 0.0;
    const auto linear = [](double v) {
        return v <= 0.04045 ? v / 12.92 : std::pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * linear(c.redF()) +
           0.7152 * linear(c.greenF()) +
           0.0722 * linear(c.blueF());
}

double Theme::contrast(const QString &a, const QString &b) {
    const QColor ca(a), cb(b);
    if (!ca.isValid() || !cb.isValid())
        return 1.0;
    const double first = relativeLuminance(ca), second = relativeLuminance(cb);
    return (qMax(first, second) + 0.05) / (qMin(first, second) + 0.05);
}

QString Theme::mix(const QString &from, const QString &to, double amount) {
    const QColor a(from), b(to);
    if (!a.isValid()) return to;
    if (!b.isValid()) return from;
    const double t = qBound(0.0, amount, 1.0);
    return QColor::fromRgbF(a.redF() + (b.redF() - a.redF()) * t,
                            a.greenF() + (b.greenF() - a.greenF()) * t,
                            a.blueF() + (b.blueF() - a.blueF()) * t).name();
}

QString Theme::withAlpha(const QString &color, double alpha) {
    QColor c(color);
    if (!c.isValid()) return color;
    c.setAlphaF(qBound(0.0, alpha, 1.0));
    return c.name(QColor::HexArgb);
}

QHash<QString, QString> Theme::readColors(const QString &path) {
    QHash<QString, QString> colors;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return colors;
    static const QRegularExpression expression(R"re(^\s*([A-Za-z0-9_-]+)\s*=\s*["']([^"'\r\n]+)["'])re",
                                                QRegularExpression::MultilineOption);
    auto matches = expression.globalMatch(QString::fromUtf8(file.readAll()));
    while (matches.hasNext()) {
        const auto match = matches.next();
        colors.insert(match.captured(1), match.captured(2));
    }
    return colors;
}

QString Theme::readable(const QString &color, const QString &foreground, const QStringList &surfaces, double ratio) {
    const QColor from(color), to(foreground);
    if (!from.isValid() || !to.isValid())
        return color;
    const auto enoughOn = [&](const QString &candidate) {
        for (const auto &surface : surfaces) {
            if (surface.isEmpty())
                continue;
            if (contrast(candidate, surface) < ratio)
                return false;
        }
        return true;
    };
    if (enoughOn(color))
        return color;

    // Phase 1: Lighten or darken in HSL space first, preserving original hue and saturation.
    float hue, saturation, lightness;
    from.getHslF(&hue, &saturation, &lightness);
    if (hue < 0.0f)
        hue = 0.0f;
    const float target = to.lightnessF() < lightness ? 0.0f : 1.0f;
    for (int step = 1; step <= 20; ++step) {
        const float newL = qBound(0.0f, lightness + (target - lightness) * step / 20.0f, 1.0f);
        const QString shifted = QColor::fromHslF(hue, saturation, newL).name();
        if (enoughOn(shifted))
            return shifted;
    }

    // Phase 1b: Try opposite direction in HSL space if primary direction had insufficient headroom
    // (handles cases where background luminance is identical to target color, or mid-tone ceiling)
    const float altTarget = 1.0f - target;
    for (int step = 1; step <= 20; ++step) {
        const float newL = qBound(0.0f, lightness + (altTarget - lightness) * step / 20.0f, 1.0f);
        const QString shifted = QColor::fromHslF(hue, saturation, newL).name();
        if (enoughOn(shifted))
            return shifted;
    }

    // Phase 2: If HSL space has no headroom, interpolate linearly toward foreground in RGB space.
    QString candidate = color;
    for (int step = 0; step <= 20; ++step) {
        const double t = step / 20.0;
        candidate = QColor::fromRgbF(from.redF() + (to.redF() - from.redF()) * t,
                                     from.greenF() + (to.greenF() - from.greenF()) * t,
                                     from.blueF() + (to.blueF() - from.blueF()) * t).name();
        if (enoughOn(candidate))
            return candidate;
    }

    // Phase 3: Extreme fallback if reference foreground itself lacked contrast on surfaces
    if (enoughOn(QStringLiteral("#ffffff")))
        return QStringLiteral("#ffffff");
    if (enoughOn(QStringLiteral("#000000")))
        return QStringLiteral("#000000");

    return candidate;
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

    Q_UNUSED(hyprctl);
    // User Supreme Visual Iron Rule: All radii are permanently zero (controlRadius=0, panelRadius=0, radius=0, rounded=false).
    // Hyprland rounding polling timer is intentionally purged to eliminate redundant process forks and enforce zero-radius geometry.

    reload();
}

Theme::~Theme() = default;

void Theme::refreshRounding() {
    // Purged / No-op: Zero-radius visual iron rule
}

QString Theme::accentForeground() const {
    const QColor c(m_accent);
    if (!c.isValid())
        return "black";
    return relativeLuminance(c) > 0.179 ? "black" : "white";
}

void Theme::parsePalette(const QString &path,
                         QString &mode, QString &accent, QString &selection, QString &muted,
                         QString &background, QString &surface1, QString &surface2, QString &surface3,
                         QString &text1, QString &text2, QString &text3, QString &text4, QString &border) {
    const auto raw = readColors(path);
    if (raw.isEmpty())
        return;

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

    // Border: explicit 'border' or subtle alpha separator
    if (raw.contains("border")) border = raw["border"];
    else border = (mode == "light") ? "#14000000" : "#14ffffff";
}

void Theme::setThemeMode(const QString &mode) {
    const QString normalized = mode.trimmed().toLower();
    if (m_themeMode != normalized) {
        m_themeMode = normalized;
        emit themeModeChanged();
        reload();
        emit changed();
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
    while (!QFileInfo::exists(ancestor) && ancestor != "/" && ancestor != ".")
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

    // 4. Parse colors.toml using full canonical reader
    const QString colorsPath = m_directory + "/theme/colors.toml";
    const auto rawColors = readColors(colorsPath);

    m_detectedMode = rawColors.value("mode", "dark");
    QString effectiveMode = m_themeMode;
    if (effectiveMode != "light" && effectiveMode != "dark") {
        effectiveMode = m_detectedMode;
    }

    const bool isDark = (effectiveMode != "light");
    QString mode = isDark ? "dark" : "light";

    QString window, sidebar, deep, raised, foreground;
    QString selection, muted, accent;
    QString text1, text2, text3, text4;
    QString good, warning, danger;
    bool forcedDark = false;

    if (!isDark) {
        // Light Mode
        if (m_detectedMode == "light" && rawColors.contains("background")) {
            // Authentic light theme from colors.toml (e.g. Catppuccin Latte)
            window = rawColors.value("background", "#eff1f5");
            sidebar = rawColors.value("dark_background", "#e3e4e8");
            deep = rawColors.value("darker_background", "#d7d8dc");
            raised = rawColors.value("lighter_background", "#dce0e8");
            foreground = rawColors.value("foreground", "#4c4f69");
            selection = rawColors.value("selection", "#ccd0da");
            muted = rawColors.value("muted", "#acb0be");
            accent = rawColors.value("accent", "#1e66f5");
            text1 = rawColors.value("bright_foreground", foreground);
            text2 = rawColors.value("foreground", "#1E293B");
            text3 = rawColors.value("light_foreground", "#475569");
            text4 = rawColors.value("dark_foreground", "#64748B");
            good = rawColors.value("green", rawColors.value("bright_green", "#40a02b"));
            warning = rawColors.value("yellow", rawColors.value("bright_yellow", rawColors.value("orange", "#df8e1d")));
            danger = rawColors.value("red", rawColors.value("bright_red", "#d20f39"));
        } else {
            // Forced Pure White Theme
            window = "#FFFFFF";
            sidebar = "#F8FAFC";
            deep = "#F1F5F9";
            raised = "#E2E8F0";
            foreground = "#0F172A";
            text1 = "#0F172A";
            text2 = "#1E293B";
            text3 = "#475569";
            text4 = "#64748B";
            selection = "#E2E8F0";
            muted = "#94A3B8";
            accent = rawColors.value("accent", m_accent);
            if (accent.isEmpty() || accent == "#798186" || accent == "#cacccc") {
                accent = "#0284C7";
            }
            good = rawColors.value("green", rawColors.value("bright_green", "#16A34A"));
            warning = rawColors.value("yellow", rawColors.value("bright_yellow", rawColors.value("orange", "#D97706")));
            danger = rawColors.value("red", rawColors.value("bright_red", "#DC2626"));
        }
    } else {
        // Dark Mode
        const bool isUnderlyingLight = (m_detectedMode == "light") ||
            (rawColors.contains("background") && relativeLuminance(QColor(rawColors.value("background"))) > 0.4);

        if (!isUnderlyingLight && rawColors.contains("background")) {
            // Authentic dark theme from colors.toml (e.g. Jade Horse, Tokyo Night, Gruvbox)
            window = rawColors.value("background", "#142620");
            sidebar = rawColors.value("dark_background", "#0f1e19");
            deep = rawColors.value("darker_background", "#0a1713");
            raised = rawColors.value("lighter_background", "#203b31");
            foreground = rawColors.value("foreground", "#dfede5");
            selection = rawColors.value("selection", "#2b5147");
            muted = rawColors.value("muted", "#64887b");
            accent = rawColors.value("accent", "#8bcbb1");
            text1 = "#FFFFFF";
            text2 = "#F3F4F6";
            text3 = "#CBD5E1";
            text4 = "#94A3B8";
            good = rawColors.value("green", rawColors.value("bright_green", "#8bcbb1"));
            warning = rawColors.value("yellow", rawColors.value("bright_yellow", rawColors.value("orange", "#c5cc91")));
            danger = rawColors.value("red", rawColors.value("bright_red", "#d88d91"));
        } else {
            // Forced dark mode when system theme is light, or fallback
            forcedDark = true;
            window = "#0e0e14";
            sidebar = "#101016";
            deep = "#0a0a0f";
            raised = "#24283b";
            foreground = "#f5f5f7";
            selection = rawColors.value("selection", "#292e42");
            muted = rawColors.value("muted", "#64887b");
            accent = rawColors.value("accent", "#FFD60A");
            text1 = "#FFFFFF";
            text2 = "#a9b1d6";
            text3 = "#CBD5E1";
            text4 = "#94A3B8";
            good = rawColors.value("green", rawColors.value("bright_green", "#5fc97f"));
            warning = rawColors.value("yellow", rawColors.value("bright_yellow", rawColors.value("orange", "#ffc27a")));
            danger = rawColors.value("red", rawColors.value("bright_red", "#ff5f4a"));
        }
    }

    // Contrast guard for selection background (prevents light selection bleeding into forcedDark mode)
    if (contrast(text1, selection) < 4.5) {
        selection = isDark ? mix(window, accent, 0.24) : mix(window, accent, 0.14);
        if (contrast(text1, selection) < 4.5) {
            selection = isDark ? QStringLiteral("#292e42") : QStringLiteral("#E2E8F0");
        }
    }

    // Surfaces computation
    QString canvas;
    QString surfaceTop;
    QString surfaceBottom;
    if (forcedDark) {
        canvas = QStringLiteral("#08080c");
        surfaceTop = QStringLiteral("#13141c");
        surfaceBottom = QStringLiteral("#1a1b26");
    } else if (!isDark) {
        canvas = QStringLiteral("#F8FAFC");
        surfaceTop = QStringLiteral("#FFFFFF");
        surfaceBottom = QStringLiteral("#F1F5F9");
    } else {
        canvas = mix(mix(window, deep, 0.55), accent, 0.02);
        surfaceTop = mix(canvas, foreground, 0.055);
        surfaceBottom = mix(canvas, foreground, 0.025);
    }
    QString hairline = withAlpha(text1, isDark ? 0.12 : 0.14);
    QString controlBorder = withAlpha(text1, isDark ? 0.24 : 0.28);
    QString border = withAlpha(text1, isDark ? 0.08 : 0.12);

    // Dynamic WCAG 4.5:1 Contrast Adaptation for Semantic Status Colors
    const QStringList surfaces = { canvas, surfaceTop, window, sidebar };
    QString goodText = readable(good, text1, surfaces);
    QString warningText = readable(warning, text1, surfaces);
    QString dangerText = readable(danger, text1, surfaces);
    QString accentText = readable(accent, text1, surfaces);

    // Zebra Striping & Component Slots
    QString rowEven = isDark ? mix(deep, window, 0.35) : window;
    QString rowOdd = isDark ? mix(window, foreground, 0.085) : mix(sidebar, foreground, 0.085);
    QString trackBg = withAlpha(foreground, isDark ? 0.16 : 0.12);
    QString pillBg = withAlpha(foreground, isDark ? 0.07 : 0.06);

    bool hasChanged = (mode != m_mode || accent != m_accent || selection != m_selection || muted != m_muted ||
                       window != m_background || sidebar != m_surface1 || window != m_surface2 || raised != m_surface3 ||
                       text1 != m_text1 || text2 != m_text2 || text3 != m_text3 || text4 != m_text4 || border != m_border ||
                       canvas != m_canvas || surfaceTop != m_surfaceTop || surfaceBottom != m_surfaceBottom ||
                       hairline != m_hairline || controlBorder != m_controlBorder ||
                       good != m_good || warning != m_warning || danger != m_danger ||
                       dangerText != m_dangerText || goodText != m_goodText ||
                       warningText != m_warningText || accentText != m_accentText ||
                       rowEven != m_rowEven || rowOdd != m_rowOdd || trackBg != m_trackBg || pillBg != m_pillBg);

    if (hasChanged) {
        m_mode = mode;
        m_accent = accent;
        m_selection = selection;
        m_muted = muted;
        m_background = window;
        m_surface1 = sidebar;
        m_surface2 = window;
        m_surface3 = raised;
        m_text1 = text1;
        m_text2 = text2;
        m_text3 = text3;
        m_text4 = text4;
        m_border = border;
        m_canvas = canvas;
        m_surfaceTop = surfaceTop;
        m_surfaceBottom = surfaceBottom;
        m_hairline = hairline;
        m_controlBorder = controlBorder;
        m_good = good;
        m_warning = warning;
        m_danger = danger;
        m_dangerText = dangerText;
        m_goodText = goodText;
        m_warningText = warningText;
        m_accentText = accentText;
        m_rowEven = rowEven;
        m_rowOdd = rowOdd;
        m_trackBg = trackBg;
        m_pillBg = pillBg;
        emit changed();
    }
}

