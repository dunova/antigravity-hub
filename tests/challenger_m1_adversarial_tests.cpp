#include <QtTest>
#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTemporaryFile>
#include <QQmlEngine>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQuickItem>
#include <QMetaObject>
#include <QMetaProperty>
#include <QDateTime>
#include <cstdio>
#include <unistd.h>

#include "theme.h"

class ChallengerM1AdversarialTests : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // Mission Test 1: Tri-State Theme Mode Switching (auto -> dark -> light -> auto) & Signals
    void testTriStateModeSwitchingAndSignals();

    // Mission Test 2: Rapid Theme Mode Stress & Fuzzing
    void testRapidTriStateFuzzingAndStress();

    // Mission Test 3: Inotify Dynamic Reloading & Atomic File Replacement in /tmp
    void testInotifyAtomicFileReplacementInTmp();

    // Mission Test 4: Inotify Rapid Burst & Debounce Coalescing
    void testInotifyBurstAndDebounceCoalescing();

    // Mission Test 5: Malformed & Pathological colors.toml Robustness
    void testMalformedAndEdgeCaseColorsToml();

    // Mission Test 6: QML Property Readability & Dynamic NOTIFY Bindings (rowEven, rowOdd, trackBg, pillBg)
    void testQmlPropertyReadabilityAndDynamicBinding();

    // Mission Test 7: Canonical Color Engine Oracles & Mathematical Extremes
    void testColorAlgorithmOraclesAndExtremes();

    // Mission Test 8: Memory Safety & Lifecycle Under Offscreen Platform
    void testMemorySafetyAndLifecycleStress();

    // Critical Defect Reproduction: Forced Dark Mode on Light Themes
    void testForcedDarkModeOnLightThemesDefect();

    void cleanupTestCase();
};

void ChallengerM1AdversarialTests::initTestCase() {
    qDebug() << "==========================================================";
    qDebug() << "Challenger 2: Antigravity Hub Milestone 1 Adversarial Suite";
    qDebug() << "Platform:" << qgetenv("QT_QPA_PLATFORM");
    qDebug() << "==========================================================";
    QVERIFY(!qgetenv("QT_QPA_PLATFORM").isEmpty());
}

// -----------------------------------------------------------------------------
// Test 1: Tri-State Theme Mode Switching & Signal Integrity
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testTriStateModeSwitchingAndSignals() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Setup base dark palette (Jade Horse)
    QDir(tempDir.path()).mkpath("theme");
    QFile colorsFile(tempDir.filePath("theme/colors.toml"));
    QVERIFY(colorsFile.open(QIODevice::WriteOnly | QIODevice::Text));
    colorsFile.write(
        "mode = \"dark\"\n"
        "accent = \"#8bcbb1\"\n"
        "selection = \"#2b5147\"\n"
        "muted = \"#64887b\"\n"
        "background = \"#142620\"\n"
        "dark_background = \"#0f1e19\"\n"
        "darker_background = \"#0a1713\"\n"
        "lighter_background = \"#203b31\"\n"
        "foreground = \"#dfede5\"\n"
        "bright_foreground = \"#f0faf4\"\n"
        "red = \"#d88d91\"\n"
        "yellow = \"#c5cc91\"\n"
        "green = \"#8bcbb1\"\n"
    );
    colorsFile.close();

    Theme theme(tempDir.path());
    QSignalSpy modeSpy(&theme, &Theme::themeModeChanged);
    QSignalSpy changeSpy(&theme, &Theme::changed);

    // Initial state: default is system/auto
    QCOMPARE(theme.themeMode(), QString("system"));
    QCOMPARE(theme.mode(), QString("dark"));
    const QString initialBg = theme.background();
    const QString initialRowEven = theme.rowEven();
    const QString initialRowOdd = theme.rowOdd();
    QCOMPARE(initialBg, QString("#142620"));

    // Step 1: Switch to "dark"
    theme.setThemeMode("dark");
    QCOMPARE(modeSpy.count(), 1);
    QCOMPARE(theme.themeMode(), QString("dark"));
    QCOMPARE(theme.mode(), QString("dark"));
    // Even if mode stays dark, tokens were re-evaluated
    QCOMPARE(theme.background(), initialBg);
    QCOMPARE(theme.rowEven(), initialRowEven);

    // Redundant switch to "dark": should NOT re-emit themeModeChanged
    theme.setThemeMode("dark");
    QCOMPARE(modeSpy.count(), 1);

    // Step 2: Switch to "light"
    theme.setThemeMode("light");
    QCOMPARE(modeSpy.count(), 2);
    QVERIFY(changeSpy.count() >= 1);
    QCOMPARE(theme.themeMode(), QString("light"));
    QCOMPARE(theme.mode(), QString("light"));
    QCOMPARE(theme.background(), QString("#FFFFFF"));
    QCOMPARE(theme.text1(), QString("#0F172A"));
    QCOMPARE(theme.rowEven(), QString("#FFFFFF"));
    QVERIFY(theme.rowOdd() != QString("#000000"));
    QVERIFY(theme.rowOdd() != theme.rowEven());

    // Step 3: Switch to "auto"
    theme.setThemeMode("auto");
    QCOMPARE(modeSpy.count(), 3);
    QCOMPARE(theme.themeMode(), QString("auto"));
    // Since colors.toml mode is "dark", auto resolves back to dark
    QCOMPARE(theme.mode(), QString("dark"));
    QCOMPARE(theme.background(), QString("#142620"));
    QCOMPARE(theme.text1(), QString("#FFFFFF"));
    QCOMPARE(theme.rowEven(), initialRowEven);
    QCOMPARE(theme.rowOdd(), initialRowOdd);

    // Step 4: Now update colors.toml to mode = "light" (Catppuccin Latte style)
    QFile colorsFile2(tempDir.filePath("theme/colors.toml"));
    QVERIFY(colorsFile2.open(QIODevice::WriteOnly | QIODevice::Text));
    colorsFile2.write(
        "mode = \"light\"\n"
        "accent = \"#1e66f5\"\n"
        "background = \"#eff1f5\"\n"
        "dark_background = \"#e3e4e8\"\n"
        "darker_background = \"#d7d8dc\"\n"
        "lighter_background = \"#dce0e8\"\n"
        "foreground = \"#4c4f69\"\n"
        "bright_foreground = \"#4c4f69\"\n"
        "red = \"#d20f39\"\n"
        "yellow = \"#df8e1d\"\n"
        "green = \"#40a02b\"\n"
    );
    colorsFile2.close();

    // Trigger reload via inotify or manual cycle
    QTRY_COMPARE_WITH_TIMEOUT(theme.mode(), QString("light"), 3000);
    QCOMPARE(theme.background(), QString("#eff1f5"));
    QCOMPARE(theme.accent(), QString("#1e66f5"));
}

// -----------------------------------------------------------------------------
// Test 2: Rapid Theme Mode Stress & Fuzzing
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testRapidTriStateFuzzingAndStress() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    Theme theme(tempDir.path());

    // 1. Stress: 3,000 rapid toggles between auto, dark, light
    const QStringList modes = {"auto", "dark", "light", "system", "dark", "light"};
    for (int i = 0; i < 3000; ++i) {
        theme.setThemeMode(modes[i % modes.size()]);
    }
    QVERIFY(theme.mode() == "dark" || theme.mode() == "light");

    // 2. Fuzzing with unexpected strings: empty, whitespace, unknown, case variations
    const QStringList fuzzInputs = {
        "", "   ", "UNKNOWN", "DARK", "Light", "system", "auto",
        "null", "undefined", "12345", "!@#$%", QString(1024, 'A')
    };

    for (const auto &input : fuzzInputs) {
        theme.setThemeMode(input);
        // Effective mode must remain strictly either "dark" or "light"
        QVERIFY(theme.mode() == "dark" || theme.mode() == "light");
        // Row zebra striping must never be pure black #000000
        QVERIFY(theme.rowEven() != QString("#000000"));
        QVERIFY(theme.rowOdd() != QString("#000000"));
        QVERIFY(theme.rowEven() != theme.rowOdd());
        // Track and pill bg must remain valid #AARRGGBB hex
        QVERIFY(theme.trackBg().startsWith("#"));
        QVERIFY(theme.pillBg().startsWith("#"));
        QVERIFY(!theme.trackBg().contains("rgba"));
        QVERIFY(!theme.pillBg().contains("rgba"));
    }
}

// -----------------------------------------------------------------------------
// Test 3: Inotify Dynamic Reloading & Atomic File Replacement in /tmp
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testInotifyAtomicFileReplacementInTmp() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString themeDir = tempDir.filePath("theme");
    QDir(tempDir.path()).mkpath("theme");
    const QString targetColors = tempDir.filePath("theme/colors.toml");

    // Initial state: Tokyo Night dark
    {
        QFile f(targetColors);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "mode = \"dark\"\n"
            "accent = \"#7aa2f7\"\n"
            "background = \"#1a1b26\"\n"
            "dark_background = \"#16161e\"\n"
            "darker_background = \"#13141c\"\n"
            "lighter_background = \"#24283b\"\n"
            "foreground = \"#c0caf5\"\n"
            "bright_foreground = \"#ffffff\"\n"
            "red = \"#f7768e\"\n"
            "yellow = \"#e0af68\"\n"
            "green = \"#9ece6a\"\n"
        );
        f.close();
    }

    Theme theme(tempDir.path());
    QCOMPARE(theme.accent(), QString("#7aa2f7"));
    QCOMPARE(theme.background(), QString("#1a1b26"));

    QSignalSpy spy(&theme, &Theme::changed);

    // Simulate atomic swap: write to a temporary file in /tmp, then rename over target
    QString tmpPath;
    {
        QTemporaryFile tmpFile(QDir::tempPath() + "/antigravity_atomic_XXXXXX.toml");
        tmpFile.setAutoRemove(false);
        QVERIFY(tmpFile.open());
        tmpFile.write(
            "mode = \"dark\"\n"
            "accent = \"#d65d0e\"\n" // Gruvbox orange
            "background = \"#282828\"\n"
            "dark_background = \"#1d2021\"\n"
            "darker_background = \"#141617\"\n"
            "lighter_background = \"#3c3836\"\n"
            "foreground = \"#ebdbb2\"\n"
            "bright_foreground = \"#fbf1c7\"\n"
            "red = \"#cc241d\"\n"
            "yellow = \"#d79921\"\n"
            "green = \"#98971a\"\n"
        );
        tmpPath = tmpFile.fileName();
        tmpFile.close();
    }

    // POSIX rename across or within filesystems (using QFile::rename or POSIX ::rename)
    // Note: If /tmp is a different mount point (e.g. tmpfs) from /mnt/nas, cross-device rename
    // is simulated by copying to tempDir first, then renaming atomically within the same directory.
    const QString atomicStaging = tempDir.filePath("theme/colors.toml.tmp");
    QVERIFY(QFile::copy(tmpPath, atomicStaging));
    QFile::remove(tmpPath);

    // Atomic replacement step using POSIX rename (atomic overwrite)
    QVERIFY(::rename(atomicStaging.toUtf8().constData(), targetColors.toUtf8().constData()) == 0);

    // Theme watcher should detect change, debounce for 80ms, and reload
    QTRY_COMPARE_WITH_TIMEOUT(theme.accent(), QString("#d65d0e"), 3000);
    QCOMPARE(theme.background(), QString("#282828"));
    QVERIFY(spy.count() >= 1);
}

// -----------------------------------------------------------------------------
// Test 4: Inotify Rapid Burst & Debounce Coalescing
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testInotifyBurstAndDebounceCoalescing() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    QDir(tempDir.path()).mkpath("theme");
    const QString targetColors = tempDir.filePath("theme/colors.toml");

    Theme theme(tempDir.path());
    QSignalSpy spy(&theme, &Theme::changed);

    // Perform 10 rapid atomic writes within 20ms
    QString finalAccent;
    for (int i = 0; i < 10; ++i) {
        finalAccent = QString("#%1%1%1%1%1%1").arg(i, 1, 16);
        const QString staging = tempDir.filePath(QString("theme/colors_tmp_%1.toml").arg(i));
        QFile f(staging);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(QString("mode = \"dark\"\naccent = \"%1\"\nbackground = \"#101010\"\n").arg(finalAccent).toUtf8());
        f.close();
        QVERIFY(::rename(staging.toUtf8().constData(), targetColors.toUtf8().constData()) == 0);
        usleep(2000); // 2ms gap, far below 80ms debounce
    }

    // Wait for the single coalesced reload to settle
    QTRY_COMPARE_WITH_TIMEOUT(theme.accent(), finalAccent, 3000);
    // Debounce should coalesce the burst into very few signal emissions (typically 1 or 2)
    qDebug() << "Burst of 10 writes generated" << spy.count() << "changed() emissions.";
    QVERIFY(spy.count() <= 5);
}

// -----------------------------------------------------------------------------
// Test 5: Malformed & Pathological colors.toml Robustness
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testMalformedAndEdgeCaseColorsToml() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    QDir(tempDir.path()).mkpath("theme");
    const QString targetColors = tempDir.filePath("theme/colors.toml");

    Theme theme(tempDir.path());

    // Scenario A: Completely empty file
    {
        QFile f(targetColors);
        QVERIFY(f.open(QIODevice::WriteOnly));
        f.close();
    }
    const auto emptyRes = Theme::readColors(targetColors);
    QVERIFY(emptyRes.isEmpty());

    // Scenario B: Corrupted binary junk
    {
        QFile f(targetColors);
        QVERIFY(f.open(QIODevice::WriteOnly));
        QByteArray garbage("\x00\xFF\xFE\x00\xDE\xAD\xBE\xEF\x00\x00\x01\x02\x03\x04", 14);
        f.write(garbage);
        f.close();
    }
    const auto garbageRes = Theme::readColors(targetColors);
    QVERIFY(garbageRes.isEmpty()); // Regex safely rejects non-matching binary

    // Scenario C: Pathological 10,000 line file with thousands of comments and whitespace
    {
        QFile f(targetColors);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        for (int i = 0; i < 5000; ++i) {
            f.write("# This is a long comment line testing regex backtrack safety\n");
            f.write("   \t  \n");
        }
        f.write("accent = \"#abcdef\"\n");
        f.write("mode = \"dark\"\n");
        for (int i = 0; i < 5000; ++i) {
            f.write("# trailing comments\n");
        }
        f.close();
    }
    const auto largeRes = Theme::readColors(targetColors);
    QCOMPARE(largeRes.value("accent"), QString("#abcdef"));
    QCOMPARE(largeRes.value("mode"), QString("dark"));

    // Scenario D: File unlinking / deletion while running
    QVERIFY(QFile::remove(targetColors));
    // Calling readColors on non-existent file must not crash
    const auto missingRes = Theme::readColors(targetColors);
    QVERIFY(missingRes.isEmpty());
}

// -----------------------------------------------------------------------------
// Test 6: QML Property Readability & Dynamic Binding (rowEven, rowOdd, trackBg, pillBg)
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testQmlPropertyReadabilityAndDynamicBinding() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    Theme theme(tempDir.path());

    // 1. QMetaObject Inspection
    const QMetaObject *meta = theme.metaObject();
    QVERIFY(meta != nullptr);

    const char *targetProps[] = {"rowEven", "rowOdd", "trackBg", "pillBg"};
    for (const char *name : targetProps) {
        int idx = meta->indexOfProperty(name);
        QVERIFY2(idx >= 0, qPrintable(QString("Missing Q_PROPERTY: %1").arg(name)));
        QMetaProperty prop = meta->property(idx);
        QVERIFY2(prop.isValid(), qPrintable(QString("Property invalid: %1").arg(name)));
        QVERIFY2(prop.isReadable(), qPrintable(QString("Property not readable: %1").arg(name)));
        QVERIFY2(prop.hasNotifySignal(), qPrintable(QString("Property lacks NOTIFY: %1").arg(name)));

        QMetaMethod notifySignal = prop.notifySignal();
        QCOMPARE(QString(notifySignal.name()), QString("changed"));
    }

    // 2. QML Dynamic Evaluation & Type Parsing via QQmlEngine
    QQmlEngine engine;
    engine.rootContext()->setContextProperty("theme", &theme);

    const QString qmlCode =
        "import QtQuick 2.15\n"
        "QtObject {\n"
        "    property string rowEvenStr: theme.rowEven\n"
        "    property string rowOddStr: theme.rowOdd\n"
        "    property string trackBgStr: theme.trackBg\n"
        "    property string pillBgStr: theme.pillBg\n"
        "    property color rowEvenColor: theme.rowEven\n"
        "    property color rowOddColor: theme.rowOdd\n"
        "    property color trackBgColor: theme.trackBg\n"
        "    property color pillBgColor: theme.pillBg\n"
        "}\n";

    QQmlComponent component(&engine);
    component.setData(qmlCode.toUtf8(), QUrl());
    QVERIFY2(component.isReady(), qPrintable(component.errorString()));

    QObject *obj = component.create();
    QVERIFY(obj != nullptr);

    // Verify string equality with C++ getters
    QCOMPARE(obj->property("rowEvenStr").toString(), theme.rowEven());
    QCOMPARE(obj->property("rowOddStr").toString(), theme.rowOdd());
    QCOMPARE(obj->property("trackBgStr").toString(), theme.trackBg());
    QCOMPARE(obj->property("pillBgStr").toString(), theme.pillBg());

    // Verify QML successfully parsed them into valid QColors (NO "#000000" fallback from invalid CSS)
    const QColor cRowEven = obj->property("rowEvenColor").value<QColor>();
    const QColor cRowOdd = obj->property("rowOddColor").value<QColor>();
    const QColor cTrackBg = obj->property("trackBgColor").value<QColor>();
    const QColor cPillBg = obj->property("pillBgColor").value<QColor>();

    QVERIFY(cRowEven.isValid());
    QVERIFY(cRowOdd.isValid());
    QVERIFY(cTrackBg.isValid());
    QVERIFY(cPillBg.isValid());

    // Verify zebra striping invariants
    QVERIFY(cRowEven != cRowOdd);
    QVERIFY(cRowEven != QColor("#000000"));
    QVERIFY(cRowOdd != QColor("#000000"));

    // Verify dynamic reactive binding: toggle theme mode to "light" and verify QML properties auto-updated
    theme.setThemeMode("light");
    QCOMPARE(obj->property("rowEvenStr").toString(), theme.rowEven());
    QCOMPARE(obj->property("rowOddStr").toString(), theme.rowOdd());
    QCOMPARE(obj->property("rowEvenStr").toString(), QString("#FFFFFF"));

    // Toggle back to "dark"
    theme.setThemeMode("dark");
    QCOMPARE(obj->property("rowEvenStr").toString(), theme.rowEven());
    QCOMPARE(obj->property("rowOddStr").toString(), theme.rowOdd());

    delete obj;
}

// -----------------------------------------------------------------------------
// Test 7: Canonical Color Engine Oracles & Mathematical Extremes
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testColorAlgorithmOraclesAndExtremes() {
    // 1. Contrast mathematical bounds
    // Maximum: White vs Black -> 21.0
    const double maxRatio = Theme::contrast("#ffffff", "#000000");
    QVERIFY(qAbs(maxRatio - 21.0) < 0.05);

    // Minimum: Same color -> 1.0
    const double minRatio = Theme::contrast("#8bcbb1", "#8bcbb1");
    QCOMPARE(minRatio, 1.0);

    // Symmetry oracle: contrast(a, b) == contrast(b, a)
    const QStringList sampleColors = {"#123456", "#abcdef", "#ff5500", "#00ff77", "#808080", "#142620"};
    for (int i = 0; i < sampleColors.size(); ++i) {
        for (int j = i; j < sampleColors.size(); ++j) {
            double c1 = Theme::contrast(sampleColors[i], sampleColors[j]);
            double c2 = Theme::contrast(sampleColors[j], sampleColors[i]);
            QVERIFY(qAbs(c1 - c2) < 0.0001);
            QVERIFY(c1 >= 1.0 && c1 <= 21.0);
        }
    }

    // Invalid color inputs must return 1.0 gracefully without crashing
    QCOMPARE(Theme::contrast("", "#ffffff"), 1.0);
    QCOMPARE(Theme::contrast("invalid", "#ffffff"), 1.0);
    QCOMPARE(Theme::contrast("#123456", "invalid"), 1.0);

    // 2. Mix mathematical bounds
    QCOMPARE(Theme::mix("#000000", "#ffffff", 0.0), QString("#000000"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", 1.0), QString("#ffffff"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", -5.0), QString("#000000")); // Clamped to 0.0
    QCOMPARE(Theme::mix("#000000", "#ffffff", 10.0), QString("#ffffff")); // Clamped to 1.0
    // Midpoint
    QCOMPARE(Theme::mix("#000000", "#ffffff", 0.5), QString("#808080"));

    // 3. withAlpha formatting and hex accuracy
    QCOMPARE(Theme::withAlpha("#ffffff", 0.0), QString("#00ffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 1.0), QString("#ffffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.5), QString("#80ffffff"));
    QCOMPARE(Theme::withAlpha("#123456", -1.0), QString("#00123456"));
    QCOMPARE(Theme::withAlpha("#123456", 2.0), QString("#ff123456"));

    // 4. readable() WCAG 4.5:1 adaptation guarantee
    // Ensure that low-contrast colors are boosted to >= 4.5 contrast against dark surfaces
    const QString darkSurface = "#142620";
    const QString lowContrastRed = "#1a2c26"; // Almost invisible against #142620
    const QString adapted = Theme::readable(lowContrastRed, "#ffffff", {darkSurface}, 4.5);
    const double adaptedContrast = Theme::contrast(adapted, darkSurface);
    QVERIFY2(adaptedContrast >= 4.5, qPrintable(QString("Contrast %1 < 4.5").arg(adaptedContrast)));
    // Must NOT fall back to hardcoded pure red #FF6B6B
    QVERIFY(adapted != QString("#FF6B6B"));
}

// -----------------------------------------------------------------------------
// Test 8: Memory Safety & Lifecycle Under Offscreen Platform
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testMemorySafetyAndLifecycleStress() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Rapidly instantiate and delete 100 Theme instances to verify clean destruction of QProcess, QFileSystemWatcher, QTimer
    for (int i = 0; i < 100; ++i) {
        Theme *t = new Theme(tempDir.path());
        QVERIFY(t->accent().startsWith("#"));
        delete t;
    }

    // Verify signal re-entrancy safety: calling methods inside signal slot
    Theme theme(tempDir.path());
    int invocations = 0;
    connect(&theme, &Theme::changed, &theme, [&]() {
        invocations++;
        // Query properties while in changed() signal
        Q_UNUSED(theme.rowEven());
        Q_UNUSED(theme.rowOdd());
        Q_UNUSED(theme.trackBg());
        Q_UNUSED(theme.pillBg());
    });

    theme.setThemeMode("light");
    theme.setThemeMode("dark");
    QVERIFY(invocations >= 2);
}

// -----------------------------------------------------------------------------
// Critical Defect Reproduction: Forced Dark Mode on Light Themes
// -----------------------------------------------------------------------------
void ChallengerM1AdversarialTests::testForcedDarkModeOnLightThemesDefect() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Setup an official light theme (e.g. 'white')
    QDir(tempDir.path()).mkpath("theme");
    QFile colorsFile(tempDir.filePath("theme/colors.toml"));
    QVERIFY(colorsFile.open(QIODevice::WriteOnly | QIODevice::Text));
    colorsFile.write(
        "mode = \"light\"\n"
        "accent = \"#6e6e6e\"\n"
        "background = \"#ffffff\"\n"
        "dark_background = \"#f5f5f5\"\n"
        "darker_background = \"#e8e8e8\"\n"
        "lighter_background = \"#c0c0c0\"\n"
        "foreground = \"#000000\"\n"
        "bright_foreground = \"#000000\"\n"
    );
    colorsFile.close();

    Theme theme(tempDir.path());
    QCOMPARE(theme.mode(), QString("light"));
    QCOMPARE(theme.background(), QString("#ffffff"));

    // User forces "dark" mode in SettingsDialog
    theme.setThemeMode("dark");

    // Empirical Observation:
    const QString bg = theme.background();
    const QString text1 = theme.text1();
    const double contrastRatio = Theme::contrast(text1, bg);

    qDebug() << "==========================================================";
    qDebug() << "[CRITICAL DEFECT] Forced Dark Mode on System Light Theme:";
    qDebug() << "  background:" << bg;
    qDebug() << "  text1:" << text1;
    qDebug() << "  contrast ratio:" << contrastRatio << ": 1 (WCAG Minimum: 4.5:1)";
    qDebug() << "  rowEven:" << theme.rowEven();
    qDebug() << "==========================================================";

    // In a dark mode, text1 (#FFFFFF) on background (#ffffff) is pure white on pure white!
    // This is an empirical defect: contrast is 1.0:1 (completely unreadable).
    QVERIFY2(contrastRatio >= 4.5,
             qPrintable(QString("CRITICAL DEFECT: White text on white background in forced dark mode! Contrast: %1:1").arg(contrastRatio)));
}

void ChallengerM1AdversarialTests::cleanupTestCase() {
    qDebug() << "Challenger 2 adversarial test suite completed successfully.";
}

QTEST_MAIN(ChallengerM1AdversarialTests)
#include "challenger_m1_adversarial_tests.moc"
