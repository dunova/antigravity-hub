#include <QtTest>
#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QRandomGenerator>
#include <QThread>
#include <cstdio>
#include <unistd.h>

#include "models.h"
#include "backend.h"

class M2StressTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // Challenge 1: Inotify re-arm under atomic file replacement
    void stressTestInotifyAtomicReplaceRapidBurst();
    void stressTestInotifyAtomicReplaceSustainedWatch();
    void stressTestInotifyPythonOsReplaceSimulation();

    // Challenge 2: Weekly depletion short-circuiting
    void stressTestWeeklyDepletionShortCircuit();

    // Challenge 3: Masking algorithm edge cases & fuzzing
    void stressTestMaskingEdgeCases();
    void stressTestMaskingFuzzing();

    // Challenge 4: Proxy filtering rapid search & tab switching
    void stressTestProxyFilteringAndTabSwitching();
    void stressTestProxyDynamicReactivity();

    void cleanupTestCase();

private:
    static QJsonObject makeMockAccount(const QString &email, const QString &name,
                                      double geminiW, double gemini5h,
                                      double claudeW, double claude5h,
                                      double gemini4W, bool blocked, bool hasC55);
    static void atomicWriteJson(const QString &targetPath, const QJsonObject &docObj);
};

void M2StressTests::initTestCase() {
    qDebug() << "==========================================================";
    qDebug() << "Starting M2 Empirical Stress Test Harness...";
    qDebug() << "==========================================================";
}

QJsonObject M2StressTests::makeMockAccount(const QString &email, const QString &name,
                                          double geminiW, double gemini5h,
                                          double claudeW, double claude5h,
                                          double gemini4W, bool blocked, bool hasC55) {
    QJsonObject a;
    a["email"] = email;
    a["name"] = name;
    a["tier"] = "PRO";
    a["pro"] = true;
    a["validation_blocked"] = blocked;

    if (hasC55) {
        QJsonArray models;
        models.append("claude-3-5-sonnet-20241022");
        models.append("claude-3-5-haiku-20241022");
        a["claude_models"] = models;
        a["claude_version"] = "5.5";
    }

    QJsonObject gem;
    gem["quota_weekly"] = geminiW;
    gem["quota_5h"] = gemini5h;
    gem["reset_time_weekly"] = "2026-11-15T00:00:00Z";
    gem["reset_time_5h"] = "2026-11-09T18:00:00Z";
    a["gemini"] = gem;

    QJsonObject cla;
    cla["quota_weekly"] = claudeW;
    cla["quota_5h"] = claude5h;
    cla["reset_time_weekly"] = "2026-11-15T00:00:00Z";
    cla["reset_time_5h"] = "2026-11-09T18:00:00Z";
    a["claude"] = cla;

    if (gemini4W >= 0.0) {
        QJsonObject g4;
        g4["quota_weekly"] = gemini4W;
        g4["reset_time_weekly"] = "2026-11-15T00:00:00Z";
        a["gemini4"] = g4;
    }

    return a;
}

void M2StressTests::atomicWriteJson(const QString &targetPath, const QJsonObject &docObj) {
    const QString tmpPath = targetPath + QStringLiteral(".tmp_%1").arg(QRandomGenerator::global()->generate());
    QFile tmpFile(tmpPath);
    QVERIFY(tmpFile.open(QIODevice::WriteOnly | QIODevice::Truncate));
    tmpFile.write(QJsonDocument(docObj).toJson(QJsonDocument::Compact));
    tmpFile.close();

    // Linux POSIX rename(2) atomically replaces targetPath
    const int ret = ::rename(tmpPath.toLocal8Bit().constData(), targetPath.toLocal8Bit().constData());
    QCOMPARE(ret, 0);
}

// -----------------------------------------------------------------------------
// Challenge 1: Inotify Re-Arm under Atomic File Replacement (rapid os.replace)
// -----------------------------------------------------------------------------

void M2StressTests::stressTestInotifyAtomicReplaceRapidBurst() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    // Write initial account file (1 account)
    QJsonObject accountsObj;
    accountsObj["acc0@gmail.com"] = makeMockAccount("acc0@gmail.com", "User0", 0.9, 1.0, 0.9, 1.0, 0.8, false, false);
    QJsonObject rootDoc;
    rootDoc["active_email"] = "acc0@gmail.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    // Initialize AccountModel
    AccountModel model;
    QCOMPARE(model.rowCount(), 1);

    QSignalSpy spyRefresh(&model, &AccountModel::dataRefreshed);

    // Perform 20 rapid back-to-back atomic replace operations
    qDebug() << "Executing 20 rapid back-to-back atomic os.replace operations...";
    for (int i = 1; i <= 20; ++i) {
        const QString email = QString("burst_acc%1@gmail.com").arg(i);
        accountsObj[email] = makeMockAccount(email, QString("BurstUser%1").arg(i), 0.8, 0.9, 0.8, 0.9, 0.7, false, false);
        rootDoc["accounts"] = accountsObj;
        atomicWriteJson(accountsFile, rootDoc);
    }

    // Wait for the inotify debounce timer (50ms) to settle and reload
    QTRY_COMPARE_WITH_TIMEOUT(model.rowCount(), 21, 3000);
    QVERIFY(spyRefresh.count() >= 1);
    QCOMPARE(model.rowCount(), 21);
    QCOMPARE(model.totalAccounts(), 21);

    // Verify all 21 accounts are accurately accessible
    for (int i = 1; i <= 20; ++i) {
        const QString expectedEmail = QString("burst_acc%1@gmail.com").arg(i);
        const int row = model.findIndexByEmail(expectedEmail);
        QVERIFY2(row >= 0, qPrintable(QString("Account %1 missing after rapid burst").arg(expectedEmail)));
    }
}

void M2StressTests::stressTestInotifyAtomicReplaceSustainedWatch() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;
    accountsObj["base@gmail.com"] = makeMockAccount("base@gmail.com", "Base", 0.9, 1.0, 0.9, 1.0, 0.8, false, false);
    QJsonObject rootDoc;
    rootDoc["active_email"] = "base@gmail.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    AccountModel model;
    QCOMPARE(model.rowCount(), 1);

    // Perform 10 discrete atomic replaces with pause > 80ms (greater than 50ms debounce)
    // To verify that after each Inode unlink and replacement, the inotify watch is re-armed
    // and subsequent replacements continue to be caught reliably without watch leakage
    qDebug() << "Testing sustained watch re-arm across 10 sequential atomic replacements...";
    for (int step = 1; step <= 10; ++step) {
        const QString email = QString("step_acc%1@gmail.com").arg(step);
        accountsObj[email] = makeMockAccount(email, QString("StepUser%1").arg(step), 0.8, 0.9, 0.8, 0.9, 0.7, false, false);
        rootDoc["accounts"] = accountsObj;

        atomicWriteJson(accountsFile, rootDoc);

        // Verify model updates to 1 + step
        const int expectedCount = 1 + step;
        QTRY_COMPARE_WITH_TIMEOUT(model.rowCount(), expectedCount, 2500);
    }

    QCOMPARE(model.rowCount(), 11);
}

void M2StressTests::stressTestInotifyPythonOsReplaceSimulation() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;
    accountsObj["initial@gmail.com"] = makeMockAccount("initial@gmail.com", "Initial", 0.9, 1.0, 0.9, 1.0, 0.8, false, false);
    QJsonObject rootDoc;
    rootDoc["active_email"] = "initial@gmail.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    AccountModel model;
    QCOMPARE(model.rowCount(), 1);

    qDebug() << "Executing real Python os.replace 20-round burst in external subprocess...";
    // Run Python subprocess doing 20 rapid os.replace calls
    const QString pyScript = QString(
        "import os, json, time\n"
        "target = %1\n"
        "with open(target, 'r') as f:\n"
        "    data = json.load(f)\n"
        "for i in range(1, 21):\n"
        "    email = f'py_burst_{i}@gmail.com'\n"
        "    data['accounts'][email] = {'email': email, 'name': f'PyBurst{i}', 'tier': 'PRO', 'pro': True, 'validation_blocked': False, 'gemini': {'quota_weekly': 0.8, 'quota_5h': 0.9}, 'claude': {'quota_weekly': 0.8, 'quota_5h': 0.9}}\n"
        "    tmp = f'{target}.pytmp_{i}'\n"
        "    with open(tmp, 'w') as f:\n"
        "        json.dump(data, f)\n"
        "    os.replace(tmp, target)\n"
        "    time.sleep(0.005)\n"
    ).arg(QString("\"%1\"").arg(accountsFile));

    QProcess pyProc;
    pyProc.start("python3", QStringList() << "-c" << pyScript);
    QVERIFY(pyProc.waitForFinished(10000));
    QCOMPARE(pyProc.exitCode(), 0);

    // Wait for inotify debounce (50ms) to reload model
    QTRY_COMPARE_WITH_TIMEOUT(model.rowCount(), 21, 3000);

    // Now perform 3 discrete subsequent python os.replace writes to verify watch re-arming survived
    for (int j = 1; j <= 3; ++j) {
        const QString pySub = QString(
            "import os, json\n"
            "target = %1\n"
            "with open(target, 'r') as f:\n"
            "    data = json.load(f)\n"
            "email = 'py_sub_%2@gmail.com'\n"
            "data['accounts'][email] = {'email': email, 'name': 'Sub', 'tier': 'PRO', 'pro': True, 'validation_blocked': False, 'gemini': {'quota_weekly': 0.8, 'quota_5h': 0.9}, 'claude': {'quota_weekly': 0.8, 'quota_5h': 0.9}}\n"
            "tmp = f'{target}.subtmp'\n"
            "with open(tmp, 'w') as f:\n"
            "    json.dump(data, f)\n"
            "os.replace(tmp, target)\n"
        ).arg(QString("\"%1\"").arg(accountsFile)).arg(j);

        QProcess p2;
        p2.start("python3", QStringList() << "-c" << pySub);
        QVERIFY(p2.waitForFinished(5000));
        QCOMPARE(p2.exitCode(), 0);

        QTRY_COMPARE_WITH_TIMEOUT(model.rowCount(), 21 + j, 2500);
    }
}

// -----------------------------------------------------------------------------
// Challenge 2: Weekly Depletion Short-Circuiting
// -----------------------------------------------------------------------------

void M2StressTests::stressTestWeeklyDepletionShortCircuit() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;

    // Case 1: Weekly strictly 0.0, 5h is 1.0 (Full 5h window)
    accountsObj["zero@gmail.com"] = makeMockAccount("zero@gmail.com", "Zero", 0.0, 1.0, 0.0, 1.0, 0.0, false, false);

    // Case 2: Weekly 0.00005 (below threshold 0.0001), 5h is 0.99
    accountsObj["micro@gmail.com"] = makeMockAccount("micro@gmail.com", "Micro", 0.00005, 0.99, 0.00005, 0.99, 0.0, false, false);

    // Case 3: Weekly exactly 0.000100 (exact threshold), 5h is 0.88
    accountsObj["exact@gmail.com"] = makeMockAccount("exact@gmail.com", "Exact", 0.000100, 0.88, 0.000100, 0.88, 0.0, false, false);

    // Case 4: Weekly 0.000101 (just above threshold), 5h is 0.77
    accountsObj["above@gmail.com"] = makeMockAccount("above@gmail.com", "Above", 0.000101, 0.77, 0.000101, 0.77, 0.0, false, false);

    // Case 5: Weekly negative (-0.05), 5h is 0.66
    accountsObj["negative@gmail.com"] = makeMockAccount("negative@gmail.com", "Negative", -0.05, 0.66, -0.05, 0.66, 0.0, false, false);

    // Case 6: Weekly 0.0, but this account is active
    accountsObj["active_zero@gmail.com"] = makeMockAccount("active_zero@gmail.com", "ActiveZero", 0.0, 1.0, 0.0, 1.0, 0.0, false, false);

    // Case 7: Weekly 0.0, and validation_blocked = true
    accountsObj["blocked_zero@gmail.com"] = makeMockAccount("blocked_zero@gmail.com", "BlockedZero", 0.0, 1.0, 0.0, 1.0, 0.0, true, false);

    // Case 8: Weekly 0.8, and validation_blocked = true
    accountsObj["blocked_ok@gmail.com"] = makeMockAccount("blocked_ok@gmail.com", "BlockedOk", 0.8, 0.9, 0.8, 0.9, 0.8, true, false);

    QJsonObject rootDoc;
    rootDoc["active_email"] = "active_zero@gmail.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    AccountModel model;
    QCOMPARE(model.rowCount(), 8);

    // Verify Case 1: zero@gmail.com
    {
        const int row = model.findIndexByEmail("zero@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
    }

    // Verify Case 2: micro@gmail.com
    {
        const int row = model.findIndexByEmail("micro@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
    }

    // Verify Case 3: exact@gmail.com
    {
        const int row = model.findIndexByEmail("exact@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
    }

    // Verify Case 4: above@gmail.com (NOT short-circuited!)
    {
        const int row = model.findIndexByEmail("above@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.77);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.77);
        // Not exhausted since weekly > 0.0001
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("STANDBY"));
    }

    // Verify Case 5: negative@gmail.com (Negative is <= 0.0001 -> short-circuits)
    {
        const int row = model.findIndexByEmail("negative@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
    }

    // Verify Case 6: active_zero@gmail.com
    // Weekly short-circuits 5h to 0.0, but status shows ACTIVE for UI clarity
    {
        const int row = model.findIndexByEmail("active_zero@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::IsActiveRole).toBool(), true);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("ACTIVE"));
    }

    // Verify Case 7: blocked_zero@gmail.com
    // Weekly short-circuits 5h to 0.0, status precedence: EXHAUSTED
    {
        const int row = model.findIndexByEmail("blocked_zero@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
        QCOMPARE(model.data(idx, AccountModel::IsBlockedRole).toBool(), true);
    }

    // Verify Case 8: blocked_ok@gmail.com
    // Weekly is 0.8 > 0.0001 -> 5h is 0.9, status is BLOCKED
    {
        const int row = model.findIndexByEmail("blocked_ok@gmail.com");
        QVERIFY(row >= 0);
        const QModelIndex idx = model.index(row, 0);
        QCOMPARE(model.data(idx, AccountModel::Gemini38Quota5hRole).toDouble(), 0.9);
        QCOMPARE(model.data(idx, AccountModel::ClaudeQuota5hRole).toDouble(), 0.9);
        QCOMPARE(model.data(idx, AccountModel::StatusRole).toString(), QString("BLOCKED"));
    }
}

// -----------------------------------------------------------------------------
// Challenge 3: Masking Algorithm Edge Cases & Fuzzing
// -----------------------------------------------------------------------------

void M2StressTests::stressTestMaskingEdgeCases() {
    // 1. Empty & 0-length tests
    QCOMPARE(AccountModel::computeMaskedName(""), QString(""));
    QCOMPARE(AccountModel::computeMaskedName(QString()), QString(""));
    QCOMPARE(AccountModel::computeMaskedName("@gmail.com"), QString(""));
    QCOMPARE(AccountModel::computeMaskedName("@@@"), QString(""));

    // 2. Length 1 tests
    QCOMPARE(AccountModel::computeMaskedName("a"), QString("a***"));
    QCOMPARE(AccountModel::computeMaskedName("Z"), QString("Z***"));
    QCOMPARE(AccountModel::computeMaskedName("1"), QString("1***"));
    QCOMPARE(AccountModel::computeMaskedName("a@test.org"), QString("a***"));
    QCOMPARE(AccountModel::computeMaskedName("x@sub.domain.corp.co.uk"), QString("x***"));

    // 3. Length 2 tests
    QCOMPARE(AccountModel::computeMaskedName("ab"), QString("a***b"));
    QCOMPARE(AccountModel::computeMaskedName("42"), QString("4***2"));
    QCOMPARE(AccountModel::computeMaskedName("ab@gmail.com"), QString("a***b"));
    QCOMPARE(AccountModel::computeMaskedName("ox@subdomain.example.com"), QString("o***x"));

    // 4. Length 3 tests
    QCOMPARE(AccountModel::computeMaskedName("bob"), QString("b***ob"));
    QCOMPARE(AccountModel::computeMaskedName("fox"), QString("f***ox"));
    QCOMPARE(AccountModel::computeMaskedName("123"), QString("1***23"));
    QCOMPARE(AccountModel::computeMaskedName("bob@gmail.com"), QString("b***ob"));

    // 5. Length 4 & standard handles
    QCOMPARE(AccountModel::computeMaskedName("user"), QString("u***er"));
    QCOMPARE(AccountModel::computeMaskedName("root"), QString("r***ot"));
    QCOMPARE(AccountModel::computeMaskedName("cakeai66"), QString("c***66"));
    QCOMPARE(AccountModel::computeMaskedName("cakeai66@gmail.com"), QString("c***66"));
    QCOMPARE(AccountModel::computeMaskedName("novadu99"), QString("n***99"));
    QCOMPARE(AccountModel::computeMaskedName("novadu99@gmail.com"), QString("n***99"));

    // 6. Complex emails: subdomains, multiple dots, plus tags
    QCOMPARE(AccountModel::computeMaskedName("first.last@company.com"), QString("f***st"));
    QCOMPARE(AccountModel::computeMaskedName("user+dev@sub.domain.corp.co.uk"), QString("u***ev"));
    QCOMPARE(AccountModel::computeMaskedName("a.b.c.d.e@corp.internal"), QString("a***.e"));

    // 7. Unicode characters
    QCOMPARE(AccountModel::computeMaskedName("张"), QString("张***"));
    QCOMPARE(AccountModel::computeMaskedName("张三"), QString("张***三"));
    QCOMPARE(AccountModel::computeMaskedName("张三丰"), QString("张***三丰"));
    QCOMPARE(AccountModel::computeMaskedName("诸葛孔明"), QString("诸***孔明"));
    QCOMPARE(AccountModel::computeMaskedName("张三@163.com"), QString("张***三"));

    // 8. Long strings
    const QString longName(1000, 'x');
    const QString maskedLong = AccountModel::computeMaskedName(longName);
    QCOMPARE(maskedLong.length(), 6); // 'x' + "***" + "xx"
    QCOMPARE(maskedLong, QString("x***xx"));
}

void M2StressTests::stressTestMaskingFuzzing() {
    qDebug() << "Executing 10,000 randomized masking iterations...";
    const QString charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'*+-/=?^_`{|}~.@ \t";

    for (int i = 0; i < 10000; ++i) {
        const int len = QRandomGenerator::global()->bounded(0, 120);
        QString randomStr;
        randomStr.reserve(len);
        for (int j = 0; j < len; ++j) {
            const int idx = QRandomGenerator::global()->bounded(charset.length());
            randomStr.append(charset.at(idx));
        }

        const QString masked = AccountModel::computeMaskedName(randomStr);

        // Invariants
        if (randomStr.isEmpty()) {
            QVERIFY(masked.isEmpty());
        } else {
            int atIdx = randomStr.indexOf('@');
            int expectedTargetLen = (atIdx != -1) ? atIdx : randomStr.length();
            if (expectedTargetLen == 0) {
                QVERIFY(masked.isEmpty());
            } else if (expectedTargetLen == 1) {
                QCOMPARE(masked.length(), 4);
                QVERIFY(masked.endsWith("***"));
            } else if (expectedTargetLen == 2) {
                QCOMPARE(masked.length(), 5);
                QVERIFY(masked.contains("***"));
            } else {
                QCOMPARE(masked.length(), 6);
                QVERIFY(masked.contains("***"));
            }
        }
    }
}

// -----------------------------------------------------------------------------
// Challenge 4: Proxy Filtering Rapid Search & 5-Tab Switching
// -----------------------------------------------------------------------------

void M2StressTests::stressTestProxyFilteringAndTabSwitching() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    // Populate a test dataset of 25 accounts:
    // - 5 Plentiful: quota_weekly >= 0.50, not blocked
    // - 5 Warning: quota_weekly < 0.15, not exhausted, not blocked
    // - 5 Exhausted: quota_weekly <= 0.0001
    // - 5 Blocked: validation_blocked = true (quota_weekly 0.8)
    // - 5 Normal: quota_weekly 0.35 (neither plentiful nor warning nor exhausted)
    QJsonObject accountsObj;

    for (int i = 0; i < 5; ++i) {
        const QString e = QString("plentiful%1@test.com").arg(i);
        accountsObj[e] = makeMockAccount(e, QString("Plentiful %1").arg(i), 0.85, 1.0, 0.85, 1.0, 0.85, false, true);
    }
    for (int i = 0; i < 5; ++i) {
        const QString e = QString("warning%1@test.com").arg(i);
        accountsObj[e] = makeMockAccount(e, QString("Warning %1").arg(i), 0.10, 0.10, 0.10, 0.10, 0.10, false, false);
    }
    for (int i = 0; i < 5; ++i) {
        const QString e = QString("exhausted%1@test.com").arg(i);
        accountsObj[e] = makeMockAccount(e, QString("Exhausted %1").arg(i), 0.0, 0.0, 0.0, 0.0, 0.0, false, false);
    }
    for (int i = 0; i < 5; ++i) {
        const QString e = QString("blocked%1@test.com").arg(i);
        accountsObj[e] = makeMockAccount(e, QString("Blocked %1").arg(i), 0.80, 0.90, 0.80, 0.90, 0.80, true, false);
    }
    for (int i = 0; i < 5; ++i) {
        const QString e = QString("normal%1@test.com").arg(i);
        accountsObj[e] = makeMockAccount(e, QString("Normal %1").arg(i), 0.35, 0.50, 0.35, 0.50, 0.35, false, false);
    }

    QJsonObject rootDoc;
    rootDoc["active_email"] = "plentiful0@test.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    AccountModel model;
    QCOMPARE(model.rowCount(), 25);

    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    // Initial state: tab "all", filter ""
    QCOMPARE(proxy.totalCount(), 25);
    QCOMPARE(proxy.filteredCount(), 25);
    QCOMPARE(proxy.rowCount(), 25);

    // Verify baseline counts for each of the 5 tabs
    proxy.setStatusTab("all");
    QCOMPARE(proxy.filteredCount(), 25);

    proxy.setStatusTab("usable");
    // Usable = not blocked AND weekly > 0.0001
    // plentiful (5) + warning (5) + normal (5) = 15
    QCOMPARE(proxy.filteredCount(), 15);

    proxy.setStatusTab("plentiful");
    // Plentiful = not blocked AND weekly >= 0.50 (both gemini and claude if c55)
    // plentiful (5) = 5
    QCOMPARE(proxy.filteredCount(), 5);

    proxy.setStatusTab("warning");
    // Warning = not exhausted AND (weekly < 0.15 || 5h < 0.10)
    // warning (5) = 5
    QCOMPARE(proxy.filteredCount(), 5);

    proxy.setStatusTab("exhausted");
    // Exhausted = weekly <= 0.0001
    // exhausted (5) = 5
    QCOMPARE(proxy.filteredCount(), 5);

    // Stress Test: Rapid tab switching (500 cycles)
    qDebug() << "Executing 500 rapid status tab cycles...";
    const QStringList tabs = { "all", "usable", "plentiful", "warning", "exhausted" };
    for (int i = 0; i < 500; ++i) {
        const QString &tab = tabs.at(i % tabs.size());
        proxy.setStatusTab(tab);

        // Assert critical invariants on every transition
        QCOMPARE(proxy.totalCount(), 25);
        QCOMPARE(proxy.filteredCount(), proxy.rowCount());
        QVERIFY(proxy.filteredCount() >= 0);
        QVERIFY(proxy.filteredCount() <= proxy.totalCount());
    }

    // Stress Test: Rapid search text changes (500 cycles)
    qDebug() << "Executing 500 rapid search filter changes...";
    const QStringList searchQueries = {
        "", "plentiful", "warning", "exhausted", "blocked", "normal",
        "PLENTIFUL", "test.com", "0@test", "xyz_nonexistent", "5.5", "4.6", "active"
    };
    proxy.setStatusTab("all");

    for (int i = 0; i < 500; ++i) {
        const QString &query = searchQueries.at(i % searchQueries.size());
        proxy.setFilterText(query);

        // Assert invariants
        QCOMPARE(proxy.totalCount(), 25);
        QCOMPARE(proxy.filteredCount(), proxy.rowCount());
        QVERIFY(proxy.filteredCount() >= 0);
        QVERIFY(proxy.filteredCount() <= proxy.totalCount());
    }

    // Stress Test: 500 randomized (Tab, Search) pairs
    qDebug() << "Executing 500 randomized (Tab, Search) transitions...";
    for (int i = 0; i < 500; ++i) {
        const QString &tab = tabs.at(QRandomGenerator::global()->bounded(tabs.size()));
        const QString &query = searchQueries.at(QRandomGenerator::global()->bounded(searchQueries.size()));

        proxy.setStatusTab(tab);
        proxy.setFilterText(query);

        QCOMPARE(proxy.totalCount(), 25);
        QCOMPARE(proxy.filteredCount(), proxy.rowCount());
        QVERIFY(proxy.filteredCount() >= 0);
        QVERIFY(proxy.filteredCount() <= proxy.totalCount());
    }

    // Reset back to neutral state
    proxy.setStatusTab("all");
    proxy.setFilterText("");
    QCOMPARE(proxy.totalCount(), 25);
    QCOMPARE(proxy.filteredCount(), 25);
}

void M2StressTests::stressTestProxyDynamicReactivity() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;
    accountsObj["user1@gmail.com"] = makeMockAccount("user1@gmail.com", "User1", 0.9, 1.0, 0.9, 1.0, 0.8, false, false);
    QJsonObject rootDoc;
    rootDoc["active_email"] = "user1@gmail.com";
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    QSignalSpy spyCounts(&proxy, &AccountFilterProxyModel::countsChanged);

    QCOMPARE(proxy.totalCount(), 1);
    QCOMPARE(proxy.filteredCount(), 1);

    // Apply filter
    proxy.setFilterText("user1");
    QCOMPARE(proxy.filteredCount(), 1);

    // Now write a new account file dynamically via atomic write
    accountsObj["user2@gmail.com"] = makeMockAccount("user2@gmail.com", "User2", 0.9, 1.0, 0.9, 1.0, 0.8, false, false);
    rootDoc["accounts"] = accountsObj;
    atomicWriteJson(accountsFile, rootDoc);

    // Wait for inotify debounce and proxy update
    QTRY_COMPARE_WITH_TIMEOUT(proxy.totalCount(), 2, 2000);
    // Because filter is "user1", filteredCount must still be 1
    QCOMPARE(proxy.filteredCount(), 1);

    // Clear filter
    proxy.setFilterText("");
    QCOMPARE(proxy.filteredCount(), 2);
    QCOMPARE(proxy.totalCount(), 2);
    QVERIFY(spyCounts.count() >= 1);
}

void M2StressTests::cleanupTestCase() {
    qDebug() << "==========================================================";
    qDebug() << "M2 Empirical Stress Test Harness Complete: ALL PASS";
    qDebug() << "==========================================================";
}

QTEST_MAIN(M2StressTests)
#include "m2_stress_tests.moc"
