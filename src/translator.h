#pragma once

#include <QFileSystemWatcher>
#include <QHash>
#include <QJsonValue>
#include <QLocale>
#include <QTimer>
#include <QTranslator>

/**
 * @brief Dynamic Internationalization Engine for Antigravity Hub.
 *
 * Implements the canonical Omarchy Translator pattern:
 * - Inherits QTranslator to intercept tr() and qsTr() calls.
 * - Monitors ~/.config/omarchy/language and its parent directory.
 * - 80ms single-shot debounce prevents thrashing during multi-write operations.
 * - Re-arms file watcher to survive atomic inode replacements.
 * - Supports CLDR cardinal pluralization across whole numbers.
 * - Emits changed() to trigger QQmlEngine::retranslate() for zero-restart live UI updates.
 */
class Translator : public QTranslator {
    Q_OBJECT
    Q_PROPERTY(QString language READ language NOTIFY changed)

public:
    explicit Translator(const QString &languageFile = {}, const QString &catalogDirectory = ":/i18n",
                        QObject *parent = nullptr);

    QString language() const { return m_language; }
    bool isEmpty() const override { return m_strings.isEmpty(); }
    QString translate(const char *context, const char *sourceText, const char *disambiguation = nullptr,
                      int n = -1) const override;

    static QString readLanguage(const QString &path);
    static QString pluralCategory(const QString &language, long long count);
    static QLocale formatLocale(const QString &language);

signals:
    void changed();

private:
    void reload();

    QString m_languageFile;
    QString m_catalogDirectory;
    QString m_language;
    QHash<QString, QJsonValue> m_strings;
    QFileSystemWatcher m_watcher;
    QTimer m_debounce;
};
