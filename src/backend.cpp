#include "backend.h"
#include "models.h"
#include <QDir>
#include <QFile>
#include <QDateTime>
#include <QDebug>
#include <QGuiApplication>
#include <QClipboard>
#include <QJsonArray>
#include <QUrl>
#include <QUrlQuery>

BackendController::BackendController(QObject *parent)
    : QObject(parent)
    , m_nam(new QNetworkAccessManager(this))
    , m_lockWatcher(new QFileSystemWatcher(this))
    , m_countdownTimer(new QTimer(this))
    , m_livenessTimer(new QTimer(this))
    , m_busyCount(0)
    , m_isMasked(false)
    , m_activeEmail(QString())
    , m_rotationMode(QStringLiteral("gemini"))
    , m_isDaemonActive(true)
    , m_isManualLocked(false)
    , m_manualLockRemaining(0)
    , m_lockUntilTs(0)
{
    // 确定数据存储根目录 (优先尊重 ANTIGRAVITY_HUB_DIR)
    QString envHub = qEnvironmentVariable("ANTIGRAVITY_HUB_DIR");
    if (envHub.isEmpty()) {
        m_hubDir = QDir::homePath() + QStringLiteral("/.antigravity_hub");
    } else {
        m_hubDir = envHub;
    }
    m_lockFilePath = m_hubDir + QStringLiteral("/manual_override_lock.json");

    QString envBaseUrl = qEnvironmentVariable("ANTIGRAVITY_HUB_BASE_URL");
    if (!envBaseUrl.isEmpty()) {
        m_baseUrl = envBaseUrl;
    } else {
        m_baseUrl = QStringLiteral("http://127.0.0.1:18088");
    }

    // 配置锁定倒计时定时器 (每秒触发一次)
    connect(m_countdownTimer, &QTimer::timeout, this, &BackendController::onCountdownTimerTick);

    // 配置文件系统监听器 (监听目录以防原子删除/创建导致 Inode 丢失)
    if (QDir(m_hubDir).exists()) {
        m_lockWatcher->addPath(m_hubDir);
    }
    if (QFile::exists(m_lockFilePath)) {
        m_lockWatcher->addPath(m_lockFilePath);
    }
    connect(m_lockWatcher, &QFileSystemWatcher::directoryChanged, this, &BackendController::onLockDirectoryChanged);
    connect(m_lockWatcher, &QFileSystemWatcher::fileChanged, this, &BackendController::onLockFileChanged);

    // 配置服务存活性心跳检查 (每 15 秒检查一次 systemd user 状态)
    connect(m_livenessTimer, &QTimer::timeout, this, &BackendController::onLivenessTimerTick);
    m_livenessTimer->start(15000);

    // 初始化状态与数据
    loadInitialState();
    checkManualLockState();
    checkDaemonLiveness();
    fetchSettings();
    fetchRotationStatus();
}

BackendController::~BackendController()
{
    if (m_livenessProc && m_livenessProc->state() != QProcess::NotRunning) {
        m_livenessProc->kill();
        m_livenessProc->waitForFinished(500);
    }
}

void BackendController::setBusy(bool busy)
{
    int prev = m_busyCount;
    if (busy) {
        m_busyCount++;
    } else {
        m_busyCount = qMax(0, m_busyCount - 1);
    }

    if ((prev == 0 && m_busyCount > 0) || (prev > 0 && m_busyCount == 0)) {
        emit busyChanged();
    }
}

void BackendController::setMasked(bool masked)
{
    if (m_isMasked != masked) {
        m_isMasked = masked;
        emit maskedChanged();
    }
}

void BackendController::setThemeMode(const QString &mode)
{
    if (m_themeMode != mode) {
        m_themeMode = mode;
        emit themeModeChanged();
    }
}

void BackendController::setActiveEmail(const QString &email)
{
    const QString trimmed = email.trimmed();
    if (m_activeEmail != trimmed) {
        m_activeEmail = trimmed;
        emit activeEmailChanged();
    }
}

QNetworkRequest BackendController::createRequest(const QString &path) const
{
    QUrl url(m_baseUrl + path);
    QNetworkRequest request(url);
    // Qt 6 原生支持设置传输超时：切换账号/配额全量刷新等重操作给予 25 秒，轻量请求 10 秒，杜绝假超时与 BrokenPipe
    const bool isLongOp = path.startsWith(QStringLiteral("/api/switch")) ||
                          path.startsWith(QStringLiteral("/api/refresh")) ||
                          path.startsWith(QStringLiteral("/api/unblock")) ||
                          path.startsWith(QStringLiteral("/api/warmup"));
    request.setTransferTimeout(isLongOp ? 25000 : 10000);
    return request;
}

void BackendController::executePost(const QString &path,
                                    const QByteArray &data,
                                    const QString &contentType,
                                    const QString &opName,
                                    std::function<void(const QByteArray &body, int statusCode)> onSuccess)
{
    setBusy(true);
    QNetworkRequest request = createRequest(path);
    if (!contentType.isEmpty()) {
        request.setHeader(QNetworkRequest::ContentTypeHeader, contentType);
    }

    QNetworkReply *reply = m_nam->post(request, data);
    connect(reply, &QNetworkReply::finished, this, [this, reply, opName, onSuccess]() {
        setBusy(false);
        int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QByteArray respBody = reply->readAll();

        if (reply->error() == QNetworkReply::NoError && statusCode >= 200 && statusCode < 300) {
            if (onSuccess) {
                onSuccess(respBody, statusCode);
            }
            emit operationCompleted(opName, true, QStringLiteral("Success"));
        } else {
            QString errStr = reply->errorString();
            if (reply->error() == QNetworkReply::ConnectionRefusedError) {
                if (m_isDaemonActive) {
                    m_isDaemonActive = false;
                    emit daemonActiveChanged();
                }
                errStr = tr("Cannot connect to hub daemon (127.0.0.1:18088). Is antigravity-hub.service running?");
            }
            emit notificationRequested(tr("%1 Failed").arg(opName), errStr, true);
            emit operationCompleted(opName, false, errStr);
        }
        reply->deleteLater();
    });
}

void BackendController::executeGet(const QString &path,
                                   const QString &opName,
                                   std::function<void(const QByteArray &body, int statusCode)> onSuccess)
{
    Q_UNUSED(opName);
    QNetworkRequest request = createRequest(path);
    QNetworkReply *reply = m_nam->get(request);

    connect(reply, &QNetworkReply::finished, this, [this, reply, onSuccess]() {
        int statusCode = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        QByteArray respBody = reply->readAll();

        if (reply->error() == QNetworkReply::NoError && statusCode >= 200 && statusCode < 300) {
            if (onSuccess) {
                onSuccess(respBody, statusCode);
            }
        } else {
            if (reply->error() == QNetworkReply::ConnectionRefusedError && m_isDaemonActive) {
                m_isDaemonActive = false;
                emit daemonActiveChanged();
            }
        }
        reply->deleteLater();
    });
}

void BackendController::switchAccount(const QString &email)
{
    QString trimmed = email.trimmed();
    if (trimmed.isEmpty()) return;

    // 契约格式: application/x-www-form-urlencoded, 参数名 email
    QByteArray body = "email=" + QUrl::toPercentEncoding(trimmed);
    executePost(QStringLiteral("/api/switch"), body, QStringLiteral("application/x-www-form-urlencoded"),
                tr("Switch Account"), [this, trimmed](const QByteArray &, int) {
        m_activeEmail = trimmed;
        emit activeEmailChanged();
        emit notificationRequested(tr("Account Switched"),
                                  tr("Switched to %1").arg(trimmed), false);
        checkManualLockState();
    });
}

void BackendController::switchTopGemini()
{
    // 契约: POST /api/switch_top_gemini
    executePost(QStringLiteral("/api/switch_top_gemini"), QByteArray(), QString(),
                tr("TopG Switch"), [this](const QByteArray &body, int) {
        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(body, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            QJsonObject obj = doc.object();
            bool ok = obj.value(QStringLiteral("success")).toBool();
            QString msg = obj.value(QStringLiteral("msg")).toString();
            QString targetEmail = obj.value(QStringLiteral("target_email")).toString();

            if (ok) {
                if (!targetEmail.isEmpty()) {
                    m_activeEmail = targetEmail;
                    emit activeEmailChanged();
                }
                emit notificationRequested(tr("TopG Switch"), msg, false);
            } else {
                emit notificationRequested(tr("TopG Switch Failed"), msg, true);
            }
        } else {
            emit notificationRequested(tr("TopG Switch"),
                                      tr("Best Gemini account switched successfully"), false);
        }
        checkManualLockState();
    });
}

void BackendController::toggleRotation()
{
    // 契约: POST /api/toggle-rotation
    executePost(QStringLiteral("/api/toggle-rotation"), QByteArray(), QString(),
                tr("Toggle Rotation"), [this](const QByteArray &body, int) {
        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(body, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            QJsonObject obj = doc.object();
            m_rotationMode = obj.value(QStringLiteral("mode")).toString(QStringLiteral("gemini"));
            emit rotationModeChanged();
            emit notificationRequested(tr("Rotation Mode"),
                                      tr("Mode changed to: %1").arg(m_rotationMode), false);
        }
    });
}

void BackendController::refreshQuota(bool force)
{
    Q_UNUSED(force);
    // 契约: POST /api/refresh
    executePost(QStringLiteral("/api/refresh"), QByteArray(), QString(),
                tr("Refresh Quotas"), [this](const QByteArray &, int) {
        emit notificationRequested(tr("Refresh Quotas"),
                                  tr("All accounts quota refreshed from Google"), false);
    });
}

void BackendController::triggerPrewarm()
{
    // 关键映射: 实机服务端端点为 /api/warmup-all
    executePost(QStringLiteral("/api/warmup-all"), QByteArray(), QString(),
                tr("Fleet Prewarm"), [this](const QByteArray &, int) {
        emit notificationRequested(tr("Fleet Prewarm"),
                                  tr("Hourly staggered fleet prewarm pipeline triggered"), false);
    });
}

void BackendController::unblockAccount(const QString &email)
{
    QString trimmed = email.trimmed();
    if (trimmed.isEmpty()) return;

    // 契约: POST /api/unblock, 表单参数 email
    QByteArray body = "email=" + QUrl::toPercentEncoding(trimmed);
    executePost(QStringLiteral("/api/unblock"), body, QStringLiteral("application/x-www-form-urlencoded"),
                tr("Unblock Account"), [this, trimmed](const QByteArray &, int) {
        emit notificationRequested(tr("Unblock Wizard"),
                                  tr("Unblock initiated for %1. Browser opened if puzzle required.").arg(trimmed), false);
    });
}

void BackendController::saveSettings(const QJsonObject &settings)
{
    // 契约: POST /api/settings, JSON 载荷
    QByteArray body = QJsonDocument(settings).toJson(QJsonDocument::Compact);
    executePost(QStringLiteral("/api/settings"), body, QStringLiteral("application/json; charset=utf-8"),
                tr("Save Settings"), [this, settings](const QByteArray &respBody, int) {
        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(respBody, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            m_settings = doc.object();
        } else {
            m_settings = settings;
        }

        if (m_settings.contains(QStringLiteral("rotation_mode"))) {
            m_rotationMode = m_settings.value(QStringLiteral("rotation_mode")).toString();
            emit rotationModeChanged();
        }
        if (m_settings.contains(QStringLiteral("theme_mode"))) {
            setThemeMode(m_settings.value(QStringLiteral("theme_mode")).toString());
        }
        if (m_settings.contains(QStringLiteral("account_mask"))) {
            setMasked(m_settings.value(QStringLiteral("account_mask")).toBool());
        }
        if (m_settings.contains(QStringLiteral("language"))) {
            emit languageChanged(m_settings.value(QStringLiteral("language")).toString());
        }
        emit settingsChanged();
        emit notificationRequested(tr("Settings Saved"),
                                  tr("Hub preferences updated successfully"), false);
    });
}

void BackendController::unlockManualOverride()
{
    // 契约: POST /api/unlock
    executePost(QStringLiteral("/api/unlock"), QByteArray(), QString(),
                tr("Unlock Override"), [this](const QByteArray &, int) {
        m_isManualLocked = false;
        m_manualLockRemaining = 0;
        m_countdownTimer->stop();
        emit manualLockedChanged();
        emit manualLockRemainingChanged();
        emit notificationRequested(tr("Manual Lock Cleared"),
                                  tr("Automatic watchdog rotation resumed"), false);
    });
}

void BackendController::copyToClipboard(const QString &text)
{
    if (QClipboard *clipboard = QGuiApplication::clipboard()) {
        clipboard->setText(text);
        emit notificationRequested(tr("Antigravity Hub"), tr("Copied to clipboard"), false);
    }
}

void BackendController::deleteAccounts(const QStringList &emails)
{
    if (emails.isEmpty()) return;

    QJsonObject reqObj;
    QJsonArray arr;
    for (const QString &email : emails) {
        const QString trimmed = email.trimmed();
        if (!trimmed.isEmpty()) {
            arr.append(trimmed);
        }
    }
    if (arr.isEmpty()) return;
    reqObj[QStringLiteral("emails")] = arr;

    const QByteArray body = QJsonDocument(reqObj).toJson(QJsonDocument::Compact);
    const int count = arr.size();

    executePost(QStringLiteral("/api/delete_accounts"), body,
                QStringLiteral("application/json; charset=utf-8"),
                tr("Delete Accounts"),
                [this, count](const QByteArray &, int) {
        emit accountsReloadRequested();
        emit notificationRequested(tr("Accounts Deleted"),
                                  tr("Successfully deleted %n account(s).", "", count),
                                  false);
        refreshQuota(true);
    });
}

void BackendController::ingestActiveAccount()
{
    executePost(QStringLiteral("/api/ingest_active"), QByteArray(),
                QStringLiteral("application/json; charset=utf-8"),
                tr("Ingest Active Account"),
                [this](const QByteArray &respBody, int) {
        QJsonParseError parseErr;
        const QJsonDocument doc = QJsonDocument::fromJson(respBody, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            const QJsonObject obj = doc.object();
            const bool ok = obj.value(QStringLiteral("status")).toString() == QLatin1String("ok");
            const QString email = obj.value(QStringLiteral("email")).toString();
            const QString msg = obj.value(QStringLiteral("message")).toString();

            if (ok) {
                emit accountsReloadRequested();
                emit notificationRequested(tr("Account Ingested"),
                                          email.isEmpty() ? tr("Active system credential ingested successfully.")
                                                          : tr("Ingested: %1").arg(email),
                                          false);
                refreshQuota(true);
            } else {
                emit notificationRequested(tr("Ingest Failed"),
                                          msg.isEmpty() ? tr("Could not ingest active system account.") : msg,
                                          true);
            }
        } else {
            emit accountsReloadRequested();
            emit notificationRequested(tr("Account Ingested"),
                                      tr("Active system credential ingested successfully."),
                                      false);
            refreshQuota(true);
        }
    });
}

void BackendController::startOAuthLogin()
{
    QJsonObject reqObj;
    reqObj[QStringLiteral("open_browser")] = true;
    reqObj[QStringLiteral("isolated")] = false;
    const QByteArray body = QJsonDocument(reqObj).toJson(QJsonDocument::Compact);

    executePost(QStringLiteral("/api/oauth/start"), body,
                QStringLiteral("application/json; charset=utf-8"),
                tr("OAuth Login"),
                [this](const QByteArray &respBody, int) {
        QJsonParseError parseErr;
        const QJsonDocument doc = QJsonDocument::fromJson(respBody, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            emit notificationRequested(tr("OAuth Login Started"),
                                      tr("Browser opened for Google account authorization."),
                                      false);
        } else {
            emit notificationRequested(tr("OAuth Login"),
                                      tr("Browser authorization flow initiated."),
                                      false);
        }
    });
}

void BackendController::importAccounts(const QString &json)
{
    const QString trimmed = json.trimmed();
    if (trimmed.isEmpty()) return;

    QJsonObject reqObj;
    reqObj[QStringLiteral("json_data")] = trimmed;
    const QByteArray body = QJsonDocument(reqObj).toJson(QJsonDocument::Compact);

    executePost(QStringLiteral("/api/import"), body,
                QStringLiteral("application/json; charset=utf-8"),
                tr("Import Accounts"),
                [this](const QByteArray &respBody, int) {
        QJsonParseError parseErr;
        const QJsonDocument doc = QJsonDocument::fromJson(respBody, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            const QJsonObject obj = doc.object();
            const bool ok = obj.value(QStringLiteral("status")).toString() == QLatin1String("ok");
            const int added = obj.value(QStringLiteral("added")).toInt();
            const int updated = obj.value(QStringLiteral("updated")).toInt();
            const QString msg = obj.value(QStringLiteral("message")).toString();

            if (ok) {
                emit accountsReloadRequested();
                emit notificationRequested(tr("Import Complete"),
                                          tr("Successfully added %1 and updated %2 account(s).").arg(added).arg(updated),
                                          false);
                refreshQuota(true);
            } else {
                emit notificationRequested(tr("Import Failed"),
                                          msg.isEmpty() ? tr("Failed to parse or import account credentials.") : msg,
                                          true);
            }
        } else {
            emit accountsReloadRequested();
            emit notificationRequested(tr("Import Complete"),
                                      tr("Accounts imported successfully."),
                                      false);
            refreshQuota(true);
        }
    });
}

void BackendController::exportSelectedAccounts(const QStringList &emails)
{
    if (emails.isEmpty()) return;

    QJsonObject reqObj;
    QJsonArray arr;
    for (const QString &email : emails) {
        const QString trimmed = email.trimmed();
        if (!trimmed.isEmpty()) {
            arr.append(trimmed);
        }
    }
    if (arr.isEmpty()) return;
    reqObj[QStringLiteral("emails")] = arr;

    const QByteArray body = QJsonDocument(reqObj).toJson(QJsonDocument::Compact);
    const int count = arr.size();

    executePost(QStringLiteral("/api/export_selected"), body,
                QStringLiteral("application/json; charset=utf-8"),
                tr("Export Accounts"),
                [this, count](const QByteArray &respBody, int) {
        const QString jsonStr = QString::fromUtf8(respBody);
        emit accountsExported(jsonStr);
        copyToClipboard(jsonStr);
        emit notificationRequested(tr("Export Complete"),
                                  tr("Exported %n account credential(s) to clipboard.", "", count),
                                  false);
    });
}

void BackendController::exportSelected(const QStringList &emails)
{
    exportSelectedAccounts(emails);
}

void BackendController::batchWarmup(const QStringList &emails)
{
    Q_UNUSED(emails);
    triggerPrewarm();
}

void BackendController::checkDaemonLiveness()
{
    if (!m_livenessProc) {
        m_livenessProc = new QProcess(this);
        connect(m_livenessProc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
                this, [this](int exitCode, QProcess::ExitStatus) {
            QString stdoutStr = QString::fromUtf8(m_livenessProc->readAllStandardOutput()).trimmed();
            bool active = (exitCode == 0 && stdoutStr == QStringLiteral("active"));

            if (m_isDaemonActive != active) {
                m_isDaemonActive = active;
                emit daemonActiveChanged();
                if (!active) {
                    emit notificationRequested(tr("Daemon Inactive"),
                                              tr("Antigravity Hub service is not running."), true);
                }
            }
        });
    }

    if (m_livenessProc->state() == QProcess::NotRunning) {
        m_livenessProc->start(QStringLiteral("systemctl"),
                              QStringList() << QStringLiteral("--user")
                                            << QStringLiteral("is-active")
                                            << QStringLiteral("antigravity-hub.service"));
    }
}

void BackendController::restartDaemon()
{
    setBusy(true);
    QProcess *proc = new QProcess(this);
    connect(proc, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, [this, proc](int exitCode, QProcess::ExitStatus) {
        setBusy(false);
        if (exitCode == 0) {
            m_isDaemonActive = true;
            emit daemonActiveChanged();
            emit notificationRequested(tr("Daemon Revived"),
                                      tr("Antigravity Hub service successfully restarted."), false);
            fetchSettings();
            fetchRotationStatus();
        } else {
            QString stderrStr = QString::fromUtf8(proc->readAllStandardError()).trimmed();
            emit notificationRequested(tr("Revival Failed"),
                                      stderrStr.isEmpty() ? tr("Failed to restart systemd service.") : stderrStr, true);
        }
        proc->deleteLater();
    });

    proc->start(QStringLiteral("systemctl"),
                QStringList() << QStringLiteral("--user")
                              << QStringLiteral("restart")
                              << QStringLiteral("antigravity-hub.service"));
}

void BackendController::onLockDirectoryChanged(const QString &)
{
    if (QFile::exists(m_lockFilePath) && !m_lockWatcher->files().contains(m_lockFilePath)) {
        m_lockWatcher->addPath(m_lockFilePath);
    }
    checkManualLockState();
}

void BackendController::onLockFileChanged(const QString &)
{
    if (QFile::exists(m_lockFilePath) && !m_lockWatcher->files().contains(m_lockFilePath)) {
        m_lockWatcher->addPath(m_lockFilePath);
    }
    checkManualLockState();
}

void BackendController::onCountdownTimerTick()
{
    if (!m_isManualLocked) {
        m_countdownTimer->stop();
        return;
    }

    qint64 now = QDateTime::currentSecsSinceEpoch();
    int remaining = static_cast<int>(qMax(qint64(0), m_lockUntilTs - now));

    if (remaining != m_manualLockRemaining) {
        m_manualLockRemaining = remaining;
        emit manualLockRemainingChanged();
    }

    if (remaining <= 0) {
        m_isManualLocked = false;
        m_countdownTimer->stop();
        emit manualLockedChanged();
    }
}

void BackendController::onLivenessTimerTick()
{
    checkDaemonLiveness();
}

void BackendController::checkManualLockState()
{
    QFile file(m_lockFilePath);
    if (!file.exists()) {
        if (m_isManualLocked) {
            m_isManualLocked = false;
            m_manualLockRemaining = 0;
            m_countdownTimer->stop();
            emit manualLockedChanged();
            emit manualLockRemainingChanged();
        }
        return;
    }

    if (file.open(QIODevice::ReadOnly)) {
        QByteArray data = file.readAll();
        file.close();
        QJsonDocument doc = QJsonDocument::fromJson(data);
        if (doc.isObject()) {
            QJsonObject obj = doc.object();
            qint64 lockUntil = obj.value(QStringLiteral("locked_until")).toVariant().toLongLong();
            qint64 now = QDateTime::currentSecsSinceEpoch();

            if (lockUntil > now) {
                m_lockUntilTs = lockUntil;
                m_manualLockRemaining = static_cast<int>(lockUntil - now);

                QString lockedAccount = obj.value(QStringLiteral("manual_account")).toString();
                if (lockedAccount.isEmpty()) {
                    lockedAccount = obj.value(QStringLiteral("account")).toString();
                }

                // Only treat as manually locked if lockedAccount matches the current active account
                // (or if active account was not yet initialized). Never overwrite a known active account with a stale lock!
                if (m_activeEmail.isEmpty() && !lockedAccount.isEmpty()) {
                    m_activeEmail = lockedAccount;
                    emit activeEmailChanged();
                }

                const bool lockMatchesActive = (!m_activeEmail.isEmpty() && !lockedAccount.isEmpty() &&
                                                m_activeEmail.compare(lockedAccount, Qt::CaseInsensitive) == 0);

                if (lockMatchesActive) {
                    if (!m_isManualLocked) {
                        m_isManualLocked = true;
                        emit manualLockedChanged();
                    }
                    emit manualLockRemainingChanged();

                    if (!m_countdownTimer->isActive()) {
                        m_countdownTimer->start(1000);
                    }
                    return;
                }
            }
        }
    }

    if (m_isManualLocked) {
        m_isManualLocked = false;
        m_manualLockRemaining = 0;
        m_countdownTimer->stop();
        emit manualLockedChanged();
        emit manualLockRemainingChanged();
    }
}

void BackendController::loadInitialState()
{
    QString dataFile = m_hubDir + QStringLiteral("/data/accounts_hub.json");
    if (!QFile::exists(dataFile)) {
        dataFile = m_hubDir + QStringLiteral("/accounts_hub.json");
    }

    QFile file(dataFile);
    if (file.open(QIODevice::ReadOnly)) {
        QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
        file.close();
        if (doc.isObject()) {
            QJsonObject root = doc.object();
            QString active = root.value(QStringLiteral("active_email")).toString();
            if (!active.isEmpty()) {
                m_activeEmail = active;
                emit activeEmailChanged();
            }
        }
    }
}

void BackendController::fetchSettings()
{
    executeGet(QStringLiteral("/api/settings"), tr("Fetch Settings"),
               [this](const QByteArray &body, int) {
        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(body, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            m_settings = doc.object();
            if (m_settings.contains(QStringLiteral("account_mask"))) {
                setMasked(m_settings.value(QStringLiteral("account_mask")).toBool());
            }
            if (m_settings.contains(QStringLiteral("theme_mode"))) {
                setThemeMode(m_settings.value(QStringLiteral("theme_mode")).toString());
            }
            if (m_settings.contains(QStringLiteral("language"))) {
                emit languageChanged(m_settings.value(QStringLiteral("language")).toString());
            }
            if (m_settings.contains(QStringLiteral("rotation_mode"))) {
                m_rotationMode = m_settings.value(QStringLiteral("rotation_mode")).toString();
                emit rotationModeChanged();
            }
            emit settingsChanged();
        }
    });
}

void BackendController::fetchRotationStatus()
{
    executeGet(QStringLiteral("/api/rotation-status"), tr("Fetch Rotation"),
               [this](const QByteArray &body, int) {
        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(body, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            QJsonObject obj = doc.object();
            m_rotationMode = obj.value(QStringLiteral("mode")).toString(QStringLiteral("gemini"));
            emit rotationModeChanged();
        }
    });
}

void BackendController::setAccountModel(AccountModel *model)
{
    if (m_accountModel != model) {
        m_accountModel = model;
        emit accountModelChanged();
    }
}

void BackendController::reorderAccounts(const QStringList &orderedEmails)
{
    if (orderedEmails.isEmpty()) return;

    // ------------------------------------------------------------------------
    // 步骤 1: 立即更新内存模型 (零延迟交互响应)
    // ------------------------------------------------------------------------
    if (m_accountModel) {
        m_accountModel->reorderAccounts(orderedEmails);
    }
    emit accountsReordered(orderedEmails);

    // ------------------------------------------------------------------------
    // 步骤 2: 构造 application/x-www-form-urlencoded POST 请求发送至守护服务
    // 格式契约: order[]=<url_encoded_email_1>&order[]=<url_encoded_email_2>...
    // ------------------------------------------------------------------------
    QByteArray postData;
    for (int i = 0; i < orderedEmails.size(); ++i) {
        const QString em = orderedEmails[i].trimmed();
        if (em.isEmpty()) continue;
        if (!postData.isEmpty()) {
            postData.append('&');
        }
        postData.append("order[]=");
        postData.append(QUrl::toPercentEncoding(em));
    }

    executePost(QStringLiteral("/api/reorder"), postData,
                QStringLiteral("application/x-www-form-urlencoded"),
                tr("Reorder Accounts"),
                [this](const QByteArray &, int) {
        emit notificationRequested(tr("Reorder Accounts"),
                                  tr("Account order persisted successfully"), false);
    });

    // ------------------------------------------------------------------------
    // 步骤 3: 兜底与直接持久化更新 accounts_hub.json (离线容灾防护)
    // 确保在守护服务离线或单元测试环境下，自定义顺序 100% 保持持久化
    // ------------------------------------------------------------------------
    QString accountsPath = m_hubDir + QStringLiteral("/data/accounts_hub.json");
    if (!QFile::exists(accountsPath) && QFile::exists(m_hubDir + QStringLiteral("/accounts_hub.json"))) {
        accountsPath = m_hubDir + QStringLiteral("/accounts_hub.json");
    }

    QFile file(accountsPath);
    if (file.open(QIODevice::ReadOnly)) {
        const QByteArray rawBytes = file.readAll();
        file.close();

        QJsonParseError parseErr;
        QJsonDocument doc = QJsonDocument::fromJson(rawBytes, &parseErr);
        if (parseErr.error == QJsonParseError::NoError && doc.isObject()) {
            QJsonObject root = doc.object();

            // 1. 添加/更新顶层 accounts_order JSON 数组
            QJsonArray orderArr;
            for (const QString &em : orderedEmails) {
                const QString trimmed = em.trimmed();
                if (!trimmed.isEmpty()) {
                    orderArr.append(trimmed);
                }
            }
            root[QStringLiteral("accounts_order")] = orderArr;

            // 2. 同步重排 accounts 对象字段
            const QJsonObject oldAccounts = root.value(QStringLiteral("accounts")).toObject();
            QJsonObject reorderedAccounts;
            for (const QString &em : orderedEmails) {
                const QString trimmed = em.trimmed();
                if (oldAccounts.contains(trimmed)) {
                    reorderedAccounts[trimmed] = oldAccounts.value(trimmed);
                }
            }
            for (auto it = oldAccounts.constBegin(); it != oldAccounts.constEnd(); ++it) {
                if (!reorderedAccounts.contains(it.key())) {
                    reorderedAccounts[it.key()] = it.value();
                }
            }
            root[QStringLiteral("accounts")] = reorderedAccounts;

            // 3. 回写主存储
            if (file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                file.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
                file.close();
            }

            // 4. 若存在本地根目录备份文件 (~/.antigravity_hub/accounts_hub.json)，同步双写
            const QString backupPath = m_hubDir + QStringLiteral("/accounts_hub.json");
            if (backupPath != accountsPath && QFile::exists(backupPath)) {
                QFile backupFile(backupPath);
                if (backupFile.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
                    backupFile.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
                    backupFile.close();
                }
            }
        }
    }
}
