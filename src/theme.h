#pragma once

#include <QFileSystemWatcher>
#include <QHash>
#include <QObject>
#include <QProcess>
#include <QStringList>
#include <QTimer>

class Theme : public QObject {
    Q_OBJECT

    // Core Omarchy Color & Geometry Tokens
    Q_PROPERTY(QString accent READ accent NOTIFY changed)
    Q_PROPERTY(QString accentForeground READ accentForeground NOTIFY changed)
    Q_PROPERTY(QString background READ background NOTIFY changed)
    Q_PROPERTY(QString surface1 READ surface1 NOTIFY changed)
    Q_PROPERTY(QString surface2 READ surface2 NOTIFY changed)
    Q_PROPERTY(QString surface3 READ surface3 NOTIFY changed)
    Q_PROPERTY(QString text1 READ text1 NOTIFY changed)
    Q_PROPERTY(QString text2 READ text2 NOTIFY changed)
    Q_PROPERTY(QString text3 READ text3 NOTIFY changed)
    Q_PROPERTY(QString text4 READ text4 NOTIFY changed)
    Q_PROPERTY(QString border READ border NOTIFY changed)
    Q_PROPERTY(int radius READ radius NOTIFY changed)

    // Additional Omarchy Shell Tokens
    Q_PROPERTY(QString mode READ mode NOTIFY changed)
    Q_PROPERTY(QString selection READ selection NOTIFY changed)
    Q_PROPERTY(QString muted READ muted NOTIFY changed)
    Q_PROPERTY(QString themeMode READ themeMode WRITE setThemeMode NOTIFY themeModeChanged)

    // Omarchy Standard Design System Tokens
    Q_PROPERTY(QString uiFont READ uiFont CONSTANT)
    Q_PROPERTY(QString monoFont READ monoFont CONSTANT)
    Q_PROPERTY(QString canvas READ canvas NOTIFY changed)
    Q_PROPERTY(QString surfaceTop READ surfaceTop NOTIFY changed)
    Q_PROPERTY(QString surfaceBottom READ surfaceBottom NOTIFY changed)
    Q_PROPERTY(QString hairline READ hairline NOTIFY changed)
    Q_PROPERTY(QString controlBorder READ controlBorder NOTIFY changed)
    Q_PROPERTY(int panelRadius READ panelRadius NOTIFY changed)
    Q_PROPERTY(int controlRadius READ controlRadius NOTIFY changed)
    Q_PROPERTY(bool rounded READ rounded NOTIFY changed)
    Q_PROPERTY(QString danger READ danger NOTIFY changed)
    Q_PROPERTY(QString good READ good NOTIFY changed)
    Q_PROPERTY(QString warning READ warning NOTIFY changed)
    Q_PROPERTY(QString dangerText READ dangerText NOTIFY changed)
    Q_PROPERTY(QString goodText READ goodText NOTIFY changed)
    Q_PROPERTY(QString warningText READ warningText NOTIFY changed)
    Q_PROPERTY(QString accentText READ accentText NOTIFY changed)

    // Zebra Striping & Component Slots
    Q_PROPERTY(QString rowEven READ rowEven NOTIFY changed)
    Q_PROPERTY(QString rowOdd READ rowOdd NOTIFY changed)
    Q_PROPERTY(QString trackBg READ trackBg NOTIFY changed)
    Q_PROPERTY(QString pillBg READ pillBg NOTIFY changed)

public:
    explicit Theme(const QString &currentDirectory = {}, QObject *parent = nullptr, const QString &hyprctl = {});
    ~Theme() override;

    QString accent() const { return m_accent; }
    QString accentForeground() const;
    QString background() const { return m_background; }
    QString surface1() const { return m_surface1; }
    QString surface2() const { return m_surface2; }
    QString surface3() const { return m_surface3; }
    QString text1() const { return m_text1; }
    QString text2() const { return m_text2; }
    QString text3() const { return m_text3; }
    QString text4() const { return m_text4; }
    QString border() const { return m_border; }
    int radius() const { return 0; }

    QString mode() const { return m_mode; }
    QString selection() const { return m_selection; }
    QString muted() const { return m_muted; }

    QString themeMode() const { return m_themeMode; }
    void setThemeMode(const QString &mode);

    // Omarchy Standard Getters
    QString uiFont() const { return m_uiFont; }
    QString monoFont() const { return QStringLiteral("JetBrainsMono Nerd Font"); }
    QString canvas() const { return m_canvas.isEmpty() ? m_background : m_canvas; }
    QString surfaceTop() const { return m_surfaceTop; }
    QString surfaceBottom() const { return m_surfaceBottom; }
    QString hairline() const { return m_hairline; }
    QString controlBorder() const { return m_controlBorder; }
    int panelRadius() const { return 0; }
    int controlRadius() const { return 0; }
    bool rounded() const { return false; }
    QString danger() const { return m_danger; }
    QString good() const { return m_good; }
    QString warning() const { return m_warning; }
    QString dangerText() const { return m_dangerText; }
    QString goodText() const { return m_goodText; }
    QString warningText() const { return m_warningText; }
    QString accentText() const { return m_accentText; }

    // Zebra Striping & Component Slots
    QString rowEven() const { return m_rowEven; }
    QString rowOdd() const { return m_rowOdd; }
    QString trackBg() const { return m_trackBg; }
    QString pillBg() const { return m_pillBg; }

    // Canonical Omarchy Color Algorithms
    Q_INVOKABLE static QHash<QString, QString> readColors(const QString &path);
    Q_INVOKABLE static double contrast(const QString &a, const QString &b);
    Q_INVOKABLE static QString mix(const QString &from, const QString &to, double amount);
    Q_INVOKABLE static QString withAlpha(const QString &color, double alpha);
    Q_INVOKABLE static QString readable(const QString &color, const QString &foreground, const QStringList &surfaces, double ratio = 4.5);

    // Static helper for isolated file parsing & testing
    static void parsePalette(const QString &path,
                             QString &mode, QString &accent, QString &selection, QString &muted,
                             QString &background, QString &surface1, QString &surface2, QString &surface3,
                             QString &text1, QString &text2, QString &text3, QString &text4, QString &border);

signals:
    void changed();
    void themeModeChanged();

private:
    void reload();
    void refreshRounding();

    QString m_directory;
    QString m_mode = "dark";
    QString m_themeMode = "system";
    QString m_detectedMode = "dark";
    QString m_accent = "#FFD60A";
    QString m_selection = "#292e42";
    QString m_muted = "#64887b";
    QString m_background = "#0e0e14";
    QString m_surface1 = "#13141c";
    QString m_surface2 = "#1a1b26";
    QString m_surface3 = "#24283b";
    QString m_text1 = "#FFFFFF";
    QString m_text2 = "#F3F4F6";
    QString m_text3 = "#CBD5E1";
    QString m_text4 = "#94A3B8";
    QString m_border = "#14ffffff";
    int m_radius = 0;

    QString m_uiFont = "sans-serif";
    QString m_canvas = "#0e0e14";
    QString m_surfaceTop = "#172c25";
    QString m_surfaceBottom = "#11201b";
    QString m_hairline = "#1fffffff";
    QString m_controlBorder = "#3dffffff";
    QString m_danger = "#ff5f4a";
    QString m_good = "#5fc97f";
    QString m_warning = "#ffc27a";
    QString m_dangerText = "#ff5f4a";
    QString m_goodText = "#5fc97f";
    QString m_warningText = "#ffc27a";
    QString m_accentText = "#8bcbb1";

    QString m_rowEven = "#0a0a0f";
    QString m_rowOdd = "#1a1b26";
    QString m_trackBg = "#29ffffff";
    QString m_pillBg = "#12ffffff";

    QFileSystemWatcher m_watcher;
    QTimer m_debounce;
    QString m_hyprctl;
    QProcess m_roundingProcess;
    QTimer m_roundingPoll, m_roundingTimeout;
};

