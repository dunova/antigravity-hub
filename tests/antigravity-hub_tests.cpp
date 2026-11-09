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
#include <QUrl>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <cstdio>

#include "theme.h"
#include "translator.h"
#include "models.h"
#include "backend.h"
#include "iconprovider.h"

class AntigravityHubTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // Milestone 1 Tests
    void themeFallsBack();
    void themeReadsAccent();
    void themeFollowsHyprlandRounding();
    void translatorFallsBackToEnglish();
    void translatorFollowsTheLanguageFile();
    void translatorPicksPluralForms();
    void resourcesBundleVerification();
    void themeSurvivesInotifyAtomicSwap();

    // Milestone 2 Tests: AccountModel & Roles
    void accountModelJsonParsingAndRoles();
    void accountModelMaskingAndStatus();
    void accountModelInotifyRefresh();

    // Milestone 2 Tests: AccountFilterProxyModel
    void accountFilterProxyModelFiltering();

    // Milestone 2 Tests: BackendController
    void backendControllerStateAndUrls();
    void backendControllerOffscreenExecution();

    // Milestone 3 Tests: QML Components Instantiation & Smoke
    void qmlComponentsInstantiationAndSmoke();
    void accountListViewVisualDenoisingInvariants();

    void cleanupTestCase();
};

void AntigravityHubTests::initTestCase() {
    qDebug() << "Initializing Antigravity Hub Milestone 1 & 2 test suite...";
}

// -----------------------------------------------------------------------------
// Milestone 1: Theme & Translator Verification
// -----------------------------------------------------------------------------

void AntigravityHubTests::themeFallsBack() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    Theme theme(tempDir.path());
    QCOMPARE(theme.accent(), QString("#FFD60A"));
    QCOMPARE(theme.accentForeground(), QString("black"));
    QCOMPARE(theme.radius(), 0);
    QCOMPARE(theme.mode(), QString("dark"));
    QCOMPARE(theme.background(), QString("#0e0e14"));
    QCOMPARE(theme.border(), QString("rgba(255, 255, 255, 0.08)"));
}

void AntigravityHubTests::themeReadsAccent() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    QDir(tempDir.path()).mkpath("theme");
    QFile colorsFile(tempDir.filePath("theme/colors.toml"));
    QVERIFY(colorsFile.open(QIODevice::WriteOnly | QIODevice::Text));
    colorsFile.write(
        "mode = \"dark\"\n"
        "accent = \"#112233\"\n"
        "darker_background = \"#0a1713\"\n"
        "dark_background = \"#0f1e19\"\n"
        "background = \"#142620\"\n"
        "lighter_background = \"#203b31\"\n"
        "bright_foreground = \"#f0faf4\"\n"
        "foreground = \"#dfede5\"\n"
        "light_foreground = \"#bed6c9\"\n"
        "dark_foreground = \"#91ad9f\"\n"
    );
    colorsFile.close();

    Theme theme(tempDir.path());
    QCOMPARE(theme.accent(), QString("#112233"));
    QCOMPARE(theme.accentForeground(), QString("white"));
    QCOMPARE(theme.background(), QString("#142620"));
    QCOMPARE(theme.surface1(), QString("#0f1e19"));
    QCOMPARE(theme.surface2(), QString("#142620"));
    QCOMPARE(theme.surface3(), QString("#203b31"));
    QCOMPARE(theme.text1(), QString("#FFFFFF"));
    QCOMPARE(theme.text2(), QString("#F3F4F6"));
    QCOMPARE(theme.text3(), QString("#9CA3AF"));
    QCOMPARE(theme.text4(), QString("#6B7280"));

    // Verify Light Mode (白色主题) switch
    theme.setThemeMode("light");
    QCOMPARE(theme.mode(), QString("light"));
    QCOMPARE(theme.background(), QString("#FFFFFF"));
    QCOMPARE(theme.surface1(), QString("#F8FAFC"));
    QCOMPARE(theme.text1(), QString("#0F172A"));
    QCOMPARE(theme.text2(), QString("#1E293B"));

    // Verify Dark Mode switch
    theme.setThemeMode("dark");
    QCOMPARE(theme.mode(), QString("dark"));
    QCOMPARE(theme.text1(), QString("#FFFFFF"));
}

void AntigravityHubTests::themeFollowsHyprlandRounding() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString mockScriptPath = tempDir.filePath("mock_hyprctl.sh");
    QFile mockScript(mockScriptPath);
    QVERIFY(mockScript.open(QIODevice::WriteOnly | QIODevice::Text));
    mockScript.write(
        "#!/bin/sh\n"
        "echo '{\"option\": \"decoration:rounding\", \"int\": 6, \"set\": true}'\n"
    );
    mockScript.close();
    mockScript.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);

    Theme theme(tempDir.path(), nullptr, mockScriptPath);
    QTRY_COMPARE_WITH_TIMEOUT(theme.radius(), 6, 2500);
}

void AntigravityHubTests::translatorFallsBackToEnglish() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    Translator translator(tempDir.filePath("non_existent_language_file"), ":/i18n");
    QCOMPARE(translator.language(), QString("en"));

    QVERIFY(translator.translate("Main", "NonExistentKey123").isEmpty());
    QCOMPARE(translator.translate("Main", "Antigravity Hub"), QString("Antigravity Hub"));
    QCOMPARE(translator.translate("Main", "Mask"), QString("Mask"));
    QCOMPARE(translator.translate("Main", "Gemini 4"), QString("Gemini 4"));
}

void AntigravityHubTests::translatorFollowsTheLanguageFile() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString langFilePath = tempDir.filePath("language");
    QFile langFile(langFilePath);
    QVERIFY(langFile.open(QIODevice::WriteOnly | QIODevice::Text));
    langFile.write("zh-CN\n");
    langFile.close();

    Translator translator(langFilePath, ":/i18n");
    QCOMPARE(translator.language(), QString("zh-CN"));

    QCOMPARE(translator.translate("Main", "Mask"), QString("打码"));
    QCOMPARE(translator.translate("Main", "Settings"), QString("设置"));
    QCOMPARE(translator.translate("Main", "Weekly"), QString("周"));
    QCOMPARE(translator.translate("Main", "Gemini 4"), QString("Gemini 4"));

    QSignalSpy spy(&translator, &Translator::changed);
    QVERIFY(langFile.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text));
    langFile.write("en\n");
    langFile.close();

    QTRY_COMPARE_WITH_TIMEOUT(translator.language(), QString("en"), 3000);
    QCOMPARE(translator.translate("Main", "Mask"), QString("Mask"));
    QVERIFY(spy.count() >= 1);
}

void AntigravityHubTests::translatorPicksPluralForms() {
    QCOMPARE(Translator::pluralCategory("en", 1), QString("one"));
    QCOMPARE(Translator::pluralCategory("en", 0), QString("other"));
    QCOMPARE(Translator::pluralCategory("en", 2), QString("other"));
    QCOMPARE(Translator::pluralCategory("en", 10), QString("other"));

    QCOMPARE(Translator::pluralCategory("zh-CN", 1), QString("other"));
    QCOMPARE(Translator::pluralCategory("zh-CN", 2), QString("other"));
    QCOMPARE(Translator::pluralCategory("zh-CN", 100), QString("other"));

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    Translator enTrans(tempDir.filePath("lang_en"), ":/i18n");
    QCOMPARE(enTrans.translate("Main", "%n account(s) selected", nullptr, 1), QString("%n account selected"));
    QCOMPARE(enTrans.translate("Main", "%n account(s) selected", nullptr, 5), QString("%n accounts selected"));

    QFile zhLang(tempDir.filePath("lang_zh"));
    QVERIFY(zhLang.open(QIODevice::WriteOnly | QIODevice::Text));
    zhLang.write("zh-CN\n");
    zhLang.close();
    Translator zhTrans(tempDir.filePath("lang_zh"), ":/i18n");
    QCOMPARE(zhTrans.translate("Main", "%n account(s) selected", nullptr, 1), QString("已选 %n 项"));
    QCOMPARE(zhTrans.translate("Main", "%n account(s) selected", nullptr, 5), QString("已选 %n 项"));
}

void AntigravityHubTests::resourcesBundleVerification() {
    QVERIFY(QFile::exists(":/i18n/en.json"));
    QVERIFY(QFile::exists(":/i18n/zh-CN.json"));

    QFile enFile(":/i18n/en.json");
    QVERIFY(enFile.open(QIODevice::ReadOnly));
    QJsonParseError errEn;
    const auto enDoc = QJsonDocument::fromJson(enFile.readAll(), &errEn);
    QCOMPARE(errEn.error, QJsonParseError::NoError);
    QVERIFY(enDoc.isObject());
    const auto enObj = enDoc.object();
    QVERIFY(enObj.contains("Gemini 4"));
    QCOMPARE(enObj.value("Gemini 4").toString(), QString("Gemini 4"));

    QFile zhFile(":/i18n/zh-CN.json");
    QVERIFY(zhFile.open(QIODevice::ReadOnly));
    QJsonParseError errZh;
    const auto zhDoc = QJsonDocument::fromJson(zhFile.readAll(), &errZh);
    QCOMPARE(errZh.error, QJsonParseError::NoError);
    QVERIFY(zhDoc.isObject());
    const auto zhObj = zhDoc.object();
    QVERIFY(zhObj.contains("Gemini 4"));
    QCOMPARE(zhObj.value("Gemini 4").toString(), QString("Gemini 4"));

    const auto enKeys = enObj.keys();
    for (const auto &key : enKeys) {
        QVERIFY2(zhObj.contains(key), qPrintable(QString("Key '%1' present in en.json but missing in zh-CN.json").arg(key)));
    }
    const auto zhKeys = zhObj.keys();
    for (const auto &key : zhKeys) {
        QVERIFY2(enObj.contains(key), qPrintable(QString("Key '%1' present in zh-CN.json but missing in en.json").arg(key)));
    }

    const QStringList qmlFiles = {
        ":/Main.qml", ":/HeaderBar.qml", ":/FilterBar.qml",
        ":/AccountListView.qml", ":/SettingsDialog.qml", ":/HelpOverlay.qml"
    };
    QRegularExpression qstrRegex(QStringLiteral(R"re(qsTr\(\s*"([^"\\]*(?:\\.[^"\\]*)*)")re"));
    for (const auto &qmlPath : qmlFiles) {
        QFile f(qmlPath);
        QVERIFY(f.open(QIODevice::ReadOnly | QIODevice::Text));
        const QString qmlContent = QString::fromUtf8(f.readAll());
        auto matchIterator = qstrRegex.globalMatch(qmlContent);
        while (matchIterator.hasNext()) {
            auto match = matchIterator.next();
            QString key = match.captured(1);
            QVERIFY2(enObj.contains(key),
                     qPrintable(QString("Missing i18n key in en.json: '%1' (found in %2)").arg(key, qmlPath)));
        }
    }

    QVERIFY(QFile::exists(":/assets/logo.svg"));
    QVERIFY(QFile::exists(":/Main.qml"));
}

void AntigravityHubTests::themeSurvivesInotifyAtomicSwap() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    QDir(tempDir.path()).mkpath("theme");
    QFile initialColors(tempDir.filePath("theme/colors.toml"));
    QVERIFY(initialColors.open(QIODevice::WriteOnly | QIODevice::Text));
    initialColors.write("accent = \"#223344\"\nmode = \"dark\"\n");
    initialColors.close();

    Theme theme(tempDir.path());
    QCOMPARE(theme.accent(), QString("#223344"));

    QSignalSpy spy(&theme, &Theme::changed);

    QDir(tempDir.path()).mkpath("next_theme");
    QFile nextColors(tempDir.filePath("next_theme/colors.toml"));
    QVERIFY(nextColors.open(QIODevice::WriteOnly | QIODevice::Text));
    nextColors.write("accent = \"#8bcbb1\"\nmode = \"dark\"\n");
    nextColors.close();

    QVERIFY(QDir(tempDir.filePath("theme")).removeRecursively());
    QVERIFY(QDir().rename(tempDir.filePath("next_theme"), tempDir.filePath("theme")));

    QTRY_COMPARE_WITH_TIMEOUT(theme.accent(), QString("#8bcbb1"), 3000);
    QCOMPARE(theme.accentForeground(), QString("black"));
    QVERIFY(spy.count() >= 1);
}

// -----------------------------------------------------------------------------
// Milestone 2: AccountModel & Roles
// -----------------------------------------------------------------------------

void AntigravityHubTests::accountModelJsonParsingAndRoles() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Isolate environment
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    // Construct mock payload containing:
    // 1. ACTIVE healthy account (cakeai66@gmail.com)
    // 2. WARNING account (novadu99@gmail.com)
    // 3. EXHAUSTED & BLOCKED account (blocked@gmail.com) with weekly short-circuit
    QJsonObject accountsObj;

    // Account 1: cakeai66
    QJsonObject a1;
    a1["email"] = "cakeai66@gmail.com";
    a1["name"] = "cakeai66";
    a1["tier"] = "PRO";
    a1["pro"] = true;
    a1["validation_blocked"] = false;
    QJsonObject a1Gem;
    a1Gem["quota_5h"] = 1.0;
    a1Gem["quota_weekly"] = 0.5389;
    a1Gem["reset_time_5h"] = "2026-11-09T09:02:02Z";
    a1Gem["reset_time_weekly"] = "2026-11-14T02:15:32Z";
    a1["gemini"] = a1Gem;
    QJsonObject a1Cla;
    a1Cla["quota_5h"] = 0.8;
    a1Cla["quota_weekly"] = 0.6;
    a1Cla["reset_time_5h"] = "2026-11-09T09:02:02Z";
    a1Cla["reset_time_weekly"] = "2026-11-12T16:21:29Z";
    a1["claude"] = a1Cla;
    QJsonObject a1Gem4;
    a1Gem4["quota_weekly"] = 0.85;
    a1Gem4["reset_time_weekly"] = "2026-11-14T02:17:23Z";
    a1["gemini4"] = a1Gem4;
    accountsObj["cakeai66@gmail.com"] = a1;

    // Account 2: novadu99
    QJsonObject a2;
    a2["email"] = "novadu99@gmail.com";
    a2["name"] = "Daniel lu";
    a2["tier"] = "PRO";
    a2["pro"] = true;
    a2["validation_blocked"] = false;
    QJsonObject a2Gem;
    a2Gem["quota_5h"] = 0.12;
    a2Gem["quota_weekly"] = 0.10; // < 0.15 => Warning
    a2["gemini"] = a2Gem;
    QJsonObject a2Cla;
    a2Cla["quota_5h"] = 0.12;
    a2Cla["quota_weekly"] = 0.10;
    a2["claude"] = a2Cla;
    QJsonObject a2Gem4;
    a2Gem4["quota_weekly"] = 0.16;
    a2["gemini4"] = a2Gem4;
    accountsObj["novadu99@gmail.com"] = a2;

    // Account 3: blocked & weekly exhausted
    QJsonObject a3;
    a3["email"] = "blocked@gmail.com";
    a3["name"] = "blocked";
    a3["tier"] = "FREE";
    a3["pro"] = false;
    a3["validation_blocked"] = true;
    a3["validation_url"] = "https://accounts.google.com/recover";
    QJsonObject a3Gem;
    a3Gem["quota_5h"] = 0.90; // Weekly is 0, should short-circuit to 0.0!
    a3Gem["quota_weekly"] = 0.0000;
    a3["gemini"] = a3Gem;
    QJsonObject a3Cla;
    a3Cla["quota_5h"] = 0.80;
    a3Cla["quota_weekly"] = 0.0000;
    a3["claude"] = a3Cla;
    accountsObj["blocked@gmail.com"] = a3;

    QJsonObject rootDoc;
    rootDoc["active_email"] = "cakeai66@gmail.com";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    // Instantiate AccountModel
    AccountModel model;
    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.activeEmail(), QString("cakeai66@gmail.com"));

    // Find row index for cakeai66@gmail.com
    int rowCake = model.findIndexByEmail("cakeai66@gmail.com");
    QVERIFY(rowCake >= 0);
    QModelIndex idxCake = model.index(rowCake, 0);

    QCOMPARE(model.data(idxCake, AccountModel::EmailRole).toString(), QString("cakeai66@gmail.com"));
    QCOMPARE(model.data(idxCake, AccountModel::ShortNameRole).toString(), QString("cakeai66"));
    QCOMPARE(model.data(idxCake, AccountModel::MaskedNameRole).toString(), QString("c***66"));
    QCOMPARE(model.data(idxCake, AccountModel::IsActiveRole).toBool(), true);
    QCOMPARE(model.data(idxCake, AccountModel::Gemini4QuotaRole).toDouble(), 0.85);
    QCOMPARE(model.data(idxCake, AccountModel::Gemini4ValidRole).toBool(), true);
    QCOMPARE(model.data(idxCake, AccountModel::Gemini38Quota5hRole).toDouble(), 1.0);
    QCOMPARE(model.data(idxCake, AccountModel::Gemini38QuotaWRole).toDouble(), 0.5389);
    QCOMPARE(model.data(idxCake, AccountModel::ClaudeQuota5hRole).toDouble(), 0.8);
    QCOMPARE(model.data(idxCake, AccountModel::ClaudeQuotaWRole).toDouble(), 0.6);
    QCOMPARE(model.data(idxCake, AccountModel::IsBlockedRole).toBool(), false);

    // Verify Row for blocked@gmail.com (Weekly exhaustion short-circuiting)
    int rowBlocked = model.findIndexByEmail("blocked@gmail.com");
    QVERIFY(rowBlocked >= 0);
    QModelIndex idxBlocked = model.index(rowBlocked, 0);

    QCOMPARE(model.data(idxBlocked, AccountModel::IsActiveRole).toBool(), false);
    QCOMPARE(model.data(idxBlocked, AccountModel::IsBlockedRole).toBool(), true);
    // Crucial rule: weekly quota <= 0.0001 short-circuits 5h quota to 0.0!
    QCOMPARE(model.data(idxBlocked, AccountModel::Gemini38Quota5hRole).toDouble(), 0.0);
    QCOMPARE(model.data(idxBlocked, AccountModel::ClaudeQuota5hRole).toDouble(), 0.0);
    QCOMPARE(model.data(idxBlocked, AccountModel::StatusRole).toString(), QString("EXHAUSTED"));
}

void AntigravityHubTests::accountModelMaskingAndStatus() {
    AccountModel model;

    // Verify masking algorithm
    QCOMPARE(model.maskName("cakeai66"), QString("c***66"));
    QCOMPARE(model.maskName("novadu99"), QString("n***99"));
    QCOMPARE(model.maskName("admin"), QString("a***in"));
    QCOMPARE(model.maskName("user"), QString("u***er"));
    QCOMPARE(model.maskName("bob"), QString("b***ob"));
    QCOMPARE(model.maskName("ab"), QString("a***b"));
    QCOMPARE(model.maskName("a"), QString("a***"));
    QCOMPARE(model.maskName(""), QString(""));

    // Verify dynamic isMasked property
    QSignalSpy spyMask(&model, &AccountModel::isMaskedChanged);
    QCOMPARE(model.isMasked(), false);
    QVERIFY(QMetaObject::invokeMethod(&model, "setIsMasked", Q_ARG(bool, true)));
    QCOMPARE(model.isMasked(), true);
    QCOMPARE(spyMask.count(), 1);
    QVERIFY(QMetaObject::invokeMethod(&model, "setIsMasked", Q_ARG(bool, false)));
    QCOMPARE(model.isMasked(), false);
    QCOMPARE(spyMask.count(), 2);
}

void AntigravityHubTests::accountModelInotifyRefresh() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    // 1. Initial write
    QJsonObject accountsObj;
    QJsonObject a1;
    a1["email"] = "acc1@gmail.com";
    accountsObj["acc1@gmail.com"] = a1;

    QJsonObject rootDoc;
    rootDoc["active_email"] = "acc1@gmail.com";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    AccountModel model;
    QCOMPARE(model.rowCount(), 1);

    QSignalSpy spyRefresh(&model, &AccountModel::dataRefreshed);

    // 2. Simulate atomic write (tmp file + rename)
    const QString tmpFile = tempDir.filePath("data/accounts_hub.json.tmp");
    QJsonObject a2;
    a2["email"] = "acc2@gmail.com";
    accountsObj["acc2@gmail.com"] = a2;
    rootDoc["accounts"] = accountsObj;

    QFile fTmp(tmpFile);
    QVERIFY(fTmp.open(QIODevice::WriteOnly));
    fTmp.write(QJsonDocument(rootDoc).toJson());
    fTmp.close();

    // Linux POSIX rename(2) atomically replaces target if it exists, exactly as Python's os.replace() does
    QVERIFY(::rename(tmpFile.toLocal8Bit().constData(), accountsFile.toLocal8Bit().constData()) == 0);

    // Wait for inotify debounce (50ms) to reload model
    QTRY_COMPARE_WITH_TIMEOUT(model.rowCount(), 2, 2000);
    QVERIFY(spyRefresh.count() >= 1);
}

// -----------------------------------------------------------------------------
// Milestone 2: AccountFilterProxyModel Filtering & Counting
// -----------------------------------------------------------------------------

void AntigravityHubTests::accountFilterProxyModelFiltering() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;

    // Item 1: Plentiful & Usable
    QJsonObject a1;
    a1["email"] = "cakeai66@gmail.com";
    a1["name"] = "cakeai66";
    a1["validation_blocked"] = false;
    QJsonObject a1Gem; a1Gem["quota_5h"] = 1.0; a1Gem["quota_weekly"] = 0.8; a1["gemini"] = a1Gem;
    QJsonObject a1Cla; a1Cla["quota_5h"] = 1.0; a1Cla["quota_weekly"] = 0.8; a1["claude"] = a1Cla;
    accountsObj["cakeai66@gmail.com"] = a1;

    // Item 2: Warning (< 0.15) & Usable
    QJsonObject a2;
    a2["email"] = "novadu99@gmail.com";
    a2["name"] = "Daniel";
    a2["validation_blocked"] = false;
    QJsonObject a2Gem; a2Gem["quota_5h"] = 0.10; a2Gem["quota_weekly"] = 0.08; a2["gemini"] = a2Gem;
    QJsonObject a2Cla; a2Cla["quota_5h"] = 0.10; a2Cla["quota_weekly"] = 0.08; a2["claude"] = a2Cla;
    accountsObj["novadu99@gmail.com"] = a2;

    // Item 3: Exhausted (<= 0.0001)
    QJsonObject a3;
    a3["email"] = "dead@gmail.com";
    a3["name"] = "dead";
    a3["validation_blocked"] = false;
    QJsonObject a3Gem; a3Gem["quota_5h"] = 0.0; a3Gem["quota_weekly"] = 0.0; a3["gemini"] = a3Gem;
    QJsonObject a3Cla; a3Cla["quota_5h"] = 0.0; a3Cla["quota_weekly"] = 0.0; a3["claude"] = a3Cla;
    accountsObj["dead@gmail.com"] = a3;

    QJsonObject rootDoc;
    rootDoc["active_email"] = "cakeai66@gmail.com";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    // Initial state: all 3 items visible
    QCOMPARE(proxy.totalCount(), 3);
    QCOMPARE(proxy.filteredCount(), 3);
    QCOMPARE(proxy.rowCount(), 3);

    // 1. Text filter test
    proxy.setFilterText("cake");
    QCOMPARE(proxy.filteredCount(), 1);
    QCOMPARE(proxy.totalCount(), 3);
    QCOMPARE(proxy.rowCount(), 1);

    // Case-insensitive search
    proxy.setFilterText("CAKE");
    QCOMPARE(proxy.filteredCount(), 1);

    // Non-matching text
    proxy.setFilterText("nonexistent");
    QCOMPARE(proxy.filteredCount(), 0);
    QCOMPARE(proxy.rowCount(), 0);

    // Clear text filter
    proxy.setFilterText("");
    QCOMPARE(proxy.filteredCount(), 3);

    // 2. Status tab filter tests
    proxy.setStatusTab("usable");
    // cakeai66 and novadu99 are usable; dead is exhausted
    QCOMPARE(proxy.filteredCount(), 2);

    proxy.setStatusTab("plentiful");
    // only cakeai66 has weekly >= 0.50
    QCOMPARE(proxy.filteredCount(), 1);

    proxy.setStatusTab("warning");
    // only novadu99 has weekly < 0.15
    QCOMPARE(proxy.filteredCount(), 1);

    proxy.setStatusTab("exhausted");
    // dead has weekly <= 0.0001
    QCOMPARE(proxy.filteredCount(), 1);

    // 3. Combined Filter test
    proxy.setStatusTab("usable");
    proxy.setFilterText("novadu");
    QCOMPARE(proxy.filteredCount(), 1);

    proxy.setStatusTab("exhausted");
    proxy.setFilterText("novadu");
    QCOMPARE(proxy.filteredCount(), 0);

    // Reset filters
    proxy.setStatusTab("all");
    proxy.setFilterText("");
    QCOMPARE(proxy.filteredCount(), 3);
}

// -----------------------------------------------------------------------------
// Milestone 2: BackendController State & Endpoints
// -----------------------------------------------------------------------------

void AntigravityHubTests::backendControllerStateAndUrls() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    BackendController backend;

    // Verify initial states
    QCOMPARE(backend.isMasked(), false);
    QCOMPARE(backend.isBusy(), false);
    QCOMPARE(backend.isManualLocked(), false);
    QCOMPARE(backend.manualLockRemaining(), 0);

    // Verify masking toggle & signal emission via QMetaObject to guarantee QML invokability
    QSignalSpy spyMask(&backend, &BackendController::maskedChanged);
    QVERIFY2(QMetaObject::invokeMethod(&backend, "setMasked", Q_ARG(bool, true)),
             "CRITICAL: BackendController::setMasked is not invokable via QMetaObject / QML!");
    QCOMPARE(backend.isMasked(), true);
    QCOMPARE(spyMask.count(), 1);

    QVERIFY2(QMetaObject::invokeMethod(&backend, "setMasked", Q_ARG(bool, false)),
             "CRITICAL: BackendController::setMasked is not invokable via QMetaObject / QML!");
    QCOMPARE(backend.isMasked(), false);
    QCOMPARE(spyMask.count(), 2);

    // Verify that all core operations are invokable without crash
    // In offscreen testing, these methods dispatch async HTTP requests safely
    QVERIFY(QMetaObject::invokeMethod(&backend, "switchAccount", Q_ARG(QString, QStringLiteral("test@example.com"))));
    QVERIFY(QMetaObject::invokeMethod(&backend, "switchTopGemini"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "toggleRotation"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "refreshQuota", Q_ARG(bool, true)));
    QVERIFY(QMetaObject::invokeMethod(&backend, "triggerPrewarm"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "unblockAccount", Q_ARG(QString, QStringLiteral("test@example.com"))));
    QVERIFY(QMetaObject::invokeMethod(&backend, "saveSettings", Q_ARG(QJsonObject, QJsonObject())));
    QVERIFY(QMetaObject::invokeMethod(&backend, "unlockManualOverride"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "copyToClipboard", Q_ARG(QString, QStringLiteral("sample text"))));
    QVERIFY(QMetaObject::invokeMethod(&backend, "checkDaemonLiveness"));
}

void AntigravityHubTests::backendControllerOffscreenExecution() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    BackendController backend;

    QSignalSpy spyBusy(&backend, &BackendController::busyChanged);
    QSignalSpy spyNotify(&backend, &BackendController::notificationRequested);

    // Invoke an operation that triggers network dispatch
    backend.refreshQuota(true);

    // Verify busy state transitioned
    QVERIFY(spyBusy.count() >= 1);

    // Process pending events in Qt event loop to ensure non-blocking offscreen handling
    QCoreApplication::processEvents();

    // Verify no crashes or UI thread blockages occurred
    QVERIFY(true);
}

void AntigravityHubTests::qmlComponentsInstantiationAndSmoke() {
    QQmlEngine engine;
    engine.addImageProvider(QStringLiteral("icons"), new IconProvider());

    // 1. Register required custom C++ types
    qmlRegisterType<AccountModel>("AntigravityHub", 1, 0, "AccountModel");
    qmlRegisterType<AccountFilterProxyModel>("AntigravityHub", 1, 0, "AccountFilterProxyModel");
    qmlRegisterType<BackendController>("AntigravityHub", 1, 0, "BackendController");
    qmlRegisterUncreatableType<Theme>("AntigravityHub", 1, 0, "Theme",
        QStringLiteral("Theme context property"));
    qmlRegisterUncreatableType<Translator>("AntigravityHub", 1, 0, "Translator",
        QStringLiteral("Translator context property"));

    // 2. Setup mock environment & context properties
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    Theme theme(tempDir.path());
    Translator translator(tempDir.filePath("lang"), ":/i18n");
    BackendController backend;
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

    // 3. Verify SettingsDialog.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/SettingsDialog.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "SettingsDialog failed to instantiate offscreen");
        QCOMPARE(obj->property("modal").toBool(), true);
        QVERIFY(obj->metaObject()->indexOfMethod("saveAndApply()") != -1);
    }

    // 4. Verify HelpOverlay.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/HelpOverlay.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "HelpOverlay failed to instantiate offscreen");
        QCOMPARE(obj->property("modal").toBool(), true);
        QVERIFY(obj->metaObject()->indexOfMethod("toggle()") != -1);
    }

    // 5. Verify HeaderBar.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/HeaderBar.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "HeaderBar failed to instantiate offscreen");
    }

    // 6. Verify FilterBar.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/FilterBar.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "FilterBar failed to instantiate offscreen");
        QVERIFY(obj->metaObject()->indexOfMethod("focusSearch()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("clearSearch()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("clearOrUnfocus()") != -1);
    }

    // 7. Verify AccountListView.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/AccountListView.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "AccountListView failed to instantiate offscreen");
        QVERIFY(obj->metaObject()->indexOfMethod("selectNext()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("selectPrevious()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("activateCurrent()") != -1);
    }

    // 8. Verify Main.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/Main.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "Main.qml failed to instantiate offscreen");
    }
}

void AntigravityHubTests::accountListViewVisualDenoisingInvariants() {
    QFile file(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(file.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString content = QString::fromUtf8(file.readAll());
    file.close();

    // 1. Zero tolerance on "5.5" badge in account name cell
    QVERIFY2(!content.contains(QStringLiteral("\"5.5\"")),
             "MANDATORY DENOISING VIOLATION: Literal '5.5' found in AccountListView.qml");
    QVERIFY2(!content.contains(QStringLiteral("[5.5]")),
             "MANDATORY DENOISING VIOLATION: '[5.5]' badge found in AccountListView.qml");

    // 2. Column 5 header must strictly be "Gemini 4", purged of "(周)"
    QVERIFY2(content.contains(QStringLiteral("text: qsTr(\"Gemini 4\")")),
             "MANDATORY DENOISING VIOLATION: Column header does not strictly match qsTr(\"Gemini 4\")");
    QVERIFY2(!content.contains(QStringLiteral("(周)")),
             "MANDATORY DENOISING VIOLATION: '(周)' found in AccountListView.qml");
    QVERIFY2(!content.contains(QStringLiteral("(周额度)")),
             "MANDATORY DENOISING VIOLATION: '(周额度)' found in AccountListView.qml");

    // 3. Weekly depletion short-circuit to 0.0% & Weekly Depleted
    QVERIFY2(content.contains(QStringLiteral("qsTr(\"Weekly Depleted\")")),
             "AccountListView.qml missing Weekly Depleted short-circuit handler");
}

void AntigravityHubTests::cleanupTestCase() {
    qDebug() << "Antigravity Hub Milestone 1 & 2 test suite execution completed.";
}

QTEST_MAIN(AntigravityHubTests)
#include "antigravity-hub_tests.moc"
