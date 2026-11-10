#include "models.h"

#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QJsonValue>
#include <QStandardPaths>
#include <QDebug>
#include <QSet>
#include <QHash>
#include <QRegularExpression>
#include <algorithm>

// ============================================================================
// 辅助函数: 敏感账号打码与时间格式化
// ============================================================================

QString AccountModel::computeMaskedName(const QString &rawName) {
    if (rawName.isEmpty()) return QString();

    QString target = rawName;
    int atIdx = target.indexOf('@');
    if (atIdx != -1) {
        target = target.left(atIdx);
    }

    const int len = target.length();
    if (len == 0) {
        return QString();
    } else if (len == 1) {
        return target + QStringLiteral("***");
    } else if (len == 2) {
        return target.left(1) + QStringLiteral("***") + target.right(1);
    } else {
        // 长度 >= 3: 首位保留 1 字符，末尾保留 2 字符，中间使用 3 个星号 "***"
        // 验证：bob -> b***ob, user -> u***er, cakeai66 -> c***66, novadu99 -> n***99
        return target.left(1) + QStringLiteral("***") + target.right(2);
    }
}

QString AccountModel::computeMaskedUsername(const QString &rawUname) {
    if (rawUname.isEmpty()) return QString();

    QString target = rawUname;
    int atIdx = target.indexOf('@');
    if (atIdx != -1) {
        target = target.left(atIdx);
    }

    const int len = target.length();
    if (len == 0) {
        return QString();
    } else if (len == 1) {
        return target + QStringLiteral("***");
    } else if (len == 2) {
        return target.left(1) + QStringLiteral("***") + target.right(1);
    } else {
        return target.left(1) + QStringLiteral("***") + target.right(2);
    }
}

qint64 AccountModel::parseIsoTimestamp(const QString &isoStr) {
    if (isoStr.isEmpty() || isoStr == QStringLiteral("--")) {
        return 0;
    }
    QDateTime dt = QDateTime::fromString(isoStr, Qt::ISODate);
    if (!dt.isValid()) {
        dt = QDateTime::fromString(isoStr, Qt::ISODateWithMs);
    }
    return dt.isValid() ? dt.toSecsSinceEpoch() : 0;
}

QString AccountModel::formatCountdown(qint64 targetEpoch, qint64 nowEpoch) {
    if (targetEpoch <= 0) return QStringLiteral("--");
    qint64 diff = targetEpoch - nowEpoch;
    if (diff <= 0) {
        return QStringLiteral("即将恢复");
    }
    const qint64 days = diff / 86400;
    const qint64 hours = (diff % 86400) / 3600;
    const qint64 mins = (diff % 3600) / 60;

    if (days > 0) {
        return QStringLiteral("%1d %2h").arg(days).arg(hours, 2, 10, QLatin1Char('0'));
    }
    if (hours > 0) {
        return QStringLiteral("%1h %2m").arg(hours).arg(mins, 2, 10, QLatin1Char('0'));
    }
    if (mins > 0) {
        return QStringLiteral("0h %1m").arg(mins, 2, 10, QLatin1Char('0'));
    }
    return QStringLiteral("< 1m");
}

// ============================================================================
// AccountModel 实现
// ============================================================================

AccountModel::AccountModel(QObject *parent)
    : QAbstractListModel(parent)
{
    QString baseDir = QString::fromLocal8Bit(qgetenv("ANTIGRAVITY_HUB_DIR"));
    if (baseDir.isEmpty()) {
        baseDir = QDir::homePath() + QStringLiteral("/.antigravity_hub");
    }

    m_baseDir = baseDir;
    m_hubDataDirPath = baseDir + QStringLiteral("/data");
    m_hubAccountsPath = m_hubDataDirPath + QStringLiteral("/accounts_hub.json");
    m_manualLockPath = baseDir + QStringLiteral("/manual_override_lock.json");

    // 容灾检查: 若 data/accounts_hub.json 不存在但根目录下存在，优先兜底
    if (!QFile::exists(m_hubAccountsPath) && QFile::exists(baseDir + QStringLiteral("/accounts_hub.json"))) {
        m_hubAccountsPath = baseDir + QStringLiteral("/accounts_hub.json");
    }

    m_debounceTimer = new QTimer(this);
    m_debounceTimer->setSingleShot(true);
    connect(m_debounceTimer, &QTimer::timeout, this, &AccountModel::onDebounceTimeout);

    m_secondTimer = new QTimer(this);
    connect(m_secondTimer, &QTimer::timeout, this, &AccountModel::onSecondTick);
    m_secondTimer->start(1000);

    loadFromDisk();
    loadManualLockState();
    initWatcher();
}

void AccountModel::initWatcher() {
    if (!m_watcher) {
        m_watcher = new QFileSystemWatcher(this);
        connect(m_watcher, &QFileSystemWatcher::fileChanged, this, &AccountModel::onFileSystemChanged);
        connect(m_watcher, &QFileSystemWatcher::directoryChanged, this, &AccountModel::onFileSystemChanged);
    }

    if (QFileInfo::exists(m_baseDir)) {
        m_watcher->addPath(m_baseDir);
    }
    if (QFileInfo::exists(m_hubDataDirPath)) {
        m_watcher->addPath(m_hubDataDirPath);
    }
    if (QFile::exists(m_hubAccountsPath)) {
        m_watcher->addPath(m_hubAccountsPath);
    }
    if (QFile::exists(m_manualLockPath)) {
        m_watcher->addPath(m_manualLockPath);
    }
}

void AccountModel::onFileSystemChanged(const QString &path) {
    Q_UNUSED(path);
    if (m_watcher) {
        if (QFile::exists(m_hubAccountsPath) && !m_watcher->files().contains(m_hubAccountsPath)) {
            m_watcher->addPath(m_hubAccountsPath);
        }
        if (QFile::exists(m_manualLockPath) && !m_watcher->files().contains(m_manualLockPath)) {
            m_watcher->addPath(m_manualLockPath);
        }
        if (QFileInfo::exists(m_hubDataDirPath) && !m_watcher->directories().contains(m_hubDataDirPath)) {
            m_watcher->addPath(m_hubDataDirPath);
        }
        if (QFileInfo::exists(m_baseDir) && !m_watcher->directories().contains(m_baseDir)) {
            m_watcher->addPath(m_baseDir);
        }
    }
    m_debounceTimer->start(50);
}

void AccountModel::onDebounceTimeout() {
    loadFromDisk();
    loadManualLockState();
    emit dataRefreshed();
}

void AccountModel::reload() {
    loadFromDisk();
    loadManualLockState();
    emit dataRefreshed();
}

void AccountModel::loadFromDisk() {
    if (!QFile::exists(m_hubAccountsPath)) {
        if (QFile::exists(m_hubDataDirPath + QStringLiteral("/accounts_hub.json"))) {
            m_hubAccountsPath = m_hubDataDirPath + QStringLiteral("/accounts_hub.json");
        } else if (QFile::exists(m_baseDir + QStringLiteral("/accounts_hub.json"))) {
            m_hubAccountsPath = m_baseDir + QStringLiteral("/accounts_hub.json");
        }
    }

    QFile file(m_hubAccountsPath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return;
    }

    const QByteArray rawBytes = file.readAll();
    file.close();

    QJsonParseError parseErr;
    const QJsonDocument doc = QJsonDocument::fromJson(rawBytes, &parseErr);
    if (parseErr.error != QJsonParseError::NoError || !doc.isObject()) {
        return;
    }

    const QJsonObject root = doc.object();
    const QString activeEmail = root.value(QStringLiteral("active_email")).toString();
    const QJsonObject accountsObj = root.value(QStringLiteral("accounts")).toObject();

    const qint64 nowEpoch = QDateTime::currentSecsSinceEpoch();
    QList<AccountItem> newItems;
    newItems.reserve(accountsObj.size());

    for (auto it = accountsObj.constBegin(); it != accountsObj.constEnd(); ++it) {
        const QJsonObject a = it.value().toObject();
        AccountItem item;

        item.email = a.value(QStringLiteral("email")).toString(it.key());
        item.id = a.value(QStringLiteral("id")).toString();
        item.tier = a.value(QStringLiteral("tier")).toString(QStringLiteral("PRO"));
        item.pro = a.value(QStringLiteral("pro")).toBool(true);
        item.isBlocked = a.value(QStringLiteral("validation_blocked")).toBool(false);
        item.validationUrl = a.value(QStringLiteral("validation_url")).toString();

        // 账号名与脱敏名 (剥离 @ 后缀保留纯净用户名作为账号列标识)
        item.username = item.email.contains('@') ? item.email.section('@', 0, 0) : item.email;
        item.maskedUsername = computeMaskedUsername(item.username);

        QString rawName = a.value(QStringLiteral("name")).toString();
        if (rawName.isEmpty()) {
            rawName = item.username;
        }
        item.name = rawName;
        item.shortName = item.username;
        item.maskedName = computeMaskedName(item.shortName);

        // Claude 版本与模型矩阵探测
        const QJsonArray cModels = a.value(QStringLiteral("claude_models")).toArray();
        bool has55 = false;
        for (const QJsonValue &v : cModels) {
            const QString mStr = v.toString();
            if (mStr.contains(QStringLiteral("5-5")) || mStr.contains(QStringLiteral("5.5"))) {
                has55 = true;
                break;
            }
        }
        if (!has55 && a.value(QStringLiteral("claude_version")).toString() == QStringLiteral("5.5")) {
            has55 = true;
        }
        item.hasClaude55 = has55;

        // Gemini 4 专享解析
        QJsonObject g4Obj = a.value(QStringLiteral("gemini4")).toObject();
        if (g4Obj.isEmpty()) {
            g4Obj = a.value(QStringLiteral("gemini_4")).toObject();
        }
        if (!g4Obj.isEmpty() && g4Obj.contains(QStringLiteral("quota_weekly"))) {
            item.gemini4Quota = g4Obj.value(QStringLiteral("quota_weekly")).toDouble();
            const QString g4ResetIso = g4Obj.value(QStringLiteral("reset_time_weekly")).toString();
            item.gemini4ResetTs = parseIsoTimestamp(g4ResetIso);
            item.gemini4Reset = formatCountdown(item.gemini4ResetTs, nowEpoch);
            item.gemini4Valid = true;
        } else if (item.hasClaude55) {
            // 5.5 账号必然开通 Gemini 4，若无独立周记录继承 Gemini 周可用额度
            const QJsonObject gObj = a.value(QStringLiteral("gemini")).toObject();
            item.gemini4Quota = gObj.value(QStringLiteral("quota_weekly")).toDouble(1.0);
            const QString gResetIso = gObj.value(QStringLiteral("reset_time_weekly")).toString();
            item.gemini4ResetTs = parseIsoTimestamp(gResetIso);
            item.gemini4Reset = formatCountdown(item.gemini4ResetTs, nowEpoch);
            item.gemini4Valid = true;
        } else {
            item.gemini4Quota = 0.0;
            item.gemini4Reset = QStringLiteral("--");
            item.gemini4Valid = false;
        }

        // Gemini 3.8 双维解析 (带周耗尽短路)
        const QJsonObject geminiObj = a.value(QStringLiteral("gemini")).toObject();
        item.gemini38QuotaW = geminiObj.value(QStringLiteral("quota_weekly")).toDouble(1.0);
        const QString gResetWIso = geminiObj.value(QStringLiteral("reset_time_weekly")).toString();
        item.gemini38ResetWTs = parseIsoTimestamp(gResetWIso);
        item.gemini38ResetW = formatCountdown(item.gemini38ResetWTs, nowEpoch);

        if (item.gemini38QuotaW <= 0.0001) {
            item.gemini38Quota5h = 0.0; // 周耗尽短路
        } else {
            item.gemini38Quota5h = geminiObj.value(QStringLiteral("quota_5h")).toDouble(1.0);
        }
        const QString gReset5hIso = geminiObj.value(QStringLiteral("reset_time_5h")).toString();
        item.gemini38Reset5hTs = parseIsoTimestamp(gReset5hIso);
        item.gemini38Reset5h = formatCountdown(item.gemini38Reset5hTs, nowEpoch);

        // Claude 双维解析 (带周耗尽短路)
        const QJsonObject claudeObj = a.value(QStringLiteral("claude")).toObject();
        item.claudeQuotaW = claudeObj.value(QStringLiteral("quota_weekly")).toDouble(1.0);
        const QString cResetWIso = claudeObj.value(QStringLiteral("reset_time_weekly")).toString();
        item.claudeResetWTs = parseIsoTimestamp(cResetWIso);
        item.claudeResetW = formatCountdown(item.claudeResetWTs, nowEpoch);

        if (item.claudeQuotaW <= 0.0001) {
            item.claudeQuota5h = 0.0; // 周耗尽短路
        } else {
            item.claudeQuota5h = claudeObj.value(QStringLiteral("quota_5h")).toDouble(1.0);
        }
        const QString cReset5hIso = claudeObj.value(QStringLiteral("reset_time_5h")).toString();
        item.claudeReset5hTs = parseIsoTimestamp(cReset5hIso);
        item.claudeReset5h = formatCountdown(item.claudeReset5hTs, nowEpoch);

        // 活跃状态与状态胶囊
        item.isActive = (!activeEmail.isEmpty() && item.email.compare(activeEmail, Qt::CaseInsensitive) == 0);
        if (item.isActive) {
            item.status = QStringLiteral("ACTIVE");
        } else if (item.gemini38QuotaW <= 0.0001) {
            item.status = QStringLiteral("EXHAUSTED");
        } else if (item.isBlocked) {
            item.status = QStringLiteral("BLOCKED");
        } else {
            item.status = QStringLiteral("STANDBY");
        }

        newItems.append(item);
    }

    // ========================================================================
    // ★ v2.50.0: 解决 Qt QJsonObject 字典序强制排序问题，恢复权威自定义/物理排序
    // ========================================================================
    QStringList preferredOrder;

    // 策略 1: 优先读取 JSON 根对象中的 accounts_order / account_order 数组
    QJsonArray orderArr = root.value(QStringLiteral("accounts_order")).toArray();
    if (orderArr.isEmpty()) {
        orderArr = root.value(QStringLiteral("account_order")).toArray();
    }
    for (const auto &v : orderArr) {
        const QString em = v.toString().trimmed();
        if (!em.isEmpty()) {
            preferredOrder.append(em.toLower());
        }
    }

    // 策略 2: 兜底策略 — 若 accounts_order 不存在，从 rawBytes 扫描 accounts 下键的物理书写顺序
    if (preferredOrder.isEmpty()) {
        const int accountsPos = rawBytes.indexOf("\"accounts\"");
        if (accountsPos != -1) {
            const QString text = QString::fromUtf8(rawBytes.mid(accountsPos));
            static const QRegularExpression rxKey(QStringLiteral("\"([^\"]+)\"\\s*:\\s*\\{"));
            auto itMatch = rxKey.globalMatch(text);
            while (itMatch.hasNext()) {
                const QString candidate = itMatch.next().captured(1).trimmed();
                if (accountsObj.contains(candidate)) {
                    const QString lower = candidate.toLower();
                    if (!preferredOrder.contains(lower)) {
                        preferredOrder.append(lower);
                        if (preferredOrder.size() == accountsObj.size()) {
                            break;
                        }
                    }
                }
            }
        }
    }

    // 按 preferredOrder 对 newItems 进行保序重建
    if (!preferredOrder.isEmpty()) {
        QHash<QString, AccountItem> itemMap;
        for (const auto &item : newItems) {
            itemMap.insert(item.email.trimmed().toLower(), item);
        }

        QList<AccountItem> orderedItems;
        orderedItems.reserve(newItems.size());
        QSet<QString> placed;

        for (const QString &em : preferredOrder) {
            if (itemMap.contains(em) && !placed.contains(em)) {
                orderedItems.append(itemMap.value(em));
                placed.insert(em);
            }
        }

        // 兜底追加未出现在 preferredOrder 中的账号（确保绝对零丢号）
        for (const auto &item : newItems) {
            const QString em = item.email.trimmed().toLower();
            if (!placed.contains(em)) {
                orderedItems.append(item);
                placed.insert(em);
            }
        }

        newItems = std::move(orderedItems);
    }

    beginResetModel();
    m_accounts = std::move(newItems);
    const bool emailChanged = (m_activeEmail != activeEmail);
    if (emailChanged) {
        m_activeEmail = activeEmail;
    }
    endResetModel();

    if (emailChanged) {
        emit activeEmailChanged(m_activeEmail);
    }
    emit countChanged();
}

void AccountModel::loadManualLockState() {
    QFile file(m_manualLockPath);
    if (!file.exists() || !file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        for (auto &acc : m_accounts) {
            acc.manualLockRemaining = 0;
            acc.manualLockUntilTs = 0;
        }
        return;
    }

    const QByteArray data = file.readAll();
    file.close();

    const QJsonDocument doc = QJsonDocument::fromJson(data);
    if (!doc.isObject()) return;

    const QJsonObject obj = doc.object();
    const QString lockedAccount = obj.value(QStringLiteral("manual_account")).toString();
    const qint64 lockedUntil = obj.value(QStringLiteral("locked_until")).toVariant().toLongLong();
    const qint64 nowEpoch = QDateTime::currentSecsSinceEpoch();

    for (int i = 0; i < m_accounts.size(); ++i) {
        if (m_accounts[i].email.compare(lockedAccount, Qt::CaseInsensitive) == 0 && lockedUntil > nowEpoch) {
            m_accounts[i].manualLockUntilTs = lockedUntil;
            m_accounts[i].manualLockRemaining = static_cast<int>(lockedUntil - nowEpoch);
        } else {
            m_accounts[i].manualLockUntilTs = 0;
            m_accounts[i].manualLockRemaining = 0;
        }
    }
}

void AccountModel::onSecondTick() {
    const qint64 nowEpoch = QDateTime::currentSecsSinceEpoch();
    bool anyChanged = false;

    for (int i = 0; i < m_accounts.size(); ++i) {
        auto &acc = m_accounts[i];

        if (acc.manualLockUntilTs > 0) {
            const int rem = static_cast<int>(std::max<qint64>(0, acc.manualLockUntilTs - nowEpoch));
            if (rem != acc.manualLockRemaining) {
                acc.manualLockRemaining = rem;
                anyChanged = true;
            }
        }

        const QString g4R = formatCountdown(acc.gemini4ResetTs, nowEpoch);
        if (g4R != acc.gemini4Reset) { acc.gemini4Reset = g4R; anyChanged = true; }

        const QString g38R5 = formatCountdown(acc.gemini38Reset5hTs, nowEpoch);
        if (g38R5 != acc.gemini38Reset5h) { acc.gemini38Reset5h = g38R5; anyChanged = true; }

        const QString cR5 = formatCountdown(acc.claudeReset5hTs, nowEpoch);
        if (cR5 != acc.claudeReset5h) { acc.claudeReset5h = cR5; anyChanged = true; }
    }

    if (anyChanged && !m_accounts.isEmpty()) {
        emit dataChanged(index(0), index(m_accounts.size() - 1), {
            ManualLockRemainingRole, ManualLockRemainingStrRole,
            Gemini4ResetRole, Gemini38Reset5hRole, ClaudeReset5hRole
        });
    }
}

void AccountModel::setIsMasked(bool masked) {
    if (m_isMasked != masked) {
        m_isMasked = masked;
        emit isMaskedChanged(m_isMasked);
        if (!m_accounts.isEmpty()) {
            emit dataChanged(index(0), index(m_accounts.size() - 1), { MaskedNameRole, NameRole, UsernameRole, DisplayUsernameRole });
        }
    }
}

int AccountModel::rowCount(const QModelIndex &parent) const {
    if (parent.isValid()) return 0;
    return m_accounts.size();
}

QVariant AccountModel::data(const QModelIndex &index, int role) const {
    if (!index.isValid() || index.row() < 0 || index.row() >= m_accounts.size()) {
        return QVariant();
    }

    const auto &item = m_accounts.at(index.row());

    switch (role) {
    case IndexRole:
        return index.row() + 1; // 1-based 表格序号
    case EmailRole:
        return item.email;
    case UsernameRole:
        return item.username;
    case DisplayUsernameRole:
        return m_isMasked ? item.maskedUsername : item.username;
    case NameRole:
        return m_isMasked ? item.maskedName : item.name;
    case ShortNameRole:
        return item.shortName;
    case MaskedNameRole:
        return item.maskedName;
    case IsActiveRole:
        return item.isActive;
    case StatusRole:
        return item.status;
    case ManualLockRemainingRole:
        return item.manualLockRemaining;
    case ManualLockRemainingStrRole: {
        if (item.manualLockRemaining <= 0) return QString();
        const int mins = item.manualLockRemaining / 60;
        const int secs = item.manualLockRemaining % 60;
        return mins > 0 ? QStringLiteral("%1m").arg(mins)
                        : QStringLiteral("%1s").arg(secs);
    }
    case Gemini4QuotaRole:
        return item.gemini4Quota;
    case Gemini4ResetRole:
        return item.gemini4Reset;
    case Gemini4ValidRole:
        return item.gemini4Valid;
    case Gemini38Quota5hRole:
        return item.gemini38Quota5h;
    case Gemini38Reset5hRole:
        return item.gemini38Reset5h;
    case Gemini38QuotaWRole:
        return item.gemini38QuotaW;
    case Gemini38ResetWRole:
        return item.gemini38ResetW;
    case ClaudeQuota5hRole:
        return item.claudeQuota5h;
    case ClaudeReset5hRole:
        return item.claudeReset5h;
    case ClaudeQuotaWRole:
        return item.claudeQuotaW;
    case ClaudeResetWRole:
        return item.claudeResetW;
    case HasClaude55Role:
        return item.hasClaude55;
    case IsBlockedRole:
        return item.isBlocked;
    case ValidationUrlRole:
        return item.validationUrl;
    case TierRole:
        return item.tier;
    case IdRole:
        return item.id;
    default:
        return QVariant();
    }
}

QHash<int, QByteArray> AccountModel::roleNames() const {
    QHash<int, QByteArray> roles;
    roles[IndexRole] = "index";
    roles[EmailRole] = "email";
    roles[UsernameRole] = "username";
    roles[DisplayUsernameRole] = "displayUsername";
    roles[NameRole] = "name";
    roles[ShortNameRole] = "shortName";
    roles[MaskedNameRole] = "maskedName";
    roles[IsActiveRole] = "isActive";
    roles[StatusRole] = "status";
    roles[ManualLockRemainingRole] = "manualLockRemaining";
    roles[ManualLockRemainingStrRole] = "manualLockRemainingStr";
    roles[Gemini4QuotaRole] = "gemini4Quota";
    roles[Gemini4ResetRole] = "gemini4Reset";
    roles[Gemini4ValidRole] = "gemini4Valid";
    roles[Gemini38Quota5hRole] = "gemini38Quota5h";
    roles[Gemini38Reset5hRole] = "gemini38Reset5h";
    roles[Gemini38QuotaWRole] = "gemini38QuotaW";
    roles[Gemini38ResetWRole] = "gemini38ResetW";
    roles[ClaudeQuota5hRole] = "claudeQuota5h";
    roles[ClaudeReset5hRole] = "claudeReset5h";
    roles[ClaudeQuotaWRole] = "claudeQuotaW";
    roles[ClaudeResetWRole] = "claudeResetW";
    roles[HasClaude55Role] = "hasClaude55";
    roles[IsBlockedRole] = "isBlocked";
    roles[ValidationUrlRole] = "validationUrl";
    roles[TierRole] = "tier";
    roles[IdRole] = "id";
    return roles;
}

QVariantMap AccountModel::getAccount(int row) const {
    QVariantMap map;
    if (row < 0 || row >= m_accounts.size()) return map;

    const auto &item = m_accounts.at(row);
    map[QStringLiteral("index")] = row + 1;
    map[QStringLiteral("email")] = item.email;
    map[QStringLiteral("username")] = item.username;
    map[QStringLiteral("displayUsername")] = m_isMasked ? item.maskedUsername : item.username;
    map[QStringLiteral("name")] = m_isMasked ? item.maskedName : item.name;
    map[QStringLiteral("shortName")] = item.shortName;
    map[QStringLiteral("maskedName")] = item.maskedName;
    map[QStringLiteral("isActive")] = item.isActive;
    map[QStringLiteral("status")] = item.status;
    map[QStringLiteral("manualLockRemaining")] = item.manualLockRemaining;
    map[QStringLiteral("gemini4Quota")] = item.gemini4Quota;
    map[QStringLiteral("gemini4Reset")] = item.gemini4Reset;
    map[QStringLiteral("gemini4Valid")] = item.gemini4Valid;
    map[QStringLiteral("gemini38Quota5h")] = item.gemini38Quota5h;
    map[QStringLiteral("gemini38Reset5h")] = item.gemini38Reset5h;
    map[QStringLiteral("gemini38QuotaW")] = item.gemini38QuotaW;
    map[QStringLiteral("gemini38ResetW")] = item.gemini38ResetW;
    map[QStringLiteral("claudeQuota5h")] = item.claudeQuota5h;
    map[QStringLiteral("claudeReset5h")] = item.claudeReset5h;
    map[QStringLiteral("claudeQuotaW")] = item.claudeQuotaW;
    map[QStringLiteral("claudeResetW")] = item.claudeResetW;
    map[QStringLiteral("hasClaude55")] = item.hasClaude55;
    map[QStringLiteral("isBlocked")] = item.isBlocked;
    map[QStringLiteral("tier")] = item.tier;
    return map;
}

QString AccountModel::maskName(const QString &raw) const {
    return computeMaskedName(raw);
}

int AccountModel::findIndexByEmail(const QString &email) const {
    for (int i = 0; i < m_accounts.size(); ++i) {
        if (m_accounts[i].email.compare(email, Qt::CaseInsensitive) == 0) {
            return i;
        }
    }
    return -1;
}

// ============================================================================
// ★ v2.50.0 新增: 内存模型账号自定义排序实现
// ============================================================================

void AccountModel::reorderAccounts(const QStringList &orderedEmails)
{
    if (orderedEmails.isEmpty() || m_accounts.size() <= 1) {
        return;
    }

    QHash<QString, AccountItem> itemMap;
    for (const auto &item : m_accounts) {
        itemMap.insert(item.email.trimmed().toLower(), item);
    }

    QList<AccountItem> reordered;
    reordered.reserve(m_accounts.size());
    QSet<QString> placed;

    for (const QString &rawEmail : orderedEmails) {
        const QString lower = rawEmail.trimmed().toLower();
        if (itemMap.contains(lower) && !placed.contains(lower)) {
            reordered.append(itemMap.value(lower));
            placed.insert(lower);
        }
    }

    // 兜底保留未在 orderedEmails 中列出的账号
    for (const auto &item : m_accounts) {
        const QString lower = item.email.trimmed().toLower();
        if (!placed.contains(lower)) {
            reordered.append(item);
            placed.insert(lower);
        }
    }

    beginResetModel();
    m_accounts = std::move(reordered);
    endResetModel();

    emit countChanged();
    emit dataRefreshed();
}

QStringList AccountModel::accountsOrder() const
{
    QStringList list;
    list.reserve(m_accounts.size());
    for (const auto &item : m_accounts) {
        list.append(item.email);
    }
    return list;
}

// ============================================================================
// AccountFilterProxyModel 实现
// ============================================================================

AccountFilterProxyModel::AccountFilterProxyModel(QObject *parent)
    : QSortFilterProxyModel(parent)
{
    setDynamicSortFilter(true);
    connect(this, &QAbstractItemModel::modelReset, this, &AccountFilterProxyModel::updateCounts);
    connect(this, &QAbstractItemModel::rowsInserted, this, &AccountFilterProxyModel::updateCounts);
    connect(this, &QAbstractItemModel::rowsRemoved, this, &AccountFilterProxyModel::updateCounts);
    connect(this, &QAbstractItemModel::layoutChanged, this, &AccountFilterProxyModel::updateCounts);
}

void AccountFilterProxyModel::setSourceModel(QAbstractItemModel *sourceModel) {
    if (this->sourceModel()) {
        disconnect(this->sourceModel(), nullptr, this, nullptr);
    }
    QSortFilterProxyModel::setSourceModel(sourceModel);
    if (sourceModel) {
        connect(sourceModel, &QAbstractItemModel::modelReset, this, &AccountFilterProxyModel::updateCounts);
        connect(sourceModel, &QAbstractItemModel::rowsInserted, this, &AccountFilterProxyModel::updateCounts);
        connect(sourceModel, &QAbstractItemModel::rowsRemoved, this, &AccountFilterProxyModel::updateCounts);
        connect(sourceModel, &QAbstractItemModel::dataChanged, this, &AccountFilterProxyModel::updateCounts);
    }
    updateCounts();
}

void AccountFilterProxyModel::setFilterText(const QString &text) {
    const QString trimmed = text.trimmed();
    if (m_filterText != trimmed) {
        m_filterText = trimmed;
        emit filterTextChanged(m_filterText);
        invalidate();
        updateCounts();
    }
}

void AccountFilterProxyModel::setStatusTab(const QString &tab) {
    const QString lower = tab.toLower();
    if (m_statusTab != lower) {
        m_statusTab = lower;
        emit statusTabChanged(m_statusTab);
        invalidate();
        updateCounts();
    }
}

int AccountFilterProxyModel::totalCount() const {
    return sourceModel() ? sourceModel()->rowCount() : 0;
}

int AccountFilterProxyModel::filteredCount() const {
    return rowCount();
}

void AccountFilterProxyModel::setSortField(const QString &field) {
    if (m_sortField != field) {
        m_sortField = field;
        emit sortFieldChanged(m_sortField);
        if (m_sortField != QStringLiteral("default") && !m_sortField.isEmpty()) {
            sort(0, m_sortOrder);
            invalidate();
        } else {
            sort(-1);
            invalidate();
        }
    }
}

void AccountFilterProxyModel::setSortOrder(Qt::SortOrder order) {
    if (m_sortOrder != order) {
        m_sortOrder = order;
        emit sortOrderChanged(m_sortOrder);
        if (m_sortField != QStringLiteral("default") && !m_sortField.isEmpty()) {
            sort(0, m_sortOrder);
            invalidate();
        }
    }
}

void AccountFilterProxyModel::setSortRule(const QString &field, Qt::SortOrder order) {
    m_sortField = field;
    m_sortOrder = order;
    emit sortFieldChanged(m_sortField);
    emit sortOrderChanged(m_sortOrder);
    if (m_sortField != QStringLiteral("default") && !m_sortField.isEmpty()) {
        sort(0, m_sortOrder);
        invalidate();
    } else {
        sort(-1);
        invalidate();
    }
}

void AccountFilterProxyModel::updateCounts() {
    emit countsChanged();
}

bool AccountFilterProxyModel::filterAcceptsRow(int sourceRow, const QModelIndex &sourceParent) const {
    if (!sourceModel()) return false;
    const QModelIndex idx = sourceModel()->index(sourceRow, 0, sourceParent);
    if (!idx.isValid()) return false;

    // 1. 状态分类 Tab 门禁
    const double gW = sourceModel()->data(idx, AccountModel::Gemini38QuotaWRole).toDouble();
    const double g5h = sourceModel()->data(idx, AccountModel::Gemini38Quota5hRole).toDouble();
    const double cW = sourceModel()->data(idx, AccountModel::ClaudeQuotaWRole).toDouble();
    const bool isBlocked = sourceModel()->data(idx, AccountModel::IsBlockedRole).toBool();
    const bool hasC55 = sourceModel()->data(idx, AccountModel::HasClaude55Role).toBool();

    if (m_statusTab == QStringLiteral("usable")) {
        // 可用: 未风控且拥有周配额
        if (isBlocked || gW <= 0.0001) return false;
    } else if (m_statusTab == QStringLiteral("plentiful")) {
        // 充足: 综合配额充沛 (Gemini 周度 >= 50% 且 Claude 周度 >= 50%)
        if (isBlocked) return false;
        if (gW < 0.50) return false;
        if (hasC55 && cW < 0.50) return false;
    } else if (m_statusTab == QStringLiteral("warning")) {
        // 告急: 处于低水位但未彻底耗尽
        if (gW <= 0.0001) return false;
        const bool isLow = (gW < 0.15 || cW < 0.15 || g5h < 0.10);
        if (!isLow) return false;
    } else if (m_statusTab == QStringLiteral("exhausted")) {
        // 枯竭: 周配额彻底耗尽
        if (gW > 0.0001) return false;
    }

    // 2. 搜索框模糊过滤
    if (!m_filterText.isEmpty()) {
        const QString email = sourceModel()->data(idx, AccountModel::EmailRole).toString();
        const QString shortName = sourceModel()->data(idx, AccountModel::ShortNameRole).toString();
        const QString name = sourceModel()->data(idx, AccountModel::NameRole).toString();

        if (email.contains(m_filterText, Qt::CaseInsensitive) ||
            shortName.contains(m_filterText, Qt::CaseInsensitive) ||
            name.contains(m_filterText, Qt::CaseInsensitive)) {
            return true;
        }

        // 标签穿透支持
        if (m_filterText == QStringLiteral("5.5") && hasC55) return true;
        if (m_filterText == QStringLiteral("4.6") && !hasC55) return true;
        if (m_filterText == QStringLiteral("active") && sourceModel()->data(idx, AccountModel::IsActiveRole).toBool()) return true;

        return false;
    }

    return true;
}

bool AccountFilterProxyModel::lessThan(const QModelIndex &sourceLeft, const QModelIndex &sourceRight) const {
    if (m_sortField == QStringLiteral("index")) {
        const int a = sourceModel()->data(sourceLeft, AccountModel::IndexRole).toInt();
        const int b = sourceModel()->data(sourceRight, AccountModel::IndexRole).toInt();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("account") || m_sortField == QStringLiteral("username")) {
        const QString a = sourceModel()->data(sourceLeft, AccountModel::DisplayUsernameRole).toString().toLower();
        const QString b = sourceModel()->data(sourceRight, AccountModel::DisplayUsernameRole).toString().toLower();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("status")) {
        // Active > Standby > Cooling > Exhausted > Blocked
        const auto statusRank = [](const QModelIndex &idx) -> int {
            if (idx.data(AccountModel::IsActiveRole).toBool()) return 0;
            const QString st = idx.data(AccountModel::StatusRole).toString();
            if (st == QStringLiteral("STANDBY")) return 1;
            if (st == QStringLiteral("COOLING")) return 2;
            if (st == QStringLiteral("EXHAUSTED")) return 3;
            if (idx.data(AccountModel::IsBlockedRole).toBool()) return 4;
            return 5;
        };
        const int a = statusRank(sourceLeft);
        const int b = statusRank(sourceRight);
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("gemini4")) {
        const double a = sourceModel()->data(sourceLeft, AccountModel::Gemini4QuotaRole).toDouble();
        const double b = sourceModel()->data(sourceRight, AccountModel::Gemini4QuotaRole).toDouble();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("gemini38_5h")) {
        const double a = sourceModel()->data(sourceLeft, AccountModel::Gemini38Quota5hRole).toDouble();
        const double b = sourceModel()->data(sourceRight, AccountModel::Gemini38Quota5hRole).toDouble();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("gemini38_w")) {
        const double a = sourceModel()->data(sourceLeft, AccountModel::Gemini38QuotaWRole).toDouble();
        const double b = sourceModel()->data(sourceRight, AccountModel::Gemini38QuotaWRole).toDouble();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("claude_5h")) {
        const double a = sourceModel()->data(sourceLeft, AccountModel::ClaudeQuota5hRole).toDouble();
        const double b = sourceModel()->data(sourceRight, AccountModel::ClaudeQuota5hRole).toDouble();
        if (a != b) return a < b;
    } else if (m_sortField == QStringLiteral("claude_w")) {
        const double a = sourceModel()->data(sourceLeft, AccountModel::ClaudeQuotaWRole).toDouble();
        const double b = sourceModel()->data(sourceRight, AccountModel::ClaudeQuotaWRole).toDouble();
        if (a != b) return a < b;
    }

    return sourceLeft.row() < sourceRight.row();
}

QVariantMap AccountFilterProxyModel::getFilteredAccount(int row) const {
    const QModelIndex proxyIdx = index(row, 0);
    if (!proxyIdx.isValid()) return QVariantMap();
    const QModelIndex srcIdx = mapToSource(proxyIdx);
    auto *srcModel = qobject_cast<AccountModel*>(sourceModel());
    return srcModel ? srcModel->getAccount(srcIdx.row()) : QVariantMap();
}
