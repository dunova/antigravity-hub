#include <QtTest>
#include <QTcpServer>
#include <QTcpSocket>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QUrlQuery>
#include <QDateTime>
#include <QElapsedTimer>
#include <memory>

#include "backend.h"
#include "models.h"

// =============================================================================
// Mock HTTP Server for Empirical Stress Testing
// =============================================================================

class MockHttpServer : public QTcpServer {
    Q_OBJECT
public:
    struct Request {
        QString method;
        QString path;
        QMap<QString, QString> headers;
        QByteArray body;
    };

    explicit MockHttpServer(QObject *parent = nullptr) : QTcpServer(parent) {
        connect(this, &QTcpServer::newConnection, this, &MockHttpServer::onNewConnection);
    }

    void reset() {
        requests.clear();
        customResponseStatus = 200;
        customResponseBody = QByteArray("{\"status\":\"ok\"}");
        customResponseContentType = QStringLiteral("application/json; charset=utf-8");
        hang = false;
        holdConnections = false;
        heldSockets.clear();
    }

    QList<Request> requests;
    int customResponseStatus = 200;
    QByteArray customResponseBody = QByteArray("{\"status\":\"ok\"}");
    QString customResponseContentType = QStringLiteral("application/json; charset=utf-8");
    bool hang = false;
    bool holdConnections = false;
    QList<QTcpSocket*> heldSockets;

    void releaseOneSocket() {
        if (!heldSockets.isEmpty()) {
            QTcpSocket *sock = heldSockets.takeFirst();
            sendResponse(sock, customResponseStatus, customResponseBody, customResponseContentType);
        }
    }

    void releaseAllSockets() {
        while (!heldSockets.isEmpty()) {
            releaseOneSocket();
        }
    }

signals:
    void requestReceived(const MockHttpServer::Request &req);

private slots:
    void onNewConnection() {
        QTcpSocket *socket = nextPendingConnection();
        if (!socket) return;

        connect(socket, &QTcpSocket::readyRead, this, [this, socket]() {
            QByteArray raw = socket->readAll();
            int headerEnd = raw.indexOf("\r\n\r\n");
            if (headerEnd == -1) return;

            QByteArray headerPart = raw.left(headerEnd);
            QByteArray bodyPart = raw.mid(headerEnd + 4);

            QList<QByteArray> lines = headerPart.split('\n');
            if (lines.isEmpty()) return;

            QByteArray requestLine = lines[0].trimmed();
            QList<QByteArray> parts = requestLine.split(' ');
            if (parts.size() < 2) return;

            Request req;
            req.method = QString::fromUtf8(parts[0]);
            req.path = QString::fromUtf8(parts[1]);

            for (int i = 1; i < lines.size(); ++i) {
                QByteArray line = lines[i].trimmed();
                int colon = line.indexOf(':');
                if (colon != -1) {
                    QString key = QString::fromUtf8(line.left(colon).trimmed()).toLower();
                    QString val = QString::fromUtf8(line.mid(colon + 1).trimmed());
                    req.headers[key] = val;
                }
            }

            req.body = bodyPart;
            requests.append(req);
            emit requestReceived(req);

            if (hang) {
                // Do not respond at all; client will timeout
                return;
            }

            if (holdConnections) {
                heldSockets.append(socket);
                return;
            }

            sendResponse(socket, customResponseStatus, customResponseBody, customResponseContentType);
        });
    }

    void sendResponse(QTcpSocket *socket, int status, const QByteArray &body, const QString &contentType) {
        if (!socket || socket->state() != QAbstractSocket::ConnectedState) return;

        QByteArray resp;
        resp += "HTTP/1.1 " + QByteArray::number(status) + " OK\r\n";
        resp += "Content-Type: " + contentType.toUtf8() + "\r\n";
        resp += "Content-Length: " + QByteArray::number(body.size()) + "\r\n";
        resp += "Connection: close\r\n\r\n";
        resp += body;

        socket->write(resp);
        socket->flush();
        socket->disconnectFromHost();
    }
};

// =============================================================================
// Empirical Stress Test Suite
// =============================================================================

class StressM2BackendTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();

    // Challenge 1: REST endpoint payloads and URL routing
    void stressRestSwitchPayloadAndRouting();
    void stressRestUnblockPayloadAndRouting();
    void stressRestPrewarmStrictWarmupAll();
    void stressRestSettingsJsonPayload();
    void stressRestAuxiliaryEndpoints();

    // Challenge 2: Network failure and timeout handling
    void stressConnectionRefusedHandling();
    void stressHttp500FailureHandling();
    void stressTimeoutEnforcement();

    // Challenge 3: manual_override_lock.json dynamic lifecycle
    void stressLockLifecycleCreationAndUpdate();
    void stressLockLifecycleDeletionAndInotifyRearm();
    void stressLockLifecycleUnlockApiAction();

    // Challenge 4: Concurrent request handling and busy counter reentrancy
    void stressConcurrentRequestsAndBusyReentrancy();

private:
    void waitForInit(BackendController &backend);

    std::unique_ptr<MockHttpServer> m_server;
    int m_serverPort = 0;
    QString m_serverBaseUrl;
};

void StressM2BackendTests::initTestCase() {
    m_server = std::make_unique<MockHttpServer>();
    QVERIFY2(m_server->listen(QHostAddress::LocalHost, 0), "Failed to bind MockHttpServer");
    m_serverPort = m_server->serverPort();
    m_serverBaseUrl = QStringLiteral("http://127.0.0.1:%1").arg(m_serverPort);
    qDebug() << "MockHttpServer listening on" << m_serverBaseUrl;
}

void StressM2BackendTests::cleanupTestCase() {
    if (m_server) {
        m_server->close();
    }
}

void StressM2BackendTests::waitForInit(BackendController &backend) {
    Q_UNUSED(backend);
    // BackendController constructor fires fetchSettings() and fetchRotationStatus() asynchronously
    QTRY_VERIFY_WITH_TIMEOUT(m_server->requests.size() >= 2, 2000);
    m_server->reset();
}

// -----------------------------------------------------------------------------
// Challenge 1: REST Endpoint Payloads & Routing
// -----------------------------------------------------------------------------

void StressM2BackendTests::stressRestSwitchPayloadAndRouting() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    QSignalSpy spyEmail(&backend, &BackendController::activeEmailChanged);

    // Test with email containing special characters (+, &, =, @)
    const QString targetEmail = QStringLiteral("alice+dev&test=1@antigravity.io");
    backend.switchAccount(targetEmail);

    // Wait for operationCompleted signal
    QVERIFY2(spyOp.wait(3000), "Timed out waiting for switchAccount completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), true); // success == true
    QCOMPARE(backend.activeEmail(), targetEmail);
    QCOMPARE(spyEmail.count(), 1);

    // Assert request received by mock server
    QCOMPARE(m_server->requests.size(), 1);
    const auto req = m_server->requests.first();
    QCOMPARE(req.method, QStringLiteral("POST"));
    QCOMPARE(req.path, QStringLiteral("/api/switch"));
    QCOMPARE(req.headers.value(QStringLiteral("content-type")),
             QStringLiteral("application/x-www-form-urlencoded"));

    // Verify application/x-www-form-urlencoded decoding
    QUrlQuery query(QString::fromUtf8(req.body));
    QVERIFY2(query.hasQueryItem(QStringLiteral("email")), "Missing 'email' form parameter");
    QCOMPARE(query.queryItemValue(QStringLiteral("email"), QUrl::FullyDecoded), targetEmail);
}

void StressM2BackendTests::stressRestUnblockPayloadAndRouting() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);

    const QString unblockEmail = QStringLiteral("blocked+solver#99@example.com");
    backend.unblockAccount(unblockEmail);

    QVERIFY2(spyOp.wait(3000), "Timed out waiting for unblockAccount completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), true);

    QCOMPARE(m_server->requests.size(), 1);
    const auto req = m_server->requests.first();
    QCOMPARE(req.method, QStringLiteral("POST"));
    QCOMPARE(req.path, QStringLiteral("/api/unblock"));
    QCOMPARE(req.headers.value(QStringLiteral("content-type")),
             QStringLiteral("application/x-www-form-urlencoded"));

    QUrlQuery query(QString::fromUtf8(req.body));
    QVERIFY2(query.hasQueryItem(QStringLiteral("email")), "Missing 'email' form parameter");
    QCOMPARE(query.queryItemValue(QStringLiteral("email"), QUrl::FullyDecoded), unblockEmail);
}

void StressM2BackendTests::stressRestPrewarmStrictWarmupAll() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);

    backend.triggerPrewarm();

    QVERIFY2(spyOp.wait(3000), "Timed out waiting for triggerPrewarm completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), true);

    QCOMPARE(m_server->requests.size(), 1);
    const auto req = m_server->requests.first();
    QCOMPARE(req.method, QStringLiteral("POST"));

    // ★ CRITICAL VERIFICATION: Must strictly target /api/warmup-all
    QCOMPARE(req.path, QStringLiteral("/api/warmup-all"));
    QVERIFY2(req.path != QStringLiteral("/api/prewarm"), "FATAL: triggerPrewarm targeted non-existent /api/prewarm");
    QVERIFY2(req.path != QStringLiteral("/api/warmup"), "FATAL: triggerPrewarm targeted single-account /api/warmup");
}

void StressM2BackendTests::stressRestSettingsJsonPayload() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    QSignalSpy spySettings(&backend, &BackendController::settingsChanged);

    QJsonObject inputSettings;
    inputSettings["rotation_mode"] = QStringLiteral("gemini");
    inputSettings["min_quota_threshold"] = 0.15;
    inputSettings["auto_unblock"] = true;
    inputSettings["max_concurrency"] = 16;
    QJsonArray tags;
    tags.append("fast");
    tags.append("reliable");
    inputSettings["tags"] = tags;

    // Server echoes back updated settings
    m_server->customResponseBody = QJsonDocument(inputSettings).toJson();

    backend.saveSettings(inputSettings);

    QVERIFY2(spyOp.wait(3000), "Timed out waiting for saveSettings completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), true);
    QCOMPARE(spySettings.count(), 1);

    QCOMPARE(m_server->requests.size(), 1);
    const auto req = m_server->requests.first();
    QCOMPARE(req.method, QStringLiteral("POST"));
    QCOMPARE(req.path, QStringLiteral("/api/settings"));
    QVERIFY2(req.headers.value(QStringLiteral("content-type")).contains("application/json"),
             "Content-Type must be application/json");

    // Verify valid JSON body matches inputSettings
    QJsonParseError parseErr;
    QJsonDocument doc = QJsonDocument::fromJson(req.body, &parseErr);
    QCOMPARE(parseErr.error, QJsonParseError::NoError);
    QVERIFY(doc.isObject());
    QJsonObject sentObj = doc.object();
    QCOMPARE(sentObj["rotation_mode"].toString(), QStringLiteral("gemini"));
    QCOMPARE(sentObj["min_quota_threshold"].toDouble(), 0.15);
    QCOMPARE(sentObj["auto_unblock"].toBool(), true);
    QCOMPARE(sentObj["max_concurrency"].toInt(), 16);
    QCOMPARE(sentObj["tags"].toArray().size(), 2);
}

void StressM2BackendTests::stressRestAuxiliaryEndpoints() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    // 1. switchTopGemini -> POST /api/switch_top_gemini
    {
        QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
        m_server->customResponseBody = QByteArray("{\"success\":true,\"target_email\":\"top@gmail.com\",\"msg\":\"ok\"}");
        backend.switchTopGemini();
        QVERIFY(spyOp.wait(3000));
        QCOMPARE(m_server->requests.last().path, QStringLiteral("/api/switch_top_gemini"));
        QCOMPARE(backend.activeEmail(), QStringLiteral("top@gmail.com"));
    }

    // 2. toggleRotation -> POST /api/toggle-rotation
    {
        QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
        m_server->customResponseBody = QByteArray("{\"mode\":\"round_robin\"}");
        backend.toggleRotation();
        QVERIFY(spyOp.wait(3000));
        QCOMPARE(m_server->requests.last().path, QStringLiteral("/api/toggle-rotation"));
        QCOMPARE(backend.rotationMode(), QStringLiteral("round_robin"));
    }

    // 3. refreshQuota -> POST /api/refresh
    {
        QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
        backend.refreshQuota(true);
        QVERIFY(spyOp.wait(3000));
        QCOMPARE(m_server->requests.last().path, QStringLiteral("/api/refresh"));
    }

    // 4. unlockManualOverride -> POST /api/unlock
    {
        QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
        backend.unlockManualOverride();
        QVERIFY(spyOp.wait(3000));
        QCOMPARE(m_server->requests.last().path, QStringLiteral("/api/unlock"));
    }
}

// -----------------------------------------------------------------------------
// Challenge 2: Network Failure & Timeout Handling
// -----------------------------------------------------------------------------

void StressM2BackendTests::stressConnectionRefusedHandling() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    // Point to an unused closed port
    qputenv("ANTIGRAVITY_HUB_BASE_URL", "http://127.0.0.1:29876");

    BackendController backend;
    QCOMPARE(backend.isBusy(), false);

    QSignalSpy spyDaemon(&backend, &BackendController::daemonActiveChanged);
    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    QSignalSpy spyNotify(&backend, &BackendController::notificationRequested);

    backend.switchAccount("anyone@gmail.com");

    // Wait for connection refused to complete
    QVERIFY2(spyOp.wait(3000), "Timed out waiting for connection refused completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), false); // success == false

    // Daemon active must transition to false
    QCOMPARE(backend.isDaemonActive(), false);
    QVERIFY(spyDaemon.count() >= 1);

    // Notification must report error
    QCOMPARE(spyNotify.count(), 1);
    QCOMPARE(spyNotify.first().at(2).toBool(), true); // isError == true

    // Busy flag must return to false without leaking
    QCOMPARE(backend.isBusy(), false);
}

void StressM2BackendTests::stressHttp500FailureHandling() {
    m_server->reset();

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    // Set 500 status after constructor init completes
    m_server->customResponseStatus = 500;
    m_server->customResponseBody = QByteArray("{\"error\":\"Internal Server Crash\"}");

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    QSignalSpy spyNotify(&backend, &BackendController::notificationRequested);

    backend.switchAccount("crash@test.com");

    QVERIFY2(spyOp.wait(3000), "Timed out waiting for 500 response completion");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), false); // success == false

    QCOMPARE(spyNotify.count(), 1);
    QCOMPARE(spyNotify.first().at(2).toBool(), true); // isError == true
    QCOMPARE(backend.isBusy(), false);
}

void StressM2BackendTests::stressTimeoutEnforcement() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend);

    // 1. Verify transferTimeout attribute is strictly 10,000 ms
    QNetworkRequest req = backend.createRequest(QStringLiteral("/api/test"));
    QCOMPARE(req.transferTimeout(), 10000);

    // 2. Empirical live timeout test: mock server hangs without sending any bytes
    m_server->reset();
    m_server->hang = true;

    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    QSignalSpy spyNotify(&backend, &BackendController::notificationRequested);

    QElapsedTimer timer;
    timer.start();

    backend.switchAccount("timeout@test.com");
    QCOMPARE(backend.isBusy(), true);

    // Wait up to 12.0 seconds for Qt's 10-second transferTimeout to fire
    qDebug() << "Waiting for 10-second transferTimeout enforcement...";
    QVERIFY2(spyOp.wait(12000), "Timeout enforcement failed to trigger within 12 seconds");

    qint64 elapsed = timer.elapsed();
    qDebug() << "TransferTimeout triggered in" << elapsed << "ms";

    // Elapsed should be at least 9500ms (accounting for clock jitter)
    QVERIFY2(elapsed >= 9500, "Timeout fired too early (less than 9.5s)");
    QCOMPARE(spyOp.count(), 1);
    QCOMPARE(spyOp.first().at(1).toBool(), false); // success == false

    // Verify busy state is cleanly released
    QCOMPARE(backend.isBusy(), false);

    // Verify notification requested with error
    QCOMPARE(spyNotify.count(), 1);
    QCOMPARE(spyNotify.first().at(2).toBool(), true);
}

// -----------------------------------------------------------------------------
// Challenge 3: manual_override_lock.json Dynamic Lifecycle
// -----------------------------------------------------------------------------

void StressM2BackendTests::stressLockLifecycleCreationAndUpdate() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    const QString lockFile = tempDir.filePath("manual_override_lock.json");

    BackendController backend;
    QCOMPARE(backend.isManualLocked(), false);
    QCOMPARE(backend.manualLockRemaining(), 0);

    QSignalSpy spyLock(&backend, &BackendController::manualLockedChanged);

    // 1. Creation: lock for 120 seconds into future
    qint64 now = QDateTime::currentSecsSinceEpoch();
    qint64 lockUntil = now + 120;
    QJsonObject lockObj;
    lockObj["locked_until"] = lockUntil;
    lockObj["reason"] = "Manual test lock";

    QFile file(lockFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    // Allow inotify event to propagate
    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), true, 2000);
    QVERIFY(backend.manualLockRemaining() > 100 && backend.manualLockRemaining() <= 120);
    QVERIFY(spyLock.count() >= 1);

    // 2. Update: extend lock to 300 seconds
    lockUntil = now + 300;
    lockObj["locked_until"] = lockUntil;
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    QTRY_VERIFY_WITH_TIMEOUT(backend.manualLockRemaining() > 250, 2000);
    QCOMPARE(backend.isManualLocked(), true);
}

void StressM2BackendTests::stressLockLifecycleDeletionAndInotifyRearm() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    const QString lockFile = tempDir.filePath("manual_override_lock.json");

    // Write initial lock
    qint64 now = QDateTime::currentSecsSinceEpoch();
    QJsonObject lockObj;
    lockObj["locked_until"] = now + 100;
    QFile file(lockFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    BackendController backend;
    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), true, 2000);

    // 1. Deletion: simulate atomic unlink / deletion
    QVERIFY(QFile::remove(lockFile));

    // Watcher must detect file removal via directory changed and reset state
    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), false, 2000);
    QCOMPARE(backend.manualLockRemaining(), 0);

    // 2. Inotify Re-arm: recreate lock file after deletion
    // If the watcher failed to re-arm on directory event, this recreation would be missed!
    lockObj["locked_until"] = QDateTime::currentSecsSinceEpoch() + 80;
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), true, 2000);
    QVERIFY(backend.manualLockRemaining() > 60);

    // 3. Expiration: write an expired timestamp
    lockObj["locked_until"] = QDateTime::currentSecsSinceEpoch() - 10;
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), false, 2000);
    QCOMPARE(backend.manualLockRemaining(), 0);
}

void StressM2BackendTests::stressLockLifecycleUnlockApiAction() {
    m_server->reset();
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    const QString lockFile = tempDir.filePath("manual_override_lock.json");
    qint64 now = QDateTime::currentSecsSinceEpoch();
    QJsonObject lockObj;
    lockObj["locked_until"] = now + 200;
    QFile file(lockFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(lockObj).toJson());
    file.close();

    BackendController backend;
    waitForInit(backend);
    QTRY_COMPARE_WITH_TIMEOUT(backend.isManualLocked(), true, 2000);

    // Invoke unlockManualOverride
    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);
    backend.unlockManualOverride();

    QVERIFY(spyOp.wait(3000));
    QCOMPARE(m_server->requests.last().path, QStringLiteral("/api/unlock"));
    QCOMPARE(backend.isManualLocked(), false);
    QCOMPARE(backend.manualLockRemaining(), 0);
}

// -----------------------------------------------------------------------------
// Challenge 4: Concurrent Requests & Busy Counter Reentrancy
// -----------------------------------------------------------------------------

void StressM2BackendTests::stressConcurrentRequestsAndBusyReentrancy() {
    m_server->reset();

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    qputenv("ANTIGRAVITY_HUB_BASE_URL", m_serverBaseUrl.toLocal8Bit());

    BackendController backend;
    waitForInit(backend); // Let constructor requests finish first
    QCOMPARE(backend.isBusy(), false);

    m_server->holdConnections = true; // Now enable connection holding for concurrent test

    QSignalSpy spyBusy(&backend, &BackendController::busyChanged);
    QSignalSpy spyOp(&backend, &BackendController::operationCompleted);

    // Launch 5 concurrent asynchronous requests simultaneously
    backend.switchAccount("acc1@gmail.com");
    backend.switchTopGemini();
    backend.toggleRotation();
    backend.refreshQuota();
    backend.triggerPrewarm();

    // Verify all 5 requests received by mock server
    QTRY_COMPARE_WITH_TIMEOUT(m_server->heldSockets.size(), 5, 3000);

    // Busy must be true, and busyChanged emitted EXACTLY ONCE
    QCOMPARE(backend.isBusy(), true);
    QCOMPARE(spyBusy.count(), 1);

    // Release held connections one by one
    // Releasing 1st: 4 remaining
    m_server->releaseOneSocket();
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 1, 2000);
    QCOMPARE(backend.isBusy(), true);
    QCOMPARE(spyBusy.count(), 1); // No duplicate emission

    // Releasing 2nd: 3 remaining
    m_server->releaseOneSocket();
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 2, 2000);
    QCOMPARE(backend.isBusy(), true);
    QCOMPARE(spyBusy.count(), 1);

    // Releasing 3rd: 2 remaining
    m_server->releaseOneSocket();
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 3, 2000);
    QCOMPARE(backend.isBusy(), true);
    QCOMPARE(spyBusy.count(), 1);

    // Releasing 4th: 1 remaining
    m_server->releaseOneSocket();
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 4, 2000);
    QCOMPARE(backend.isBusy(), true);
    QCOMPARE(spyBusy.count(), 1);

    // Releasing 5th: 0 remaining -> busy must transition to false!
    m_server->releaseOneSocket();
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 5, 2000);
    QCOMPARE(backend.isBusy(), false);
    QCOMPARE(spyBusy.count(), 2); // Exactly 2 emissions: false->true, then true->false!

    // Test underflow resistance: invoke setBusy directly via failed operation
    m_server->holdConnections = false;
    m_server->customResponseStatus = 500;
    backend.switchAccount("underflow@test.com");
    QTRY_COMPARE_WITH_TIMEOUT(spyOp.count(), 6, 2000);
    QCOMPARE(backend.isBusy(), false);
}

QTEST_MAIN(StressM2BackendTests)
#include "stress_m2.moc"
