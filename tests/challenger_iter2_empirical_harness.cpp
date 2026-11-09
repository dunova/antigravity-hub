#include <QtTest>
#include <QColor>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QTemporaryDir>
#include <QStringList>
#include <cmath>

#include "theme.h"

class ChallengerIter2EmpiricalHarness : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // 1. Critical Contrast Check on Forced Dark Mode under catppuccin-latte and white
    void testForcedDarkModeOnLightThemesCatppuccinAndWhite();

    // 2. Empirically Verify Zebra Contrast > 1.20 across all 5 themes under all 3 modes
    void testZebraContrastAcross15MatrixConfigurations();

    // 3. Verify readColors regex resilience with unclosed quotes and adversarial syntax
    void testReadColorsRegexUnclosedQuotesAndAdversarial();

    // 4. Test readable() boundary and extreme fallbacks
    void testReadableBoundariesAndFallbacks();

    // 5. Test geometry and radius zero invariants under M1
    void testGeometryZeroRadiusInvariants();

    void cleanupTestCase();

private:
    QString copyThemeToml(const QString &baseDir, const QString &themeName);
};

void ChallengerIter2EmpiricalHarness::initTestCase() {
    qDebug() << "==================================================================";
    qDebug() << "Antigravity Hub — Challenger 1 M1 Iteration 2 Empirical Harness";
    qDebug() << "Platform:" << qgetenv("QT_QPA_PLATFORM");
    qDebug() << "==================================================================";
    QVERIFY(!qgetenv("QT_QPA_PLATFORM").isEmpty());
}

QString ChallengerIter2EmpiricalHarness::copyThemeToml(const QString &baseDir, const QString &themeName) {
    QDir dir(baseDir);
    dir.mkpath("theme");
    const QString targetToml = dir.filePath("theme/colors.toml");
    if (QFile::exists(targetToml)) {
        QFile::remove(targetToml);
    }
    const QString sourceToml = QStringLiteral("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName);
    if (!QFile::copy(sourceToml, targetToml)) {
        qWarning() << "Failed to copy" << sourceToml << "to" << targetToml;
    }
    return targetToml;
}

// -----------------------------------------------------------------------------
// 1. Critical Contrast Check on Forced Dark Mode under catppuccin-latte and white
// -----------------------------------------------------------------------------
void ChallengerIter2EmpiricalHarness::testForcedDarkModeOnLightThemesCatppuccinAndWhite() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QStringList lightThemes = { QStringLiteral("catppuccin-latte"), QStringLiteral("white") };

    for (const QString &themeName : lightThemes) {
        copyThemeToml(tempDir.path(), themeName);
        Theme theme(tempDir.path());

        // Baseline: Under system/auto mode, it detects as light
        QCOMPARE(theme.mode(), QStringLiteral("light"));
        const QString baselineBg = theme.background();
        qDebug() << "\n>>> Testing Theme:" << themeName;
        qDebug() << "    System mode baseline background:" << baselineBg;

        // Force Dark Mode
        theme.setThemeMode(QStringLiteral("dark"));
        QCOMPARE(theme.themeMode(), QStringLiteral("dark"));
        QCOMPARE(theme.mode(), QStringLiteral("dark"));

        const QString bg = theme.background();
        const QString text1 = theme.text1();
        const QString text2 = theme.text2();
        const QString canvas = theme.canvas();
        const QString surfaceTop = theme.surfaceTop();
        const QString surfaceBottom = theme.surfaceBottom();
        const QString surface1 = theme.surface1();
        const QString surface2 = theme.surface2();
        const QString surface3 = theme.surface3();
        const QString rEven = theme.rowEven();
        const QString rOdd = theme.rowOdd();

        // 1. Verify background is dark and not leaked light background
        QVERIFY2(bg != baselineBg, qPrintable(QString("[%1] Background remained light (%2)").arg(themeName, bg)));
        QCOMPARE(bg, QStringLiteral("#0e0e14"));
        QCOMPARE(text1, QStringLiteral("#FFFFFF"));

        // 2. Measure text1 contrast against all dark surfaces
        const double cText1Bg = Theme::contrast(text1, bg);
        const double cText1Canvas = Theme::contrast(text1, canvas);
        const double cText1SurfaceTop = Theme::contrast(text1, surfaceTop);
        const double cText1SurfaceBottom = Theme::contrast(text1, surfaceBottom);
        const double cText1Surface1 = Theme::contrast(text1, surface1);
        const double cText1Surface2 = Theme::contrast(text1, surface2);
        const double cText1Surface3 = Theme::contrast(text1, surface3);
        const double cText1Even = Theme::contrast(text1, rEven);
        const double cText1Odd = Theme::contrast(text1, rOdd);

        // 3. Measure text2 contrast against background
        const double cText2Bg = Theme::contrast(text2, bg);

        // 4. Measure semantic status colors
        const double cDanger = Theme::contrast(theme.dangerText(), canvas);
        const double cGood = Theme::contrast(theme.goodText(), canvas);
        const double cWarning = Theme::contrast(theme.warningText(), canvas);
        const double cAccent = Theme::contrast(theme.accentText(), canvas);

        qDebug() << "    [Forced Dark Mode Empirical Ratios -" << themeName << "]";
        qDebug() << "      text1 (" << text1 << ") vs background (" << bg << "):" << cText1Bg << ": 1";
        qDebug() << "      text1 vs canvas (" << canvas << "):" << cText1Canvas << ": 1";
        qDebug() << "      text1 vs surfaceTop (" << surfaceTop << "):" << cText1SurfaceTop << ": 1";
        qDebug() << "      text1 vs surfaceBottom (" << surfaceBottom << "):" << cText1SurfaceBottom << ": 1";
        qDebug() << "      text1 vs surface1 (" << surface1 << "):" << cText1Surface1 << ": 1";
        qDebug() << "      text1 vs surface2 (" << surface2 << "):" << cText1Surface2 << ": 1";
        qDebug() << "      text1 vs surface3 (" << surface3 << "):" << cText1Surface3 << ": 1";
        qDebug() << "      text1 vs rowEven (" << rEven << "):" << cText1Even << ": 1";
        qDebug() << "      text1 vs rowOdd (" << rOdd << "):" << cText1Odd << ": 1";
        qDebug() << "      text2 (" << text2 << ") vs background (" << bg << "):" << cText2Bg << ": 1";
        qDebug() << "      dangerText (" << theme.dangerText() << ") vs canvas:" << cDanger << ": 1";
        qDebug() << "      goodText (" << theme.goodText() << ") vs canvas:" << cGood << ": 1";
        qDebug() << "      warningText (" << theme.warningText() << ") vs canvas:" << cWarning << ": 1";
        qDebug() << "      accentText (" << theme.accentText() << ") vs canvas:" << cAccent << ": 1";

        // Verification Gates: Must be >= 4.5:1 (WCAG AA minimum for normal text)
        QVERIFY2(cText1Bg >= 4.5, qPrintable(QString("[%1] text1 vs bg contrast %2 < 4.5").arg(themeName).arg(cText1Bg)));
        QVERIFY2(cText1Bg >= 18.0, qPrintable(QString("[%1] text1 vs bg contrast %2 < 18.0 (expected ~19.2)").arg(themeName).arg(cText1Bg)));
        QVERIFY2(cText1Canvas >= 4.5, qPrintable(QString("[%1] text1 vs canvas contrast %2 < 4.5").arg(themeName).arg(cText1Canvas)));
        QVERIFY2(cText1SurfaceTop >= 4.5, qPrintable(QString("[%1] text1 vs surfaceTop contrast %2 < 4.5").arg(themeName).arg(cText1SurfaceTop)));
        QVERIFY2(cText1SurfaceBottom >= 4.5, qPrintable(QString("[%1] text1 vs surfaceBottom contrast %2 < 4.5").arg(themeName).arg(cText1SurfaceBottom)));
        QVERIFY2(cText1Surface1 >= 4.5, qPrintable(QString("[%1] text1 vs surface1 contrast %2 < 4.5").arg(themeName).arg(cText1Surface1)));
        QVERIFY2(cText1Even >= 4.5, qPrintable(QString("[%1] text1 vs rowEven contrast %2 < 4.5").arg(themeName).arg(cText1Even)));
        QVERIFY2(cText1Odd >= 4.5, qPrintable(QString("[%1] text1 vs rowOdd contrast %2 < 4.5").arg(themeName).arg(cText1Odd)));
        QVERIFY2(cText2Bg >= 4.5, qPrintable(QString("[%1] text2 vs bg contrast %2 < 4.5").arg(themeName).arg(cText2Bg)));
        QVERIFY2(cDanger >= 4.5, qPrintable(QString("[%1] dangerText contrast %2 < 4.5").arg(themeName).arg(cDanger)));
        QVERIFY2(cGood >= 4.5, qPrintable(QString("[%1] goodText contrast %2 < 4.5").arg(themeName).arg(cGood)));
        QVERIFY2(cWarning >= 4.5, qPrintable(QString("[%1] warningText contrast %2 < 4.5").arg(themeName).arg(cWarning)));
        QVERIFY2(cAccent >= 4.5, qPrintable(QString("[%1] accentText contrast %2 < 4.5").arg(themeName).arg(cAccent)));
    }
}

// -----------------------------------------------------------------------------
// 2. Empirically Verify Zebra Contrast > 1.20 across all 5 themes under all 3 modes
// -----------------------------------------------------------------------------
void ChallengerIter2EmpiricalHarness::testZebraContrastAcross15MatrixConfigurations() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QStringList themeNames = {
        QStringLiteral("jade-horse"),
        QStringLiteral("tokyo-night"),
        QStringLiteral("gruvbox"),
        QStringLiteral("catppuccin-latte"),
        QStringLiteral("white")
    };

    const QStringList testModes = {
        QStringLiteral("auto"),
        QStringLiteral("dark"),
        QStringLiteral("light")
    };

    qDebug() << "\n=========================================================================================";
    qDebug() << "| Theme            | Mode   | rowEven   | rowOdd    | Zebra Delta | Target | Text vs Rows   |";
    qDebug() << "=========================================================================================";

    int totalTested = 0;
    int totalPassed = 0;

    for (const QString &themeName : themeNames) {
        copyThemeToml(tempDir.path(), themeName);
        Theme theme(tempDir.path());

        for (const QString &modeSetting : testModes) {
            theme.setThemeMode(modeSetting);

            const QString rEven = theme.rowEven();
            const QString rOdd = theme.rowOdd();
            const QString text1 = theme.text1();

            // Compute Zebra contrast between rowEven and rowOdd
            const double cZebra = Theme::contrast(rEven, rOdd);

            // Compute text contrast on rowEven and rowOdd
            const double cTextEven = Theme::contrast(text1, rEven);
            const double cTextOdd = Theme::contrast(text1, rOdd);

            char logBuf[256];
            std::snprintf(logBuf, sizeof(logBuf), "| %-16s | %-6s | %-9s | %-9s | %10.3f  | > 1.20 | %5.2f / %5.2f |",
                          themeName.toLatin1().constData(),
                          modeSetting.toLatin1().constData(),
                          rEven.toLatin1().constData(),
                          rOdd.toLatin1().constData(),
                          cZebra,
                          cTextEven,
                          cTextOdd);
            qDebug() << logBuf;

            totalTested++;

            // Invariant 1: Contrast strictly greater than 1.20
            QVERIFY2(cZebra > 1.20,
                     qPrintable(QString("[%1 / %2] Zebra contrast %3 <= 1.20!").arg(themeName, modeSetting).arg(cZebra)));

            // Invariant 2: Neither rowEven nor rowOdd is pure dead black #000000
            QVERIFY2(rEven != QStringLiteral("#000000"),
                     qPrintable(QString("[%1 / %2] rowEven is dead black #000000").arg(themeName, modeSetting)));
            QVERIFY2(rOdd != QStringLiteral("#000000"),
                     qPrintable(QString("[%1 / %2] rowOdd is dead black #000000").arg(themeName, modeSetting)));

            // Invariant 3: rowEven and rowOdd never collide
            QVERIFY2(rEven != rOdd,
                     qPrintable(QString("[%1 / %2] rowEven and rowOdd collided! (%3)").arg(themeName, modeSetting, rEven)));

            // Invariant 4: Both are valid hex colors
            QVERIFY(QColor(rEven).isValid());
            QVERIFY(QColor(rOdd).isValid());

            // Invariant 5: Text contrast on both rows is >= 4.5:1
            QVERIFY2(cTextEven >= 4.5,
                     qPrintable(QString("[%1 / %2] text1 vs rowEven contrast %3 < 4.5").arg(themeName, modeSetting).arg(cTextEven)));
            QVERIFY2(cTextOdd >= 4.5,
                     qPrintable(QString("[%1 / %2] text1 vs rowOdd contrast %3 < 4.5").arg(themeName, modeSetting).arg(cTextOdd)));

            totalPassed++;
        }
    }

    qDebug() << "=========================================================================================";
    qDebug() << "Zebra Matrix Results:" << totalPassed << "/" << totalTested << "configurations PASSED.";
    QCOMPARE(totalPassed, 15);
}

// -----------------------------------------------------------------------------
// 3. Verify readColors regex resilience with unclosed quotes and adversarial syntax
// -----------------------------------------------------------------------------
void ChallengerIter2EmpiricalHarness::testReadColorsRegexUnclosedQuotesAndAdversarial() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Adversarial Case 1: Unclosed double quote on line 2, followed by valid key on line 3
    {
        const QString tomlPath = tempDir.filePath("unclosed_double.toml");
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "k1 = \"val1\"\n"
            "bad_unclosed = \"this is broken and not closed\n"
            "k2 = \"val2\"\n"
        );
        f.close();

        const auto parsed = Theme::readColors(tomlPath);
        qDebug() << "\n[Adversarial 1: Unclosed double quote]";
        qDebug() << "  Parsed keys:" << parsed.keys();
        QCOMPARE(parsed.value(QStringLiteral("k1")), QStringLiteral("val1"));
        QCOMPARE(parsed.value(QStringLiteral("k2")), QStringLiteral("val2"));
        // bad_unclosed must NOT be parsed because closing quote was missing on that line
        QVERIFY(!parsed.contains(QStringLiteral("bad_unclosed")));
    }

    // Adversarial Case 2: Unclosed single quote on line 2, followed by valid key on line 3
    {
        const QString tomlPath = tempDir.filePath("unclosed_single.toml");
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "k1 = 'val1'\n"
            "bad_unclosed_single = 'broken single quote\n"
            "k2 = 'val2'\n"
        );
        f.close();

        const auto parsed = Theme::readColors(tomlPath);
        qDebug() << "\n[Adversarial 2: Unclosed single quote]";
        qDebug() << "  Parsed keys:" << parsed.keys();
        QCOMPARE(parsed.value(QStringLiteral("k1")), QStringLiteral("val1"));
        QCOMPARE(parsed.value(QStringLiteral("k2")), QStringLiteral("val2"));
        QVERIFY(!parsed.contains(QStringLiteral("bad_unclosed_single")));
    }

    // Adversarial Case 3: Windows CRLF (\r\n) with unclosed quote
    {
        const QString tomlPath = tempDir.filePath("unclosed_crlf.toml");
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        // Explicitly write \r\n
        QByteArray data = "k1 = \"val1\"\r\nbad_crlf = \"unclosed with crlf\r\nk2 = \"val2\"\r\n";
        f.write(data);
        f.close();

        const auto parsed = Theme::readColors(tomlPath);
        qDebug() << "\n[Adversarial 3: Unclosed with CRLF]";
        qDebug() << "  Parsed keys:" << parsed.keys();
        QCOMPARE(parsed.value(QStringLiteral("k1")), QStringLiteral("val1"));
        QCOMPARE(parsed.value(QStringLiteral("k2")), QStringLiteral("val2"));
        QVERIFY(!parsed.contains(QStringLiteral("bad_crlf")));
    }

    // Adversarial Case 4: Line comments containing quotes
    {
        const QString tomlPath = tempDir.filePath("comments_with_quotes.toml");
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "accent = \"#112233\" # comment with \"quotes\" inside\n"
            "mode = 'dark' # another 'comment'\n"
        );
        f.close();

        const auto parsed = Theme::readColors(tomlPath);
        qDebug() << "\n[Adversarial 4: Comments with quotes]";
        qDebug() << "  Parsed keys:" << parsed.keys();
        QCOMPARE(parsed.value(QStringLiteral("accent")), QStringLiteral("#112233"));
        QCOMPARE(parsed.value(QStringLiteral("mode")), QStringLiteral("dark"));
    }

    // Adversarial Case 5: Pathological mixed quotes on one line: e.g. "foo' or 'bar"
    {
        const QString tomlPath = tempDir.filePath("mismatched_quotes.toml");
        QFile f(tomlPath);
        QVERIFY(f.open(QIODevice::WriteOnly | QIODevice::Text));
        f.write(
            "k1 = \"val1\"\n"
            "mismatched1 = \"value'\n"
            "mismatched2 = 'value\"\n"
            "k2 = \"val2\"\n"
        );
        f.close();

        const auto parsed = Theme::readColors(tomlPath);
        qDebug() << "\n[Adversarial 5: Mismatched quotes]";
        qDebug() << "  Parsed keys:" << parsed.keys();
        QCOMPARE(parsed.value(QStringLiteral("k1")), QStringLiteral("val1"));
        QCOMPARE(parsed.value(QStringLiteral("k2")), QStringLiteral("val2"));
        // Notice: In R"re(^\s*([A-Za-z0-9_-]+)\s*=\s*["']([^"'\r\n]+)["'])re",
        // ["'] matches either quote at start, and ["'] matches either quote at end.
        // If someone wrote "value', it matched " at start and ' at end, extracting value.
        // That is acceptable as long as it does not bleed into the next line!
        QVERIFY(!parsed.value(QStringLiteral("mismatched1")).contains(QStringLiteral("k2")));
    }
}

// -----------------------------------------------------------------------------
// 4. Test readable() boundary and extreme fallbacks
// -----------------------------------------------------------------------------
void ChallengerIter2EmpiricalHarness::testReadableBoundariesAndFallbacks() {
    // 1. Extreme: White on White (#ffffff on #ffffff)
    const QString whiteOnWhite = Theme::readable(QStringLiteral("#ffffff"), QStringLiteral("#ffffff"), {QStringLiteral("#ffffff")}, 4.5);
    const double cWhite = Theme::contrast(whiteOnWhite, QStringLiteral("#ffffff"));
    qDebug() << "\n[readable() Extreme] white on white ->" << whiteOnWhite << "contrast:" << cWhite;
    QVERIFY2(cWhite >= 4.5, "readable() must achieve >= 4.5 contrast for #ffffff on #ffffff");

    // 2. Extreme: Black on Black (#000000 on #000000)
    const QString blackOnBlack = Theme::readable(QStringLiteral("#000000"), QStringLiteral("#000000"), {QStringLiteral("#000000")}, 4.5);
    const double cBlack = Theme::contrast(blackOnBlack, QStringLiteral("#000000"));
    qDebug() << "[readable() Extreme] black on black ->" << blackOnBlack << "contrast:" << cBlack;
    QVERIFY2(cBlack >= 4.5, "readable() must achieve >= 4.5 contrast for #000000 on #000000");

    // 3. Mid-tone boundary: Gray #808080 on #808080
    const QString midGray = Theme::readable(QStringLiteral("#808080"), QStringLiteral("#ffffff"), {QStringLiteral("#808080")}, 4.5);
    const double cMid = Theme::contrast(midGray, QStringLiteral("#808080"));
    qDebug() << "[readable() Extreme] mid gray on mid gray ->" << midGray << "contrast:" << cMid;
    QVERIFY2(cMid >= 4.5, "readable() must achieve >= 4.5 contrast for #808080 on #808080");

    // 4. Non-collapsing hue check: Red against dark green background
    const QString adaptedRed = Theme::readable(QStringLiteral("#d88d91"), QStringLiteral("#ffffff"), {QStringLiteral("#142620")}, 4.5);
    const double cRed = Theme::contrast(adaptedRed, QStringLiteral("#142620"));
    qDebug() << "[readable() Hue check] red on dark green ->" << adaptedRed << "contrast:" << cRed;
    QVERIFY2(cRed >= 4.5, "readable() must achieve >= 4.5 contrast for red on dark green");
    QVERIFY2(adaptedRed != QStringLiteral("#FF6B6B"), "readable() must not inject hardcoded #FF6B6B");
}

// -----------------------------------------------------------------------------
// 5. Test geometry and radius zero invariants under M1
// -----------------------------------------------------------------------------
void ChallengerIter2EmpiricalHarness::testGeometryZeroRadiusInvariants() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    Theme theme(tempDir.path());

    // When radius is 0 (as in default or when hyprland rounding is 0)
    if (theme.radius() == 0) {
        QCOMPARE(theme.controlRadius(), 0);
        QCOMPARE(theme.panelRadius(), 0);
        QCOMPARE(theme.rounded(), false);
        qDebug() << "\n[Geometry Invariant] Theme radius is 0: controlRadius=0, panelRadius=0, rounded=false verified.";
    }

    // Normalization of setThemeMode
    theme.setThemeMode(QStringLiteral("  DARK  "));
    QCOMPARE(theme.themeMode(), QStringLiteral("dark"));
    QCOMPARE(theme.mode(), QStringLiteral("dark"));

    theme.setThemeMode(QStringLiteral("  LiGhT \t"));
    QCOMPARE(theme.themeMode(), QStringLiteral("light"));
    QCOMPARE(theme.mode(), QStringLiteral("light"));

    theme.setThemeMode(QStringLiteral("  AUTO\n"));
    QCOMPARE(theme.themeMode(), QStringLiteral("auto"));
    QCOMPARE(theme.mode(), QStringLiteral("dark")); // Default fallback mode is dark
}

void ChallengerIter2EmpiricalHarness::cleanupTestCase() {
    qDebug() << "==================================================================";
    qDebug() << "Challenger 1 M1 Iteration 2 Empirical Harness Complete.";
    qDebug() << "==================================================================";
}

QTEST_MAIN(ChallengerIter2EmpiricalHarness)
#include "challenger_iter2_empirical_harness.moc"
