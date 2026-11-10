#ifndef BACKEND_H
#define BACKEND_H

#include <QObject>
#include <QString>
#include <QJsonObject>
#include <QJsonDocument>
#include <QJsonArray>
#include <QNetworkAccessManager>
#include <QNetworkRequest>
#include <QNetworkReply>
#include <QProcess>
#include <QTimer>
#include <QFileSystemWatcher>
#include <QUrl>
#include <QUrlQuery>
#include <functional>
#include "models.h"

/**
 * @brief Antigravity Hub 原生后端控制器
 * 
 * 核心职责:
 * 1. 负责向常驻守护服务 (127.0.0.1:18088) 发送异步非阻塞 HTTP REST 信令；
 * 2. 监听本地 manual_override_lock.json 状态与倒计时秒数；
 * 3. 实时检测 systemd user 服务单元存活状态并支持一键自愈；
 * 4. 管理全局脱敏 (Masked) 状态及向 QML 派发通知反馈。
 */
class BackendController : public QObject
{
    Q_OBJECT

    // 暴露给 QML 绑定的状态属性
    Q_PROPERTY(bool busy READ isBusy NOTIFY busyChanged)
    Q_PROPERTY(bool masked READ isMasked WRITE setMasked NOTIFY maskedChanged)
    Q_PROPERTY(QString themeMode READ themeMode WRITE setThemeMode NOTIFY themeModeChanged)
    Q_PROPERTY(QString activeEmail READ activeEmail NOTIFY activeEmailChanged)
    Q_PROPERTY(QString rotationMode READ rotationMode NOTIFY rotationModeChanged)
    Q_PROPERTY(bool isDaemonActive READ isDaemonActive NOTIFY daemonActiveChanged)
    Q_PROPERTY(bool isManualLocked READ isManualLocked NOTIFY manualLockedChanged)
    Q_PROPERTY(int manualLockRemaining READ manualLockRemaining NOTIFY manualLockRemainingChanged)
    Q_PROPERTY(QJsonObject settings READ settings NOTIFY settingsChanged)
    Q_PROPERTY(AccountModel* accountModel READ accountModel WRITE setAccountModel NOTIFY accountModelChanged)

public:
    explicit BackendController(QObject *parent = nullptr);
    ~BackendController() override;

    // 属性读取器
    bool isBusy() const { return m_busyCount > 0; }
    bool isMasked() const { return m_isMasked; }
    QString themeMode() const { return m_themeMode; }
    QString activeEmail() const { return m_activeEmail; }
    QString rotationMode() const { return m_rotationMode; }
    bool isDaemonActive() const { return m_isDaemonActive; }
    bool isManualLocked() const { return m_isManualLocked; }
    int manualLockRemaining() const { return m_manualLockRemaining; }
    QJsonObject settings() const { return m_settings; }
    AccountModel* accountModel() const { return m_accountModel; }

    // 属性写入器
    Q_INVOKABLE void setMasked(bool masked);
    Q_INVOKABLE void setThemeMode(const QString &mode);
    Q_INVOKABLE void setActiveEmail(const QString &email);
    Q_INVOKABLE void setAccountModel(AccountModel *model);

    // QML 调用的核心业务控制方法 (Q_INVOKABLE)
    Q_INVOKABLE void switchAccount(const QString &email);
    Q_INVOKABLE void switchTopGemini();
    Q_INVOKABLE void toggleRotation();
    Q_INVOKABLE void refreshQuota(bool force = false);
    Q_INVOKABLE void triggerPrewarm();
    Q_INVOKABLE void unblockAccount(const QString &email);
    Q_INVOKABLE void saveSettings(const QJsonObject &settings);
    Q_INVOKABLE void unlockManualOverride();
    Q_INVOKABLE void copyToClipboard(const QString &text);
    Q_INVOKABLE void reorderAccounts(const QStringList &orderedEmails);

    // 批量操作与账号纳管扩展 (Milestone 2)
    Q_INVOKABLE void deleteAccounts(const QStringList &emails);
    Q_INVOKABLE void ingestActiveAccount();
    Q_INVOKABLE void startOAuthLogin();
    Q_INVOKABLE void importAccounts(const QString &json);
    Q_INVOKABLE void exportSelectedAccounts(const QStringList &emails);
    Q_INVOKABLE void exportSelected(const QStringList &emails);
    Q_INVOKABLE void batchWarmup(const QStringList &emails);

    // 服务运维与守护自愈
    Q_INVOKABLE void checkDaemonLiveness();
    Q_INVOKABLE void restartDaemon();

    // 请求构造辅助方法
    QNetworkRequest createRequest(const QString &path) const;

signals:
    void busyChanged();
    void maskedChanged();
    void themeModeChanged();
    void languageChanged(const QString &lang);
    void activeEmailChanged();
    void rotationModeChanged();
    void daemonActiveChanged();
    void manualLockedChanged();
    void manualLockRemainingChanged();
    void settingsChanged();

    // 统一 UI 反馈通知信号 (供 QML Toast 或 Banner 监听)
    void notificationRequested(const QString &title, const QString &message, bool isError);
    void operationCompleted(const QString &operation, bool success, const QString &message);

    // 跨组件通信与数据同步信号
    void accountsReloadRequested();
    void accountsExported(const QString &json);
    void accountsReordered(const QStringList &orderedEmails);
    void accountModelChanged();

private slots:
    void onLockDirectoryChanged(const QString &path);
    void onLockFileChanged(const QString &path);
    void onCountdownTimerTick();
    void onLivenessTimerTick();

private:
    void setBusy(bool busy);
    void checkManualLockState();
    void loadInitialState();
    void fetchSettings();
    void fetchRotationStatus();

    void executePost(const QString &path,
                     const QByteArray &data,
                     const QString &contentType,
                     const QString &opName,
                     std::function<void(const QByteArray &body, int statusCode)> onSuccess);
    void executeGet(const QString &path,
                    const QString &opName,
                    std::function<void(const QByteArray &body, int statusCode)> onSuccess);

    // 网络与系统通信组件
    QNetworkAccessManager *m_nam = nullptr;
    QFileSystemWatcher *m_lockWatcher = nullptr;
    QTimer *m_countdownTimer = nullptr;
    QTimer *m_livenessTimer = nullptr;
    QProcess *m_livenessProc = nullptr;

    // 内部状态字
    int m_busyCount = 0;
    bool m_isMasked = false;
    QString m_themeMode = QStringLiteral("system");
    QString m_activeEmail;
    QString m_rotationMode = QStringLiteral("gemini");
    bool m_isDaemonActive = true;
    bool m_isManualLocked = false;
    int m_manualLockRemaining = 0;
    qint64 m_lockUntilTs = 0;
    QJsonObject m_settings;

    // 路径与端点常量
    QString m_baseUrl;
    QString m_hubDir;
    QString m_lockFilePath;

    // 模型引用
    AccountModel *m_accountModel = nullptr;
};

#endif // BACKEND_H
