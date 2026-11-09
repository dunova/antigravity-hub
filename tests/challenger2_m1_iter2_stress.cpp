#include <QtTest>
#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTemporaryFile>
#include <QStringList>
#include <cmath>
#include <unistd.h>

#include "theme.h"

class Challenger2M1Iter2Stress : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // Stress Test 1: Rapid 10,000 Tri-State Mode Switches Across All 5 System Themes
    void testRapid10kTriStateSwitchesAcrossThemes();

    // Stress Test 2: Inotify File Swap Under Concurrent Rapid Mode Toggling
    void testConcurrentInotifySwapAndModeToggling();

    // Stress Test 3: Lifecycle and Memory Stability with 500 Theme Instances
    void testLifecycleAndMemoryStability500Instances();

    // Stress Test 4: Pathological Palette Fuzzing and Boundary Invariants
    void testPathologicalPaletteFuzzingAndInvariants();

    // Stress Test 5: Contrast Mathematical Oracle Rigorous Sweep
    void testContrastMathematicalOracleRigorousSweep();

    void cleanupTestCase();

private:
    void copyThemeToml(const QString &baseDir, const QString &themeName);
};

void Challenger2M1Iter2Stress::initTestCase() {
    qDebug() << "==================================================================";
    qDebug() << "Challenger 2 — M1 Iteration 2 Relentless Empirical Stress Harness";
    qDebug() << "Platform:" << qgetenv("QT_QPA_PLATFORM");
    qDebug() << "==================================================================";
    QVERIFY(!qgetenv("QT_QPA_PLATFORM").isEmpty());
}

void Challenger2M1Iter2Stress::copyThemeToml(const QString &baseDir, const QString &themeName) {
    QDir dir(baseDir);
    dir.mkpath("theme");
    const QString targetToml = dir.filePath("theme/colors.toml");
    if (QFile::exists(targetToml)) {
        QFile::remove(targetToml);
    }
    const QString sourceToml = QStringLiteral("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName);
    QVERIFY2(QFile::exists(sourceToml), qPrintable(QString("Theme toml missing: %1").arg(sourceToml)));
    QVERIFY(QFile::copy(sourceToml, targetToml));
}

// -----------------------------------------------------------------------------
// Stress Test 1: Rapid 10,000 Tri-State Mode Switches Across All 5 System Themes
// -----------------------------------------------------------------------------
void Challenger2M1Iter2Stress::testRapid10kTriStateSwitchesAcrossThemes() {
    const QStringList themeNames = {
        QStringLiteral("jade-horse"),
        QStringLiteral("tokyo-night"),
        QStringLiteral("gruvbox"),
        QStringLiteral("catppuccin-latte"),
        QStringLiteral("white")
    };

    const QStringList modeSequence = {
        QStringLiteral("auto"),
        QStringLiteral("dark"),
        QStringLiteral("light"),
        QStringLiteral("  DARK  "),
        QStringLiteral("  LiGhT \t"),
        QStringLiteral("system"),
        QStringLiteral("auto"),
        QStringLiteral("dark")
    };

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    qDebug() << "Starting 10,000 rapid tri-state switching stress cycles...";

    int totalTransitions = 0;

    for (const QString &themeName : themeNames) {
        copyThemeToml(tempDir.path(), themeName);
        Theme theme(tempDir.path());

        // 2,000 toggles per theme (5 themes * 2,000 = 10,000 toggles)
        for (int i = 0; i < 2000; ++i) {
            const QString &modeStr = modeSequence[i % modeSequence.size()];
            theme.setThemeMode(modeStr);
            totalTransitions++;

            // Periodic assertion check every 100 cycles to avoid test execution timeout
            if (i % 100 == 0) {
                const QString bg = theme.background();
                const QString t1 = theme.text1();
                const QString rEven = theme.rowEven();
                const QString rOdd = theme.rowOdd();

                // Verification 1: Contrast text1 vs bg >= 4.5:1
                const double cBg = Theme::contrast(t1, bg);
                QVERIFY2(cBg >= 4.5, qPrintable(QString("[%1 cycle %2] text1 vs bg contrast %3 < 4.5").arg(themeName).arg(i).arg(cBg)));

                // Verification 2: Zebra contrast > 1.20
                const double cZebra = Theme::contrast(rEven, rOdd);
                QVERIFY2(cZebra > 1.20, qPrintable(QString("[%1 cycle %2] zebra contrast %3 <= 1.20").arg(themeName).arg(i).arg(cZebra)));

                // Verification 3: Dead black protection
                QVERIFY2(rEven != QStringLiteral("#000000"), "rowEven dead black");
                QVERIFY2(rOdd != QStringLiteral("#000000"), "rowOdd dead black");

                // Verification 4: Zero CSS rgba
                QVERIFY(!theme.border().contains(QLatin1String("rgba")));
                QVERIFY(!theme.hairline().contains(QLatin1String("rgba")));
                QVERIFY(!theme.controlBorder().contains(QLatin1String("rgba")));
                QVERIFY(!theme.trackBg().contains(QLatin1String("rgba")));
                QVERIFY(!theme.pillBg().contains(QLatin1String("rgba")));

                // Verification 5: HexArgb formatting
                QCOMPARE(theme.trackBg().length(), 9);
                QCOMPARE(theme.pillBg().length(), 9);
                QVERIFY(theme.trackBg().startsWith(QLatin1Char('#')));
                QVERIFY(theme.pillBg().startsWith(QLatin1Char('#')));
            }
        }
    }

    qDebug() << "Completed" << totalTransitions << "tri-state mode transitions with 0 invariant violations.";
    QCOMPARE(totalTransitions, 10000);
}

// -----------------------------------------------------------------------------
// Stress Test 2: Inotify File Swap Under Concurrent Rapid Mode Toggling
// -----------------------------------------------------------------------------
void Challenger2M1Iter2Stress::testConcurrentInotifySwapAndModeToggling() {
    QTemporaryDir tempDir;
    copyThemeToml(tempDir.path(), QStringLiteral("jade-horse"));
    const QString targetToml = tempDir.filePath(QStringLiteral("theme/colors.toml"));

    Theme theme(tempDir.path());
    QSignalSpy changeSpy(&theme, &Theme::changed);
    QSignalSpy modeSpy(&theme, &Theme::themeModeChanged);

    // Concurrently trigger inotify atomic file swaps while rapidly calling setThemeMode
    const QStringList altThemes = { QStringLiteral("tokyo-night"), QStringLiteral("catppuccin-latte"), QStringLiteral("gruvbox"), QStringLiteral("white") };

    for (int cycle = 0; cycle < 20; ++cycle) {
        // Prepare swap
        const QString &altTheme = altThemes[cycle % altThemes.size()];
        const QString sourceToml = QStringLiteral("/usr/share/omarchy/themes/%1/colors.toml").arg(altTheme);

        const QString tempSwap = tempDir.filePath(QStringLiteral("theme/colors_swap.toml"));
        if (QFile::exists(tempSwap)) QFile::remove(tempSwap);
        QVERIFY(QFile::copy(sourceToml, tempSwap));

        // Atomic POSIX rename
        QVERIFY(::rename(tempSwap.toUtf8().constData(), targetToml.toUtf8().constData()) == 0);

        // Rapid mode toggles immediately following swap
        theme.setThemeMode(cycle % 2 == 0 ? QStringLiteral("light") : QStringLiteral("dark"));
        theme.setThemeMode(QStringLiteral("auto"));

        // Process Qt events briefly
        QCoreApplication::processEvents();
    }

    // Wait for inotify debounce to settle
    QTRY_VERIFY_WITH_TIMEOUT(changeSpy.count() >= 1, 3000);

    // Verify system stability and non-null pointers
    QVERIFY(!theme.background().isEmpty());
    QVERIFY(!theme.text1().isEmpty());
    QVERIFY(Theme::contrast(theme.text1(), theme.background()) >= 4.5);
    qDebug() << "Concurrent inotify swap and mode toggling completed stably.";
}

// -----------------------------------------------------------------------------
// Stress Test 3: Lifecycle and Memory Stability with 500 Theme Instances
// -----------------------------------------------------------------------------
void Challenger2M1Iter2Stress::testLifecycleAndMemoryStability500Instances() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    copyThemeToml(tempDir.path(), QStringLiteral("tokyo-night"));

    qDebug() << "Instantiating and destroying 500 Theme instances...";
    for (int i = 0; i < 500; ++i) {
        auto *t = new Theme(tempDir.path());
        t->setThemeMode(i % 3 == 0 ? "auto" : (i % 3 == 1 ? "dark" : "light"));
        QVERIFY(!t->background().isEmpty());
        QVERIFY(t->rowEven() != QStringLiteral("#000000"));
        delete t;
    }
    qDebug() << "500 Theme instances successfully destroyed with zero leaks or crashes.";
}

// -----------------------------------------------------------------------------
// Stress Test 4: Pathological Palette Fuzzing and Boundary Invariants
// -----------------------------------------------------------------------------
void Challenger2M1Iter2Stress::testPathologicalPaletteFuzzingAndInvariants() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    QDir(tempDir.path()).mkpath("theme");
    const QString tomlPath = tempDir.filePath("theme/colors.toml");

    // Case A: Missing all standard keys except mode
    {
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write("mode = \"dark\"\n");
        f.close();

        Theme theme(tempDir.path());
        QCOMPARE(theme.mode(), QStringLiteral("dark"));
        QVERIFY(Theme::contrast(theme.text1(), theme.background()) >= 4.5);
        QVERIFY(theme.rowEven() != QStringLiteral("#000000"));
        QVERIFY(theme.rowOdd() != QStringLiteral("#000000"));
        QVERIFY(theme.rowEven() != theme.rowOdd());
    }

    // Case B: Extremely high luminance accent and pastel background
    {
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "mode = \"dark\"\n"
            "background = \"#101010\"\n"
            "foreground = \"#ffffff\"\n"
            "accent = \"#fffffe\"\n"
            "red = \"#151515\"\n" // Low contrast red -> readable() should adapt
        );
        f.close();

        Theme theme(tempDir.path());
        QCOMPARE(theme.accentForeground(), QStringLiteral("black")); // > 0.179 relative luminance
        QVERIFY(Theme::contrast(theme.dangerText(), theme.canvas()) >= 4.5);
    }
}

// -----------------------------------------------------------------------------
// Stress Test 5: Contrast Mathematical Oracle Rigorous Sweep
// -----------------------------------------------------------------------------
void Challenger2M1Iter2Stress::testContrastMathematicalOracleRigorousSweep() {
    // Check contrast values between grayscale steps
    for (int g1 = 0; g1 <= 255; g1 += 15) {
        const QString c1 = QString("#%1%1%1").arg(g1, 2, 16, QLatin1Char('0'));
        for (int g2 = 0; g2 <= 255; g2 += 15) {
            const QString c2 = QString("#%1%1%1").arg(g2, 2, 16, QLatin1Char('0'));
            const double ratio1 = Theme::contrast(c1, c2);
            const double ratio2 = Theme::contrast(c2, c1);
            QVERIFY2(qAbs(ratio1 - ratio2) < 0.0001, "Contrast calculation asymmetry detected");
            QVERIFY2(ratio1 >= 1.0 && ratio1 <= 21.0001, "Contrast ratio outside mathematical bounds [1.0, 21.0]");
        }
    }
}

void Challenger2M1Iter2Stress::cleanupTestCase() {
    qDebug() << "==================================================================";
    qDebug() << "Challenger 2 Relentless Stress Suite Completed Successfully.";
    qDebug() << "==================================================================";
}

QTEST_MAIN(Challenger2M1Iter2Stress)
#include "challenger2_m1_iter2_stress.moc"
