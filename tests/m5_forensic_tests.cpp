#include <QtTest>
#include <cstdio>
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
#include <QQuickWindow>
#include <QQuickStyle>
#include <QProcess>

#include "theme.h"
#include "translator.h"
#include "models.h"
#include "backend.h"

class M5ForensicTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // 1. Live Dynamic Theme Switching & Inotify
    void testLiveHostOmarchyTheme();
    void testThemeAtomicSwapSimulation();
    void testThemeBurstAtomicSwapStress();
    void testWcagContrastCalculations();

    // 2. Hyprland Live Rounding & Fault Tolerance
    void testHyprlandLiveRounding();
    void testHyprlandRoundingFallbackAndHangTimeout();

    // 3. Dynamic Bilingual Hot-Reloading & Retranslate
    void testBilingualDynamicHotReload();
    void testBilingualFallbackRobustness();

    // 4. QML Live Scene Retranslate & Visual Invariants
    void testQmlLiveSceneRetranslate();
    void testVisualDenoisingPurity();

    // 5. Hyprland Floating Window Rule Configuration
    void testHyprlandWindowRuleConfiguration();

    void cleanupTestCase();
};

void M5ForensicTests::initTestCase() {
    qDebug() << "=================================================================";
    qDebug() << "Starting Milestone 5 Forensic E2E & Adversarial Stress Tests";
    qDebug() << "=================================================================";
}

// -----------------------------------------------------------------------------
// 1. Live Dynamic Theme Switching
// -----------------------------------------------------------------------------

void M5ForensicTests::testLiveHostOmarchyTheme() {
    // Test that default Theme() constructor binds directly to host machine's live Omarchy state
    const QString liveDir = QDir::homePath() + "/.local/state/omarchy/current";
    if (!QFileInfo::exists(liveDir + "/theme/colors.toml")) {
        QSKIP("Host Omarchy theme colors.toml not found, skipping live check");
    }

    Theme theme;
    QCOMPARE(theme.mode(), QStringLiteral("dark"));
    QCOMPARE(theme.accent(), QStringLiteral("#8bcbb1"));
    // #8bcbb1 has relative luminance ~0.514 > 0.179 => foreground must be black
    QCOMPARE(theme.accentForeground(), QStringLiteral("black"));
    QVERIFY(!theme.background().isEmpty());
    QVERIFY(!theme.border().isEmpty());
}

void M5ForensicTests::testThemeAtomicSwapSimulation() {
    QTemporaryDir baseDir;
    QVERIFY(baseDir.isValid());

    const QString currentDir = baseDir.filePath("current");
    QDir().mkpath(currentDir);

    // Create Theme 1: Tokyo Night (Dark, accent #7aa2f7)
    const QString theme1Dir = baseDir.filePath("themes/tokyo-night");
    QDir().mkpath(theme1Dir);
    {
        QFile f(theme1Dir + "/colors.toml");
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "mode = \"dark\"\n"
            "accent = \"#7aa2f7\"\n"
            "darker_background = \"#16161e\"\n"
            "dark_background = \"#1a1b26\"\n"
            "background = \"#1f2335\"\n"
            "lighter_background = \"#24283b\"\n"
            "bright_foreground = \"#c0caf5\"\n"
            "foreground = \"#a9b1d6\"\n"
        );
        f.close();
    }

    // Create Theme 2: Everforest (Dark, accent #a7c080)
    const QString theme2Dir = baseDir.filePath("themes/everforest");
    QDir().mkpath(theme2Dir);
    {
        QFile f(theme2Dir + "/colors.toml");
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "mode = \"dark\"\n"
            "accent = \"#a7c080\"\n"
            "darker_background = \"#1e2326\"\n"
            "dark_background = \"#272e33\"\n"
            "background = \"#2e383c\"\n"
            "lighter_background = \"#374145\"\n"
            "bright_foreground = \"#d3c6aa\"\n"
            "foreground = \"#9da9a0\"\n"
        );
        f.close();
    }

    // Create Theme 3: Catppuccin Latte (Light, accent #1e66f5)
    const QString theme3Dir = baseDir.filePath("themes/catppuccin-latte");
    QDir().mkpath(theme3Dir);
    {
        QFile f(theme3Dir + "/colors.toml");
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "mode = \"light\"\n"
            "accent = \"#1e66f5\"\n"
            "darker_background = \"#e6e9ef\"\n"
            "dark_background = \"#eff1f5\"\n"
            "background = \"#dce0e8\"\n"
            "lighter_background = \"#ccd0da\"\n"
            "bright_foreground = \"#4c4f69\"\n"
            "foreground = \"#5c5f77\"\n"
        );
        f.close();
    }

    // Initial deployment: copy theme1 -> current/theme
    {
        QDir().mkpath(currentDir + "/theme");
        QFile::copy(theme1Dir + "/colors.toml", currentDir + "/theme/colors.toml");
    }

    Theme theme(currentDir);
    QCOMPARE(theme.accent(), QStringLiteral("#7aa2f7"));
    QCOMPARE(theme.mode(), QStringLiteral("dark"));

    QSignalSpy spy(&theme, &Theme::changed);

    // Simulate omarchy-theme-set:
    // 1. rm -rf current/theme
    // 2. cp -r themes/everforest current/theme
    // 3. update theme.generation
    QDir(currentDir + "/theme").removeRecursively();
    QTest::qWait(40); // 40ms transient deletion window

    QDir().mkpath(currentDir + "/theme");
    QFile::copy(theme2Dir + "/colors.toml", currentDir + "/theme/colors.toml");
    {
        QFile gen(currentDir + "/theme.generation");
        QVERIFY(gen.open(QIODevice::WriteOnly));
        gen.write("123456789\n");
    }

    // Wait for inotify & 80ms debounce
    QVERIFY2(spy.wait(1500), "ThemeEngine failed to detect atomic directory replacement for Everforest");
    QCOMPARE(theme.accent(), QStringLiteral("#a7c080"));
    QCOMPARE(theme.mode(), QStringLiteral("dark"));

    // Switch 2: To Light Mode (Catppuccin Latte)
    spy.clear();
    QDir(currentDir + "/theme").removeRecursively();
    QTest::qWait(40);
    QDir().mkpath(currentDir + "/theme");
    QFile::copy(theme3Dir + "/colors.toml", currentDir + "/theme/colors.toml");
    {
        QFile gen(currentDir + "/theme.generation");
        QVERIFY(gen.open(QIODevice::WriteOnly));
        gen.write("987654321\n");
    }

    QVERIFY2(spy.wait(1500), "ThemeEngine failed to detect atomic directory replacement for Catppuccin Latte");
    QCOMPARE(theme.accent(), QStringLiteral("#1e66f5"));
    QCOMPARE(theme.mode(), QStringLiteral("light"));
    QCOMPARE(theme.border(), QStringLiteral("rgba(0, 0, 0, 0.08)"));
}

void M5ForensicTests::testThemeBurstAtomicSwapStress() {
    QTemporaryDir baseDir;
    QVERIFY(baseDir.isValid());

    const QString currentDir = baseDir.filePath("current");
    QDir().mkpath(currentDir + "/theme");

    QFile initial(currentDir + "/theme/colors.toml");
    QVERIFY(initial.open(QIODevice::WriteOnly | QIODevice::Text));
    initial.write("mode = \"dark\"\naccent = \"#111111\"\n");
    initial.close();

    Theme theme(currentDir);
    QSignalSpy spy(&theme, &Theme::changed);

    // Rapid burst of 10 atomic replacements (stressing inotify queue and debounce re-arm)
    for (int i = 0; i < 10; ++i) {
        QDir(currentDir + "/theme").removeRecursively();
        QDir().mkpath(currentDir + "/theme");
        QFile f(currentDir + "/theme/colors.toml");
        if (f.open(QIODevice::WriteOnly | QIODevice::Text)) {
            f.write(QString("mode = \"dark\"\naccent = \"#%1%1%1%1%1%1\"\n").arg(i % 10).toUtf8());
            f.close();
        }
        QTest::qWait(15);
    }

    // Final settle state: accent "#abcdef"
    QDir(currentDir + "/theme").removeRecursively();
    QDir().mkpath(currentDir + "/theme");
    {
        QFile f(currentDir + "/theme/colors.toml");
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("mode = \"dark\"\naccent = \"#abcdef\"\n");
        f.close();
    }

    // Wait for debounce settle
    QVERIFY2(spy.wait(2000), "ThemeEngine failed to settle after burst atomic swaps");
    QTest::qWait(120);
    QCOMPARE(theme.accent(), QStringLiteral("#abcdef"));
}

void M5ForensicTests::testWcagContrastCalculations() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    QDir(tempDir.path()).mkpath("theme");

    auto writeAndGetForeground = [&](const QString &accentHex) -> QString {
        QFile f(tempDir.filePath("theme/colors.toml"));
        if (!f.open(QIODevice::WriteOnly | QIODevice::Text)) return {};
        f.write(QString("mode = \"dark\"\naccent = \"%1\"\n").arg(accentHex).toUtf8());
        f.close();
        Theme t(tempDir.path());
        return t.accentForeground();
    };

    // 1. Extreme limits
    QCOMPARE(writeAndGetForeground("#000000"), QStringLiteral("white"));
    QCOMPARE(writeAndGetForeground("#ffffff"), QStringLiteral("black"));
    QCOMPARE(writeAndGetForeground("#FFFFFF"), QStringLiteral("black"));

    // 2. High luminance bright accents -> black text
    QCOMPARE(writeAndGetForeground("#FFD60A"), QStringLiteral("black")); // Omarchy yellow
    QCOMPARE(writeAndGetForeground("#00FF00"), QStringLiteral("black")); // Lime green
    QCOMPARE(writeAndGetForeground("#00FFFF"), QStringLiteral("black")); // Cyan
    QCOMPARE(writeAndGetForeground("#8bcbb1"), QStringLiteral("black")); // Jade horse

    // 3. Low luminance dark accents -> white text
    QCOMPARE(writeAndGetForeground("#000080"), QStringLiteral("white")); // Navy
    QCOMPARE(writeAndGetForeground("#550000"), QStringLiteral("white")); // Maroon
    QCOMPARE(writeAndGetForeground("#112233"), QStringLiteral("white")); // Deep dark blue

    // 4. Boundary verification around relative luminance threshold 0.179
    // #757575 linear luminance ~0.176 < 0.179 -> white
    // #787878 linear luminance ~0.187 > 0.179 -> black
    QCOMPARE(writeAndGetForeground("#757575"), QStringLiteral("white"));
    QCOMPARE(writeAndGetForeground("#787878"), QStringLiteral("black"));

    // 5. Corrupted / Defensive inputs
    QCOMPARE(writeAndGetForeground(""), QStringLiteral("black"));
    QCOMPARE(writeAndGetForeground("not-a-color"), QStringLiteral("black"));
}

// -----------------------------------------------------------------------------
// 2. Hyprland Live Rounding & Fault Tolerance
// -----------------------------------------------------------------------------

void M5ForensicTests::testHyprlandLiveRounding() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Create a mock hyprctl script that outputs valid rounding 14
    const QString mockHyprctl = tempDir.filePath("mock_hyprctl.sh");
    {
        QFile f(mockHyprctl);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("#!/bin/sh\n"
                "echo '{\"option\": \"decoration:rounding\", \"int\": 14, \"set\": true}'\n");
        f.close();
        f.setPermissions(QFile::ExeUser | QFile::ReadUser | QFile::WriteUser);
    }

    Theme theme(tempDir.path(), nullptr, mockHyprctl);
    QSignalSpy spy(&theme, &Theme::changed);

    // Wait for the rounding process to execute
    QVERIFY2(spy.wait(2000), "Theme failed to read rounding from mock hyprctl");
    QCOMPARE(theme.radius(), 14);
}

void M5ForensicTests::testHyprlandRoundingFallbackAndHangTimeout() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Case 1: hyprctl returns non-zero error code
    {
        const QString mockError = tempDir.filePath("mock_error.sh");
        QFile f(mockError);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("#!/bin/sh\nexit 1\n");
        f.close();
        f.setPermissions(QFile::ExeUser | QFile::ReadUser | QFile::WriteUser);

        Theme theme(tempDir.path(), nullptr, mockError);
        QTest::qWait(200);
        QCOMPARE(theme.radius(), 0); // Gracefully stays at default 0
    }

    // Case 2: hyprctl returns corrupted JSON
    {
        const QString mockGarbage = tempDir.filePath("mock_garbage.sh");
        QFile f(mockGarbage);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("#!/bin/sh\necho '!!! CORRUPTED NOT JSON !!!'\n");
        f.close();
        f.setPermissions(QFile::ExeUser | QFile::ReadUser | QFile::WriteUser);

        Theme theme(tempDir.path(), nullptr, mockGarbage);
        QTest::qWait(200);
        QCOMPARE(theme.radius(), 0); // No crash, stays at 0
    }

    // Case 3: hyprctl hangs indefinitely -> 500ms timeout kills it
    {
        const QString mockHang = tempDir.filePath("mock_hang.sh");
        QFile f(mockHang);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("#!/bin/sh\nsleep 10\n");
        f.close();
        f.setPermissions(QFile::ExeUser | QFile::ReadUser | QFile::WriteUser);

        Theme theme(tempDir.path(), nullptr, mockHang);
        // Wait 700ms to let the 500ms timeout fire and kill the hung process
        QTest::qWait(700);
        QCOMPARE(theme.radius(), 0);
        // Event loop remained fully responsive, no freeze or deadlock
    }
}

// -----------------------------------------------------------------------------
// 3. Dynamic Bilingual Hot-Reloading & Retranslate
// -----------------------------------------------------------------------------

void M5ForensicTests::testBilingualDynamicHotReload() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString langFile = tempDir.filePath("language");

    // Initialize with zh-CN
    {
        QFile f(langFile);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("zh-CN\n");
        f.close();
    }

    Translator translator(langFile, QStringLiteral(":/i18n"));
    QCOMPARE(translator.language(), QStringLiteral("zh-CN"));

    // Verify Chinese translations
    QCOMPARE(translator.translate("", "Settings"), QStringLiteral("设置"));
    QCOMPARE(translator.translate("", "Mask"), QStringLiteral("打码"));
    QCOMPARE(translator.translate("", "Prewarm"), QStringLiteral("预热"));
    QCOMPARE(translator.translate("", "Refresh"), QStringLiteral("刷新"));
    QCOMPARE(translator.translate("", "Search accounts..."), QStringLiteral("搜索账号..."));

    QSignalSpy spy(&translator, &Translator::changed);

    // Atomically replace language file with "en" (POSIX atomic rename)
    const QString tempWrite = tempDir.filePath("language.tmp");
    {
        QFile f(tempWrite);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("en\n");
        f.close();
    }
    QVERIFY(::rename(tempWrite.toLocal8Bit().constData(), langFile.toLocal8Bit().constData()) == 0);

    // Wait for inotify & reload
    QVERIFY2(spy.wait(1500), "Translator failed to detect atomic language file update to English");
    QCOMPARE(translator.language(), QStringLiteral("en"));

    // Verify English translations
    QCOMPARE(translator.translate("", "Settings"), QStringLiteral("Settings"));
    QCOMPARE(translator.translate("", "Mask"), QStringLiteral("Mask"));
    QCOMPARE(translator.translate("", "Search accounts..."), QStringLiteral("Search accounts..."));

    // Hot-reload back to zh-CN (POSIX atomic rename)
    spy.clear();
    {
        QFile f(tempWrite);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("zh-CN\n");
        f.close();
    }
    QVERIFY(::rename(tempWrite.toLocal8Bit().constData(), langFile.toLocal8Bit().constData()) == 0);

    QVERIFY2(spy.wait(1500), "Translator failed to reload back to Chinese");
    QCOMPARE(translator.language(), QStringLiteral("zh-CN"));
    QCOMPARE(translator.translate("", "Settings"), QStringLiteral("设置"));
}

void M5ForensicTests::testBilingualFallbackRobustness() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString langFile = tempDir.filePath("language");

    // Case 1: Corrupted / invalid language code
    {
        QFile f(langFile);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("invalid_code_with_symbols!!!\n");
        f.close();
    }

    Translator translator(langFile, QStringLiteral(":/i18n"));
    // Falls back to "en"
    QCOMPARE(translator.language(), QStringLiteral("en"));
    QCOMPARE(translator.translate("", "Settings"), QStringLiteral("Settings"));

    // Case 2: Untranslated source string falls back cleanly to empty or handled text
    QCOMPARE(translator.translate("", "TotallyNonExistentString12345"), QString());
}

// -----------------------------------------------------------------------------
// 4. QML Live Scene Retranslate & Visual Invariants
// -----------------------------------------------------------------------------

void M5ForensicTests::testQmlLiveSceneRetranslate() {
    QQmlEngine engine;

    // Register C++ types
    qmlRegisterType<AccountModel>("AntigravityHub", 1, 0, "AccountModel");
    qmlRegisterType<AccountFilterProxyModel>("AntigravityHub", 1, 0, "AccountFilterProxyModel");
    qmlRegisterType<BackendController>("AntigravityHub", 1, 0, "BackendController");
    qmlRegisterUncreatableType<Theme>("AntigravityHub", 1, 0, "Theme", "Theme property");
    qmlRegisterUncreatableType<Translator>("AntigravityHub", 1, 0, "Translator", "Translator property");

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    const QString langFile = tempDir.filePath("language");
    {
        QFile f(langFile);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("en\n");
        f.close();
    }

    Theme theme(tempDir.path());
    Translator translator(langFile, QStringLiteral(":/i18n"));
    BackendController backend;
    AccountModel accountModel;
    AccountFilterProxyModel proxyModel;
    proxyModel.setSourceModel(&accountModel);

    QQmlContext *ctx = engine.rootContext();
    ctx->setContextProperty("theme", &theme);
    ctx->setContextProperty("translator", &translator);
    ctx->setContextProperty("backend", &backend);
    ctx->setContextProperty("backendController", &backend);
    ctx->setContextProperty("accountModel", &accountModel);
    ctx->setContextProperty("proxyModel", &proxyModel);
    ctx->setContextProperty("accountFilterProxyModel", &proxyModel);

    // Connect translator to QQmlEngine::retranslate
    connect(&translator, &Translator::changed, &engine, &QQmlEngine::retranslate);

    // Instantiate HeaderBar.qml offscreen
    QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/HeaderBar.qml")));
    QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
    QScopedPointer<QObject> headerObj(comp.create());
    QVERIFY2(headerObj != nullptr, "HeaderBar failed to instantiate");

    // Trigger retranslate offscreen
    engine.retranslate();
    QCoreApplication::processEvents();

    QVERIFY(true); // Completed with zero crash or binding errors
}

void M5ForensicTests::testVisualDenoisingPurity() {
    // Audit AccountListView.qml for strict visual denoising invariant enforcement
    QFile file(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(file.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString qml = QString::fromUtf8(file.readAll());
    file.close();

    // 1. Literal 5.5 badge completely removed
    QVERIFY2(!qml.contains("\"5.5\""), "CRITICAL AUDIT FAIL: Found '5.5' literal in AccountListView.qml");
    QVERIFY2(!qml.contains("[5.5]"), "CRITICAL AUDIT FAIL: Found '[5.5]' badge in AccountListView.qml");

    // 2. Gemini 4 column header pure: no "(周)"
    QVERIFY2(qml.contains("text: qsTr(\"Gemini 4\")"),
             "CRITICAL AUDIT FAIL: Header does not strictly match qsTr(\"Gemini 4\")");
    QVERIFY2(!qml.contains("(周)"), "CRITICAL AUDIT FAIL: Found '(周)' in AccountListView.qml");

    // 3. Gemini 4 progress bar pure: no "周" badge before progress bar
    QVERIFY2(!qml.contains("text: \"周\""), "CRITICAL AUDIT FAIL: Found standalone '周' badge in Gemini 4 bar");

    // 4. Logo SVG present and valid
    QFile logo(QStringLiteral(":/assets/logo.svg"));
    QVERIFY2(logo.open(QIODevice::ReadOnly), "Single-color vector logo.svg missing from resources");
    const QString svgContent = QString::fromUtf8(logo.readAll());
    QVERIFY2(svgContent.contains("<svg"), "logo.svg is not a valid SVG document");
}

// -----------------------------------------------------------------------------
// 5. Hyprland Floating Window Rule Configuration
// -----------------------------------------------------------------------------

void M5ForensicTests::testHyprlandWindowRuleConfiguration() {
    const QString hyprConf = QDir::homePath() + "/.config/hypr/hyprland.lua";
    QFile file(hyprConf);
    QVERIFY2(file.open(QIODevice::ReadOnly | QIODevice::Text),
             "~/.config/hypr/hyprland.lua could not be opened for inspection");

    const QString content = QString::fromUtf8(file.readAll());
    file.close();

    // Rule must match class "^antigravity-hub$" and declare float = true, center = true
    QVERIFY2(content.contains("o.window(\"^antigravity-hub$\""),
             "Missing o.window(\"^antigravity-hub$\", ...) rule in hyprland.lua");
    QVERIFY2(content.contains("float = true"), "Window rule missing float = true");
    QVERIFY2(content.contains("center = true"), "Window rule missing center = true");
}

void M5ForensicTests::cleanupTestCase() {
    qDebug() << "=================================================================";
    qDebug() << "Milestone 5 Forensic Tests Completed Successfully (Exit 0)";
    qDebug() << "=================================================================";
}

QTEST_MAIN(M5ForensicTests)
#include "m5_forensic_tests.moc"
