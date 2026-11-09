#include <QtTest>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQuickWindow>
#include <QQuickItem>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <functional>

#include "theme.h"
#include "translator.h"
#include "models.h"
#include "backend.h"

// =============================================================================
// Intercepting Message Handler for Zero Warning Audit
// =============================================================================
static QStringList s_logWarnings;
static QStringList s_logBindingLoops;

static void e2eMessageHandler(QtMsgType type, const QMessageLogContext &context, const QString &msg) {
    Q_UNUSED(context);
    if (type == QtWarningMsg || type == QtCriticalMsg || type == QtFatalMsg) {
        s_logWarnings.append(msg);
        if (msg.contains(QStringLiteral("Binding loop"), Qt::CaseInsensitive)) {
            s_logBindingLoops.append(msg);
        }
    }
}

// =============================================================================
// Instrumented Backend Controller to Spy on Invocations
// =============================================================================
class InstrumentedBackend : public BackendController {
    Q_OBJECT

public:
    explicit InstrumentedBackend(QObject *parent = nullptr)
        : BackendController(parent),
          m_switchCount(0),
          m_refreshCount(0),
          m_topGeminiCount(0),
          m_prewarmCount(0) {}

    int m_switchCount;
    QString m_lastSwitchedEmail;
    int m_refreshCount;
    int m_topGeminiCount;
    int m_prewarmCount;

    Q_INVOKABLE void switchAccount(const QString &email) {
        m_switchCount++;
        m_lastSwitchedEmail = email;
        BackendController::switchAccount(email);
    }

    Q_INVOKABLE void refreshQuota(bool force = false) {
        m_refreshCount++;
        BackendController::refreshQuota(force);
    }

    Q_INVOKABLE void switchTopGemini() {
        m_topGeminiCount++;
        BackendController::switchTopGemini();
    }

    Q_INVOKABLE void triggerPrewarm() {
        m_prewarmCount++;
        BackendController::triggerPrewarm();
    }
};

// =============================================================================
// M5 Dual Track E2E Verification & Forensic Challenge
// =============================================================================
class M5ChallengerE2ETests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void cleanupTestCase();
    void init();
    void cleanup();

    // 1. Full Keyboard Navigation Stream
    void testKeyboardNavigationStream();

    // 2. Modal Safety & Keystroke Isolation
    void testModalSafetyAndIsolation();

    // 3. Strict Visual Denoising Invariants
    void testVisualDenoisingInvariants();
};

void M5ChallengerE2ETests::initTestCase() {
    qputenv("QT_QPA_PLATFORM", "offscreen");
    qputenv("QT_FORCE_STDERR_LOGGING", "1");
    qInstallMessageHandler(e2eMessageHandler);

    qmlRegisterType<AccountModel>("AntigravityHub", 1, 0, "AccountModel");
    qmlRegisterType<AccountFilterProxyModel>("AntigravityHub", 1, 0, "AccountFilterProxyModel");
    qmlRegisterType<BackendController>("AntigravityHub", 1, 0, "BackendController");
    qmlRegisterUncreatableType<Theme>("AntigravityHub", 1, 0, "Theme",
        QStringLiteral("Theme context property"));
    qmlRegisterUncreatableType<Translator>("AntigravityHub", 1, 0, "Translator",
        QStringLiteral("Translator context property"));
}

void M5ChallengerE2ETests::cleanupTestCase() {
    qInstallMessageHandler(nullptr);
}

void M5ChallengerE2ETests::init() {
    s_logWarnings.clear();
    s_logBindingLoops.clear();
}

void M5ChallengerE2ETests::cleanup() {
}

// -----------------------------------------------------------------------------
// 1. Full Keyboard Navigation Stream Test
// -----------------------------------------------------------------------------
void M5ChallengerE2ETests::testKeyboardNavigationStream() {
    QQmlEngine engine;
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    // Setup 5 mock accounts (account 1 is active, accounts 2-5 are standby)
    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");
    QJsonObject accountsObj;
    for (int i = 1; i <= 5; ++i) {
        QJsonObject a;
        a["email"] = QString("user%1@example.com").arg(i);
        a["name"] = QString("User %1").arg(i);
        a["validation_blocked"] = false;
        QJsonObject g; g["quota_5h"] = 0.75; g["quota_weekly"] = 0.80; a["gemini"] = g;
        QJsonObject c; c["quota_5h"] = 0.70; c["quota_weekly"] = 0.75; a["claude"] = c;
        accountsObj[QString("user%1@example.com").arg(i)] = a;
    }
    QJsonObject rootDoc;
    rootDoc["active_email"] = "user1@example.com";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    Theme theme(tempDir.path());
    Translator translator(tempDir.filePath("lang"), ":/i18n");
    InstrumentedBackend backend;
    AccountModel accountModel;
    AccountFilterProxyModel proxyModel;
    proxyModel.setSourceModel(&accountModel);

    QQmlContext *ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("theme"), &theme);
    ctx->setContextProperty(QStringLiteral("translator"), &translator);
    ctx->setContextProperty(QStringLiteral("backend"), &backend);
    ctx->setContextProperty(QStringLiteral("backendController"), &backend);
    ctx->setContextProperty(QStringLiteral("accountModel"), &accountModel);
    ctx->setContextProperty(QStringLiteral("proxyModel"), &proxyModel);
    ctx->setContextProperty(QStringLiteral("accountFilterProxyModel"), &proxyModel);

    QQmlComponent mainComp(&engine, QUrl(QStringLiteral("qrc:/Main.qml")));
    QVERIFY2(!mainComp.isError(), qPrintable(mainComp.errorString()));
    QScopedPointer<QObject> mainObj(mainComp.create());
    QVERIFY(mainObj != nullptr);

    QQuickWindow *win = qobject_cast<QQuickWindow*>(mainObj.data());
    QVERIFY(win != nullptr);
    win->show();
    win->requestActivate();
    QCoreApplication::processEvents();

    // Locate child components
    auto findByMethod = [](QObject *parent, const char *methodName, bool isPopup, auto &self) -> QObject* {
        if (!parent) return nullptr;
        if (parent->metaObject()->indexOfMethod(methodName) != -1) {
            if (!isPopup || parent->inherits("QQuickPopup")) return parent;
        }
        for (QObject *child : parent->children()) {
            QObject *res = self(child, methodName, isPopup, self);
            if (res) return res;
        }
        return nullptr;
    };

    QObject *filterBar = findByMethod(mainObj.data(), "focusSearch()", false, findByMethod);
    QVERIFY(filterBar != nullptr);

    QObject *accountListView = findByMethod(mainObj.data(), "selectNext()", false, findByMethod);
    QVERIFY(accountListView != nullptr);

    QObject *settingsDialog = findByMethod(mainObj.data(), "saveAndApply()", true, findByMethod);
    QVERIFY(settingsDialog != nullptr);

    QObject *helpOverlay = findByMethod(mainObj.data(), "toggle()", true, findByMethod);
    QVERIFY(helpOverlay != nullptr);

    // Locate ListView and SearchInput
    auto findChildItem = [](QObject *parent, const char *cls, auto &self) -> QQuickItem* {
        if (!parent) return nullptr;
        if (parent->inherits(cls)) return qobject_cast<QQuickItem*>(parent);
        for (QObject *child : parent->children()) {
            QQuickItem *res = self(child, cls, self);
            if (res) return res;
        }
        return nullptr;
    };

    QQuickItem *listView = findChildItem(accountListView, "QQuickListView", findChildItem);
    QVERIFY(listView != nullptr);

    auto findInput = [](QObject *parent, auto &self) -> QQuickItem* {
        if (!parent) return nullptr;
        if (parent->property("cursorPosition").isValid() && !parent->property("readOnly").toBool()) {
            return qobject_cast<QQuickItem*>(parent);
        }
        for (QObject *child : parent->children()) {
            QQuickItem *res = self(child, self);
            if (res) return res;
        }
        return nullptr;
    };
    QQuickItem *searchInput = findInput(filterBar, findInput);
    QVERIFY(searchInput != nullptr);

    // Initial assertions
    QCOMPARE(mainObj->property("isInputFocused").toBool(), false);
    QCOMPARE(mainObj->property("isModalOpen").toBool(), false);
    QCOMPARE(listView->property("count").toInt(), 5);
    QCOMPARE(listView->property("currentIndex").toInt(), 0);

    // --- 1.A: '/' Focuses Search Bar ---
    QTest::keyClick(win, '/');
    QCoreApplication::processEvents();
    QCOMPARE(win->activeFocusItem(), searchInput);
    QCOMPARE(mainObj->property("isInputFocused").toBool(), true);

    // --- 1.B: 'Esc' Unfocuses Search Bar ---
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QCOMPARE(mainObj->property("isInputFocused").toBool(), false);
    QCOMPARE(searchInput->property("text").toString(), QString());

    // --- 1.C: 'j' and 'k' Seamless Navigation with Clamping ---
    // 'j' moves down: 0 -> 1 -> 2 -> 3 -> 4
    for (int expected = 1; expected <= 4; ++expected) {
        QTest::keyClick(win, 'j');
        QCoreApplication::processEvents();
        QCOMPARE(listView->property("currentIndex").toInt(), expected);
    }
    // 'j' at bottom clamps at 4
    QTest::keyClick(win, 'j');
    QCoreApplication::processEvents();
    QCOMPARE(listView->property("currentIndex").toInt(), 4);

    // 'k' moves up: 4 -> 3 -> 2 -> 1 -> 0
    for (int expected = 3; expected >= 0; --expected) {
        QTest::keyClick(win, 'k');
        QCoreApplication::processEvents();
        QCOMPARE(listView->property("currentIndex").toInt(), expected);
    }
    // 'k' at top clamps at 0
    QTest::keyClick(win, 'k');
    QCoreApplication::processEvents();
    QCOMPARE(listView->property("currentIndex").toInt(), 0);

    // Also verify Down and Up arrow keys navigate identically
    QTest::keyClick(win, Qt::Key_Down);
    QCoreApplication::processEvents();
    QCOMPARE(listView->property("currentIndex").toInt(), 1);

    QTest::keyClick(win, Qt::Key_Up);
    QCoreApplication::processEvents();
    QCOMPARE(listView->property("currentIndex").toInt(), 0);

    // --- 1.D: 'Enter' Triggers Active Account Switching ---
    // Move to index 1 (user2@example.com, which is NOT active)
    QTest::keyClick(win, 'j');
    QCoreApplication::processEvents();
    QCOMPARE(listView->property("currentIndex").toInt(), 1);

    int beforeSwitches = backend.m_switchCount;
    QTest::keyClick(win, Qt::Key_Return);
    QCoreApplication::processEvents();
    QCOMPARE(backend.m_switchCount, beforeSwitches + 1);
    QCOMPARE(backend.m_lastSwitchedEmail, QStringLiteral("user2@example.com"));

    // --- 1.E: 'm' Toggles Data Masking ---
    bool maskedInitial = backend.isMasked();
    QTest::keyClick(win, 'm');
    QCoreApplication::processEvents();
    QCOMPARE(backend.isMasked(), !maskedInitial);

    QTest::keyClick(win, 'm');
    QCoreApplication::processEvents();
    QCOMPARE(backend.isMasked(), maskedInitial);

    // --- 1.F: 'r' Triggers Quota Refresh ---
    int refreshBefore = backend.m_refreshCount;
    QTest::keyClick(win, 'r');
    QCoreApplication::processEvents();
    QCOMPARE(backend.m_refreshCount, refreshBefore + 1);

    // --- 1.G: '?', 'Shift+/', and 'F1' Open HelpOverlay ---
    // Test F1
    QTest::keyClick(win, Qt::Key_F1);
    // Test F1
    QTest::keyClick(win, Qt::Key_F1);
    QCoreApplication::processEvents();
    fprintf(stderr, "helpOverlay visible after F1: %d\n", helpOverlay->property("visible").toBool());
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), true, 500);

    // Esc closes HelpOverlay
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), false, 500);

    // Test 'Shift+/' (standard US keyboard shortcut for ?)
    QTest::keyClick(win, Qt::Key_Slash, Qt::ShiftModifier);
    QCoreApplication::processEvents();
    fprintf(stderr, "helpOverlay visible after Key_Slash+Shift: %d\n", helpOverlay->property("visible").toBool());
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), true, 500);

    // Esc closes HelpOverlay again
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), false, 500);

    // Test '?' direct char click
    QTest::keyClick(win, '?');
    QCoreApplication::processEvents();
    fprintf(stderr, "helpOverlay visible after direct char '?': %d\n", helpOverlay->property("visible").toBool());
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), true, 500);

    // Esc closes HelpOverlay again
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), false, 500);

    // --- 1.H: 's' Opens SettingsDialog and Esc Closes It ---
    QTest::keyClick(win, 's');
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(settingsDialog->property("visible").toBool(), true, 500);

    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(settingsDialog->property("visible").toBool(), false, 500);
}

// -----------------------------------------------------------------------------
// 2. Modal Safety & Keystroke Isolation Test
// -----------------------------------------------------------------------------
void M5ChallengerE2ETests::testModalSafetyAndIsolation() {
    QQmlEngine engine;
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    // Setup 5 mock accounts
    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");
    QJsonObject accountsObj;
    for (int i = 1; i <= 5; ++i) {
        QJsonObject a;
        a["email"] = QString("test%1@hub.local").arg(i);
        a["name"] = QString("Test %1").arg(i);
        a["validation_blocked"] = false;
        QJsonObject g; g["quota_5h"] = 0.5; g["quota_weekly"] = 0.6; a["gemini"] = g;
        QJsonObject c; c["quota_5h"] = 0.5; c["quota_weekly"] = 0.6; a["claude"] = c;
        accountsObj[QString("test%1@hub.local").arg(i)] = a;
    }
    QJsonObject rootDoc;
    rootDoc["active_email"] = "test1@hub.local";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    Theme theme(tempDir.path());
    Translator translator(tempDir.filePath("lang"), ":/i18n");
    InstrumentedBackend backend;
    AccountModel accountModel;
    AccountFilterProxyModel proxyModel;
    proxyModel.setSourceModel(&accountModel);

    QQmlContext *ctx = engine.rootContext();
    ctx->setContextProperty(QStringLiteral("theme"), &theme);
    ctx->setContextProperty(QStringLiteral("translator"), &translator);
    ctx->setContextProperty(QStringLiteral("backend"), &backend);
    ctx->setContextProperty(QStringLiteral("backendController"), &backend);
    ctx->setContextProperty(QStringLiteral("accountModel"), &accountModel);
    ctx->setContextProperty(QStringLiteral("proxyModel"), &proxyModel);
    ctx->setContextProperty(QStringLiteral("accountFilterProxyModel"), &proxyModel);

    QQmlComponent mainComp(&engine, QUrl(QStringLiteral("qrc:/Main.qml")));
    QVERIFY2(!mainComp.isError(), qPrintable(mainComp.errorString()));
    QScopedPointer<QObject> mainObj(mainComp.create());
    QVERIFY(mainObj != nullptr);

    QQuickWindow *win = qobject_cast<QQuickWindow*>(mainObj.data());
    QVERIFY(win != nullptr);
    win->show();
    win->requestActivate();
    QCoreApplication::processEvents();

    auto findByMethod = [](QObject *parent, const char *methodName, bool isPopup, auto &self) -> QObject* {
        if (!parent) return nullptr;
        if (parent->metaObject()->indexOfMethod(methodName) != -1) {
            if (!isPopup || parent->inherits("QQuickPopup")) return parent;
        }
        for (QObject *child : parent->children()) {
            QObject *res = self(child, methodName, isPopup, self);
            if (res) return res;
        }
        return nullptr;
    };

    QObject *filterBar = findByMethod(mainObj.data(), "focusSearch()", false, findByMethod);
    QVERIFY(filterBar != nullptr);

    QObject *accountListView = findByMethod(mainObj.data(), "selectNext()", false, findByMethod);
    QVERIFY(accountListView != nullptr);

    QObject *settingsDialog = findByMethod(mainObj.data(), "saveAndApply()", true, findByMethod);
    QVERIFY(settingsDialog != nullptr);

    QObject *helpOverlay = findByMethod(mainObj.data(), "toggle()", true, findByMethod);
    QVERIFY(helpOverlay != nullptr);

    auto findChildItem = [](QObject *parent, const char *cls, auto &self) -> QQuickItem* {
        if (!parent) return nullptr;
        if (parent->inherits(cls)) return qobject_cast<QQuickItem*>(parent);
        for (QObject *child : parent->children()) {
            QQuickItem *res = self(child, cls, self);
            if (res) return res;
        }
        return nullptr;
    };
    QQuickItem *listView = findChildItem(accountListView, "QQuickListView", findChildItem);
    QVERIFY(listView != nullptr);

    auto findInput = [](QObject *parent, auto &self) -> QQuickItem* {
        if (!parent) return nullptr;
        if (parent->property("cursorPosition").isValid() && !parent->property("readOnly").toBool()) {
            return qobject_cast<QQuickItem*>(parent);
        }
        for (QObject *child : parent->children()) {
            QQuickItem *res = self(child, self);
            if (res) return res;
        }
        return nullptr;
    };
    QQuickItem *searchInput = findInput(filterBar, findInput);
    QVERIFY(searchInput != nullptr);

    // -------------------------------------------------------------------------
    // PART A: When search input is focused (isInputFocused == true)
    // -------------------------------------------------------------------------
    QMetaObject::invokeMethod(filterBar, "focusSearch");
    QCoreApplication::processEvents();
    QCOMPARE(mainObj->property("isInputFocused").toBool(), true);

    const int initialIdx = listView->property("currentIndex").toInt();
    const bool initialMasked = backend.isMasked();
    const int initialSwitches = backend.m_switchCount;
    const int initialRefreshes = backend.m_refreshCount;
    const int initialTopG = backend.m_topGeminiCount;
    const int initialPrewarm = backend.m_prewarmCount;

    // Keys typed into search input must NOT trigger global shortcuts!
    QTest::keyClick(win, 'j');
    QTest::keyClick(win, 'k');
    QTest::keyClick(win, 'm');
    QTest::keyClick(win, 'r');
    QTest::keyClick(win, 's');
    QTest::keyClick(win, 'g');
    QTest::keyClick(win, 'w');
    QTest::keyClick(win, Qt::Key_F1);
    QCoreApplication::processEvents();

    QCOMPARE(listView->property("currentIndex").toInt(), initialIdx);
    QCOMPARE(backend.isMasked(), initialMasked);
    QCOMPARE(backend.m_switchCount, initialSwitches);
    QCOMPARE(backend.m_refreshCount, initialRefreshes);
    QCOMPARE(backend.m_topGeminiCount, initialTopG);
    QCOMPARE(backend.m_prewarmCount, initialPrewarm);
    QCOMPARE(settingsDialog->property("visible").toBool(), false);
    QCOMPARE(helpOverlay->property("visible").toBool(), false);

    // Characters were entered into search input
    QVERIFY(searchInput->property("text").toString().contains("jkmrsgw"));

    // Clear and unfocus search
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QCOMPARE(mainObj->property("isInputFocused").toBool(), false);

    // -------------------------------------------------------------------------
    // PART B: When SettingsDialog is open (isModalOpen == true)
    // -------------------------------------------------------------------------
    QTest::keyClick(win, 's');
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(settingsDialog->property("visible").toBool(), true, 500);
    QCOMPARE(mainObj->property("isModalOpen").toBool(), true);

    const int curIdxBeforeModal = listView->property("currentIndex").toInt();
    const bool maskBeforeModal = backend.isMasked();
    const int refreshBeforeModal = backend.m_refreshCount;

    // Background shortcuts must NOT fire while settingsDialog is open
    QTest::keyClick(win, 'j');
    QTest::keyClick(win, 'k');
    QTest::keyClick(win, 'm');
    QTest::keyClick(win, 'r');
    QTest::keyClick(win, 'g');
    QTest::keyClick(win, 'w');
    QTest::keyClick(win, '/');
    QCoreApplication::processEvents();

    QCOMPARE(listView->property("currentIndex").toInt(), curIdxBeforeModal);
    QCOMPARE(backend.isMasked(), maskBeforeModal);
    QCOMPARE(backend.m_refreshCount, refreshBeforeModal);
    QCOMPARE(searchInput->property("activeFocus").toBool(), false);

    // Close SettingsDialog
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(settingsDialog->property("visible").toBool(), false, 500);
    QCOMPARE(mainObj->property("isModalOpen").toBool(), false);

    // -------------------------------------------------------------------------
    // PART C: When HelpOverlay is open (isModalOpen == true)
    // -------------------------------------------------------------------------
    QTest::keyClick(win, Qt::Key_F1);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), true, 500);
    QCOMPARE(mainObj->property("isModalOpen").toBool(), true);

    QTest::keyClick(win, 'j');
    QTest::keyClick(win, 'k');
    QTest::keyClick(win, 'm');
    QTest::keyClick(win, 'r');
    QTest::keyClick(win, 'g');
    QTest::keyClick(win, 'w');
    QTest::keyClick(win, '/');
    QCoreApplication::processEvents();

    QCOMPARE(listView->property("currentIndex").toInt(), curIdxBeforeModal);
    QCOMPARE(backend.isMasked(), maskBeforeModal);
    QCOMPARE(backend.m_refreshCount, refreshBeforeModal);
    QCOMPARE(searchInput->property("activeFocus").toBool(), false);

    // Close HelpOverlay
    QTest::keyClick(win, Qt::Key_Escape);
    QCoreApplication::processEvents();
    QTRY_COMPARE_WITH_TIMEOUT(helpOverlay->property("visible").toBool(), false, 500);
    QCOMPARE(mainObj->property("isModalOpen").toBool(), false);
}

// -----------------------------------------------------------------------------
// 3. Strict Visual Denoising Invariants Test
// -----------------------------------------------------------------------------
void M5ChallengerE2ETests::testVisualDenoisingInvariants() {
    // 1. Audit all QML source files for 0 occurrences of "5.5", "(周)", "(周额度)"
    const QStringList qmlFiles = {
        QStringLiteral(":/Main.qml"),
        QStringLiteral(":/HeaderBar.qml"),
        QStringLiteral(":/FilterBar.qml"),
        QStringLiteral(":/AccountListView.qml"),
        QStringLiteral(":/SettingsDialog.qml"),
        QStringLiteral(":/HelpOverlay.qml")
    };

    for (const QString &qmlPath : qmlFiles) {
        QFile file(qmlPath);
        QVERIFY2(file.open(QIODevice::ReadOnly | QIODevice::Text),
                 qPrintable(QString("Failed opening %1").arg(qmlPath)));
        const QString content = QString::fromUtf8(file.readAll());
        file.close();

        // Must not contain "5.5" badge
        QVERIFY2(!content.contains(QStringLiteral("\"5.5\"")),
                 qPrintable(QString("Violation: '\"5.5\"' in %1").arg(qmlPath)));
        QVERIFY2(!content.contains(QStringLiteral("[5.5]")),
                 qPrintable(QString("Violation: '[5.5]' in %1").arg(qmlPath)));

        // Must not contain "(周)" or "(周额度)"
        QVERIFY2(!content.contains(QStringLiteral("(周)")),
                 qPrintable(QString("Violation: '(周)' in %1").arg(qmlPath)));
        QVERIFY2(!content.contains(QStringLiteral("(周额度)")),
                 qPrintable(QString("Violation: '(周额度)' in %1").arg(qmlPath)));
    }

    // 2. Audit Column 5 header and Weekly Depleted logic in AccountListView.qml
    QFile alvFile(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(alvFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString alvContent = QString::fromUtf8(alvFile.readAll());
    alvFile.close();

    QVERIFY2(alvContent.contains(QStringLiteral("text: qsTr(\"Gemini 4\")")),
             "Column 5 header is not strictly text: qsTr(\"Gemini 4\")");

    // Audit Weekly Depleted logic
    QVERIFY2(alvContent.contains(QStringLiteral("model.gemini38QuotaW <= 0.0001")),
             "Gemini 3.8 weekly depletion short-circuit missing");
    QVERIFY2(alvContent.contains(QStringLiteral("model.claudeQuotaW <= 0.0001")),
             "Claude weekly depletion short-circuit missing");
    QVERIFY2(alvContent.contains(QStringLiteral("qsTr(\"Weekly Depleted\")")),
             "Localized 'Weekly Depleted' reset label missing");

    // Verify translations exist
    QFile enFile(QStringLiteral(":/i18n/en.json"));
    QVERIFY(enFile.open(QIODevice::ReadOnly));
    QJsonObject enDoc = QJsonDocument::fromJson(enFile.readAll()).object();
    QCOMPARE(enDoc.value(QStringLiteral("Weekly Depleted")).toString(), QStringLiteral("Weekly Depleted"));
    QCOMPARE(enDoc.value(QStringLiteral("Gemini 4")).toString(), QStringLiteral("Gemini 4"));

    QFile zhFile(QStringLiteral(":/i18n/zh-CN.json"));
    QVERIFY(zhFile.open(QIODevice::ReadOnly));
    QJsonObject zhDoc = QJsonDocument::fromJson(zhFile.readAll()).object();
    QCOMPARE(zhDoc.value(QStringLiteral("Weekly Depleted")).toString(), QStringLiteral("周枯竭"));
    QCOMPARE(zhDoc.value(QStringLiteral("Gemini 4")).toString(), QStringLiteral("Gemini 4"));

    // Check captured binding loops and warnings
    QVERIFY2(s_logBindingLoops.isEmpty(),
             qPrintable(QString("Binding loops detected: %1").arg(s_logBindingLoops.join("; "))));
}

QTEST_MAIN(M5ChallengerE2ETests)
#include "m5_challenger_e2e_test.moc"
