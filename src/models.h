#ifndef MODELS_H
#define MODELS_H

#include <QAbstractListModel>
#include <QSortFilterProxyModel>
#include <QFileSystemWatcher>
#include <QTimer>
#include <QDateTime>
#include <QList>
#include <QString>
#include <QHash>
#include <QByteArray>
#include <QVariant>
#include <QJsonObject>
#include <QModelIndex>

struct AccountItem {
    QString id;
    QString email;
    QString username;           // 剥离 @gmail.com 等后缀的纯净用户名 (如 cakeai88)
    QString maskedUsername;     // 脱敏用户名 (如 c***8)
    QString name;
    QString shortName;
    QString maskedName;
    QString tier;
    bool pro = false;
    bool isActive = false;
    bool isBlocked = false;
    QString validationUrl;

    // Gemini 4
    double gemini4Quota = 0.0;          // 0.0 ~ 1.0
    QString gemini4Reset;               // "5d 15h"
    bool gemini4Valid = false;

    // Gemini 3.8
    double gemini38Quota5h = 0.0;       // 5h quota (weekly 0 -> 0.0)
    QString gemini38Reset5h;
    double gemini38QuotaW = 0.0;        // weekly quota
    QString gemini38ResetW;

    // Claude
    double claudeQuota5h = 0.0;         // 5h quota (weekly 0 -> 0.0)
    QString claudeReset5h;
    double claudeQuotaW = 0.0;          // weekly quota
    QString claudeResetW;

    bool hasClaude55 = false;
    QString status = QStringLiteral("STANDBY"); // "ACTIVE", "STANDBY", "BLOCKED", "EXHAUSTED"
    int manualLockRemaining = 0;        // seconds

    // Absolute timestamps
    qint64 gemini4ResetTs = 0;
    qint64 gemini38Reset5hTs = 0;
    qint64 gemini38ResetWTs = 0;
    qint64 claudeReset5hTs = 0;
    qint64 claudeResetWTs = 0;
    qint64 manualLockUntilTs = 0;
};

class AccountModel : public QAbstractListModel {
    Q_OBJECT
    Q_PROPERTY(QString activeEmail READ activeEmail NOTIFY activeEmailChanged)
    Q_PROPERTY(int totalAccounts READ totalAccounts NOTIFY countChanged)
    Q_PROPERTY(bool isMasked READ isMasked WRITE setIsMasked NOTIFY isMaskedChanged)

public:
    enum AccountRoles {
        IndexRole = Qt::UserRole + 1,
        EmailRole,
        UsernameRole,
        DisplayUsernameRole,
        NameRole,
        ShortNameRole,
        MaskedNameRole,
        IsActiveRole,
        StatusRole,
        ManualLockRemainingRole,
        ManualLockRemainingStrRole,
        Gemini4QuotaRole,
        Gemini4ResetRole,
        Gemini4ValidRole,
        Gemini38Quota5hRole,
        Gemini38Reset5hRole,
        Gemini38QuotaWRole,
        Gemini38ResetWRole,
        ClaudeQuota5hRole,
        ClaudeReset5hRole,
        ClaudeQuotaWRole,
        ClaudeResetWRole,
        HasClaude55Role,
        IsBlockedRole,
        ValidationUrlRole,
        TierRole,
        IdRole
    };
    Q_ENUM(AccountRoles)

    explicit AccountModel(QObject *parent = nullptr);
    ~AccountModel() override = default;

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    int totalAccounts() const { return rowCount(); }
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    QString activeEmail() const { return m_activeEmail; }
    bool isMasked() const { return m_isMasked; }
    Q_INVOKABLE void setIsMasked(bool masked);

    // QML / Test methods
    Q_INVOKABLE void reload();
    Q_INVOKABLE QVariantMap getAccount(int row) const;
    Q_INVOKABLE QString maskName(const QString &raw) const;
    Q_INVOKABLE int findIndexByEmail(const QString &email) const;

    static QString computeMaskedName(const QString &rawName);
    static QString computeMaskedUsername(const QString &rawUname);
    static qint64 parseIsoTimestamp(const QString &isoStr);
    static QString formatCountdown(qint64 targetEpoch, qint64 nowEpoch);

signals:
    void activeEmailChanged(const QString &email);
    void isMaskedChanged(bool masked);
    void countChanged();
    void dataRefreshed();

private slots:
    void onFileSystemChanged(const QString &path);
    void onDebounceTimeout();
    void onSecondTick();

private:
    void initWatcher();
    void loadFromDisk();
    void loadManualLockState();
    void updateCountdownStrings();

    QList<AccountItem> m_accounts;
    QString m_activeEmail;
    bool m_isMasked = false;

    QString m_baseDir;
    QString m_hubAccountsPath;
    QString m_hubDataDirPath;
    QString m_manualLockPath;

    QFileSystemWatcher *m_watcher = nullptr;
    QTimer *m_debounceTimer = nullptr;
    QTimer *m_secondTimer = nullptr;
};

class AccountFilterProxyModel : public QSortFilterProxyModel {
    Q_OBJECT
    Q_PROPERTY(QString filterText READ filterText WRITE setFilterText NOTIFY filterTextChanged)
    Q_PROPERTY(QString statusTab READ statusTab WRITE setStatusTab NOTIFY statusTabChanged)
    Q_PROPERTY(int totalCount READ totalCount NOTIFY countsChanged)
    Q_PROPERTY(int filteredCount READ filteredCount NOTIFY countsChanged)
    Q_PROPERTY(QString sortField READ sortField WRITE setSortField NOTIFY sortFieldChanged)
    Q_PROPERTY(Qt::SortOrder sortOrder READ sortOrder WRITE setSortOrder NOTIFY sortOrderChanged)

public:
    explicit AccountFilterProxyModel(QObject *parent = nullptr);
    ~AccountFilterProxyModel() override = default;

    QString filterText() const { return m_filterText; }
    void setFilterText(const QString &text);

    QString statusTab() const { return m_statusTab; }
    void setStatusTab(const QString &tab);

    int totalCount() const;
    int filteredCount() const;

    QString sortField() const { return m_sortField; }
    void setSortField(const QString &field);

    Qt::SortOrder sortOrder() const { return m_sortOrder; }
    void setSortOrder(Qt::SortOrder order);

    void setSourceModel(QAbstractItemModel *sourceModel) override;

    Q_INVOKABLE void setSortRule(const QString &field, Qt::SortOrder order = Qt::DescendingOrder);
    Q_INVOKABLE QVariantMap getFilteredAccount(int row) const;

signals:
    void filterTextChanged(const QString &text);
    void statusTabChanged(const QString &tab);
    void countsChanged();
    void sortFieldChanged(const QString &field);
    void sortOrderChanged(Qt::SortOrder order);

protected:
    bool filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const override;
    bool lessThan(const QModelIndex &sourceLeft, const QModelIndex &sourceRight) const override;

private slots:
    void updateCounts();

private:
    QString m_filterText;
    QString m_statusTab = QStringLiteral("all"); // "all", "usable", "plentiful", "warning", "exhausted"
    QString m_sortField = QStringLiteral("default");
    Qt::SortOrder m_sortOrder = Qt::DescendingOrder;
};

#endif // MODELS_H
