#pragma once

#include <QFileSystemWatcher>
#include <QObject>
#include <QProcess>
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
    Q_PROPERTY(QString canvas READ canvas NOTIFY changed)
    Q_PROPERTY(QString surfaceTop READ surfaceTop NOTIFY changed)
    Q_PROPERTY(QString surfaceBottom READ surfaceBottom NOTIFY changed)
    Q_PROPERTY(QString hairline READ hairline NOTIFY changed)
    Q_PROPERTY(QString controlBorder READ controlBorder NOTIFY changed)
    Q_PROPERTY(int panelRadius READ panelRadius NOTIFY changed)
    Q_PROPERTY(int controlRadius READ controlRadius NOTIFY changed)
    Q_PROPERTY(bool rounded READ rounded NOTIFY changed)
    Q_PROPERTY(QString dangerText READ dangerText NOTIFY changed)
    Q_PROPERTY(QString goodText READ goodText NOTIFY changed)
    Q_PROPERTY(QString warningText READ warningText NOTIFY changed)
    Q_PROPERTY(QString accentText READ accentText NOTIFY changed)

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
    int radius() const { return m_radius; }

    QString mode() const { return m_mode; }
    QString selection() const { return m_selection; }
    QString muted() const { return m_muted; }

    QString themeMode() const { return m_themeMode; }
    void setThemeMode(const QString &mode);

    // Omarchy Standard Getters
    QString uiFont() const { return m_uiFont; }
    QString canvas() const { return m_background; }
    QString surfaceTop() const { return m_surfaceTop; }
    QString surfaceBottom() const { return m_surfaceBottom; }
    QString hairline() const { return m_hairline; }
    QString controlBorder() const { return m_controlBorder; }
    int panelRadius() const { return qMin(m_radius, 14); }
    int controlRadius() const { return m_radius > 0 ? qBound(4, m_radius * 2 / 3, 8) : 4; }
    bool rounded() const { return m_radius > 0; }
    QString dangerText() const { return m_dangerText; }
    QString goodText() const { return m_goodText; }
    QString warningText() const { return m_warningText; }
    QString accentText() const { return m_accentText; }

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
    QString m_border = "rgba(255, 255, 255, 0.08)";
    int m_radius = 0;

    QString m_uiFont = "sans-serif";
    QString m_surfaceTop = "#172c25";
    QString m_surfaceBottom = "#11201b";
    QString m_hairline = "rgba(255, 255, 255, 0.12)";
    QString m_controlBorder = "rgba(255, 255, 255, 0.24)";
    QString m_dangerText = "#FF6B6B";
    QString m_goodText = "#4ADE80";
    QString m_warningText = "#FFD166";
    QString m_accentText = "#8bcbb1";

    QFileSystemWatcher m_watcher;
    QTimer m_debounce;
    QString m_hyprctl;
    QProcess m_roundingProcess;
    QTimer m_roundingPoll, m_roundingTimeout;
};
