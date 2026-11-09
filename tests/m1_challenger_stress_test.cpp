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

class M1ChallengerStressTest : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();

    // 1. Empty & Missing colors.toml
    void testEmptyColorsToml();
    void testMissingColorsToml();

    // 2. Extreme contrast pairs & mathematical invariants
    void testExtremeContrastAndMath();

    // 3. Colors near WCAG boundary (contrast ~ 4.49 to 4.51)
    void testWcagBoundaryNear45();

    // 4. All 5 official Omarchy themes verification
    void testAllFiveOfficialOmarchyThemes();

    // 5. rowEven and rowOdd in all 5 themes and edge cases
    void testZebraStripingInAllThemes();

    // 6. Tri-state themeMode transitions across all themes
    void testTriStateModeTransitions();

    // 7. withAlpha() exact 9-character #AARRGGBB hex and clamping
    void testWithAlphaHexFormatAndClamping();

    // 8. Zero presence of "rgba(" in any theme property getter
    void testZeroPresenceOfRgba();

    // 9. Malformed TOML stress test
    void testMalformedColorsTomlStress();

    // 10. Empirical Bug Reproduction Slots
    void testForcedDarkModeOnLightThemesDefect();
    void testUnclosedQuoteBleedDefect();

    void cleanupTestCase();

private:
    QString setupThemeDir(const QString &baseDir, const QString &sourceColorsTomlPath);
};

void M1ChallengerStressTest::initTestCase() {
    qDebug() << "=================================================================";
    qDebug() << "Antigravity Hub — Challenger 1 Adversarial Stress Test Suite (M1)";
    qDebug() << "=================================================================";
}

QString M1ChallengerStressTest::setupThemeDir(const QString &baseDir, const QString &sourceColorsTomlPath) {
    QDir dir(baseDir);
    dir.mkpath("theme");
    const QString targetToml = dir.filePath("theme/colors.toml");
    if (QFile::exists(targetToml)) {
        QFile::remove(targetToml);
    }
    if (!sourceColorsTomlPath.isEmpty()) {
        QFile::copy(sourceColorsTomlPath, targetToml);
    }
    return targetToml;
}

// -----------------------------------------------------------------------------
// 1. Empty & Missing colors.toml
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testEmptyColorsToml() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Create an empty (0-byte) colors.toml
    const QString tomlPath = setupThemeDir(tempDir.path(), QString());
    QFile emptyFile(tomlPath);
    QVERIFY(emptyFile.open(QIODevice::WriteOnly));
    emptyFile.close();
    QCOMPARE(QFileInfo(tomlPath).size(), 0);

    // Initialize Theme pointing to the directory with empty colors.toml
    Theme theme(tempDir.path());

    // Verify Theme does not crash and falls back gracefully
    QVERIFY(!theme.background().isEmpty());
    QVERIFY(QColor(theme.background()).isValid());
    QVERIFY(!theme.text1().isEmpty());
    QVERIFY(QColor(theme.text1()).isValid());

    // Check contrast of text1 on background
    const double contrastText1 = Theme::contrast(theme.text1(), theme.background());
    qDebug() << "[Empty colors.toml] background:" << theme.background()
             << "text1:" << theme.text1() << "contrast:" << contrastText1;
    QVERIFY2(contrastText1 >= 4.5, "Fallback text1 must achieve >= 4.5 contrast against background");

    // Check zebra striping properties
    QVERIFY(!theme.rowEven().isEmpty());
    QVERIFY(!theme.rowOdd().isEmpty());
    QVERIFY2(theme.rowEven() != theme.rowOdd(), "rowEven and rowOdd must never collide on empty colors.toml");
    QVERIFY2(theme.rowEven() != QStringLiteral("#000000"), "rowEven must not evaluate to pure black #000000");
    QVERIFY2(theme.rowOdd() != QStringLiteral("#000000"), "rowOdd must not evaluate to pure black #000000");

    // Check dangerText
    QVERIFY2(theme.dangerText() != QStringLiteral("#FF6B6B"), "dangerText must never be hardcoded #FF6B6B");

    // Verify zero rgba
    QVERIFY(!theme.border().contains("rgba"));
    QVERIFY(!theme.hairline().contains("rgba"));
    QVERIFY(!theme.controlBorder().contains("rgba"));
    QVERIFY(!theme.trackBg().contains("rgba"));
    QVERIFY(!theme.pillBg().contains("rgba"));
}

void M1ChallengerStressTest::testMissingColorsToml() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    // Point to non-existent subpath
    const QString nonExistentDir = tempDir.filePath("does_not_exist");

    Theme theme(nonExistentDir);
    QVERIFY(QColor(theme.background()).isValid());
    QVERIFY(QColor(theme.text1()).isValid());
    QVERIFY(theme.rowEven() != theme.rowOdd());
    QVERIFY(theme.rowEven() != QStringLiteral("#000000"));
    QVERIFY(theme.rowOdd() != QStringLiteral("#000000"));
}

// -----------------------------------------------------------------------------
// 2. Extreme contrast pairs & mathematical invariants
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testExtremeContrastAndMath() {
    // 2.1 Identical colors -> contrast must be 1.0 exactly
    QCOMPARE(Theme::contrast("#000000", "#000000"), 1.0);
    QCOMPARE(Theme::contrast("#ffffff", "#ffffff"), 1.0);
    QCOMPARE(Theme::contrast("#123456", "#123456"), 1.0);

    // 2.2 Extreme opposite colors -> contrast must be ~21.0
    const double blackWhiteContrast = Theme::contrast("#000000", "#ffffff");
    QVERIFY(qAbs(blackWhiteContrast - 21.0) < 0.05);

    // 2.3 Symmetry: contrast(a, b) == contrast(b, a)
    const QStringList sampleColors = {
        "#142620", "#dfede5", "#d88d91", "#8bcbb1", "#eff1f5", "#4c4f69", "#000000", "#ffffff"
    };
    for (int i = 0; i < sampleColors.size(); ++i) {
        for (int j = 0; j < sampleColors.size(); ++j) {
            const double c1 = Theme::contrast(sampleColors[i], sampleColors[j]);
            const double c2 = Theme::contrast(sampleColors[j], sampleColors[i]);
            QCOMPARE(c1, c2);
            QVERIFY(c1 >= 1.0);
            QVERIFY(c1 <= 21.01);
        }
    }

    // 2.4 Invalid colors handled gracefully
    QCOMPARE(Theme::contrast("invalid", "#ffffff"), 1.0);
    QCOMPARE(Theme::contrast("#000000", "not-a-color"), 1.0);
    QCOMPARE(Theme::contrast("", ""), 1.0);

    // 2.5 mix() bounds and clamping
    QCOMPARE(Theme::mix("#000000", "#ffffff", -5.0), QStringLiteral("#000000"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", 15.0), QStringLiteral("#ffffff"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", 0.0), QStringLiteral("#000000"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", 1.0), QStringLiteral("#ffffff"));
    QCOMPARE(Theme::mix("#000000", "#ffffff", 0.5), QStringLiteral("#808080"));
    QCOMPARE(Theme::mix("invalid", "#ffffff", 0.5), QStringLiteral("#ffffff"));
    QCOMPARE(Theme::mix("#000000", "invalid", 0.5), QStringLiteral("#000000"));

    // 2.6 Extreme readable() tests:
    // Pure black on pure black surface -> must shift to contrast >= 4.5
    const QString adaptedBlack = Theme::readable("#000000", "#ffffff", {"#000000"}, 4.5);
    const double adaptedBlackContrast = Theme::contrast(adaptedBlack, "#000000");
    qDebug() << "[readable] pure black on black ->" << adaptedBlack << "contrast:" << adaptedBlackContrast;
    QVERIFY2(adaptedBlackContrast >= 4.5, "readable() must shift black on black to >= 4.5 contrast");

    // Pure white on pure white surface -> must shift to contrast >= 4.5
    const QString adaptedWhite = Theme::readable("#ffffff", "#000000", {"#ffffff"}, 4.5);
    const double adaptedWhiteContrast = Theme::contrast(adaptedWhite, "#ffffff");
    qDebug() << "[readable] pure white on white ->" << adaptedWhite << "contrast:" << adaptedWhiteContrast;
    QVERIFY2(adaptedWhiteContrast >= 4.5, "readable() must shift white on white to >= 4.5 contrast");

    // Conflicting surfaces: black and white simultaneously
    // Can it terminate safely without infinite loop or crash?
    const QString adaptedBoth = Theme::readable("#ff5555", "#ffffff", {"#000000", "#ffffff"}, 4.5);
    QVERIFY(!adaptedBoth.isEmpty());
    QVERIFY(QColor(adaptedBoth).isValid());
    qDebug() << "[readable] conflicting surfaces result:" << adaptedBoth;
}

// -----------------------------------------------------------------------------
// 3. Colors near WCAG boundary (contrast ~ 4.49 to 4.51)
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testWcagBoundaryNear45() {
    // Surface: pure black #000000 (relative luminance = 0)
    // Contrast formula against #000000: (Y + 0.05) / 0.05 = 20 * Y + 1
    // Contrast = 4.50 corresponds to Y = (4.50 - 1) / 20 = 0.175000.
    // Let's test a sequence of gray levels:
    // RGB 115 (#737373): linear(115/255 = 0.45098) = 0.17068 -> Contrast = 4.4136 (< 4.5)
    // RGB 116 (#747474): linear(116/255 = 0.45490) = 0.17410 -> Contrast = 4.4820 (< 4.50, close boundary!)
    // RGB 117 (#757575): linear(117/255 = 0.45882) = 0.17755 -> Contrast = 4.5510 (> 4.50, close boundary!)

    const QString col448 = QStringLiteral("#747474");
    const QString col455 = QStringLiteral("#757575");
    const QString surface = QStringLiteral("#000000");

    const double cSub = Theme::contrast(col448, surface);
    const double cSuper = Theme::contrast(col455, surface);
    qDebug() << "[WCAG Boundary] col448 (" << col448 << ") contrast:" << cSub;
    qDebug() << "[WCAG Boundary] col455 (" << col455 << ") contrast:" << cSuper;

    QVERIFY(cSub < 4.50);
    QVERIFY(cSuper >= 4.50);

    // Case 1: Color with contrast 4.48 < 4.50
    // Theme::readable must adapt it to achieve >= 4.50 against surface
    const QString adaptedSub = Theme::readable(col448, "#ffffff", {surface}, 4.5);
    const double adaptedContrast = Theme::contrast(adaptedSub, surface);
    qDebug() << "[WCAG Boundary] adaptedSub:" << adaptedSub << "contrast:" << adaptedContrast;
    QVERIFY2(adaptedContrast >= 4.50, "Color near 4.49 boundary MUST be adapted to >= 4.50");
    QVERIFY2(adaptedSub != col448, "Sub-4.5 color must be modified by readable()");

    // Case 2: Color with contrast 4.55 >= 4.50
    // Theme::readable should recognize that it already has enough contrast and leave it untouched
    const QString adaptedSuper = Theme::readable(col455, "#ffffff", {surface}, 4.5);
    qDebug() << "[WCAG Boundary] adaptedSuper:" << adaptedSuper;
    QCOMPARE(adaptedSuper, col455);
}

// -----------------------------------------------------------------------------
// 4. All 5 official Omarchy themes verification
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testAllFiveOfficialOmarchyThemes() {
    const QStringList themeNames = {
        "jade-horse",
        "tokyo-night",
        "gruvbox",
        "catppuccin-latte",
        "white"
    };

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    for (const QString &themeName : themeNames) {
        const QString sourceToml = QString("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName);
        QVERIFY2(QFile::exists(sourceToml), qPrintable(QString("Theme colors.toml missing: %1").arg(sourceToml)));

        setupThemeDir(tempDir.path(), sourceToml);

        Theme theme(tempDir.path());

        qDebug() << "\n>>> Stress-Testing Theme:" << themeName;
        qDebug() << "    mode:" << theme.mode()
                 << "accent:" << theme.accent()
                 << "background:" << theme.background()
                 << "canvas:" << theme.canvas()
                 << "surfaceTop:" << theme.surfaceTop()
                 << "window:" << theme.surface2()
                 << "sidebar:" << theme.surface1();
        qDebug() << "    good:" << theme.good() << "goodText:" << theme.goodText();
        qDebug() << "    warning:" << theme.warning() << "warningText:" << theme.warningText();
        qDebug() << "    danger:" << theme.danger() << "dangerText:" << theme.dangerText();
        qDebug() << "    rowEven:" << theme.rowEven() << "rowOdd:" << theme.rowOdd();

        // Check 1: Danger and DangerText must NEVER be pure red #FF6B6B
        QVERIFY2(theme.danger() != QStringLiteral("#FF6B6B"),
                 qPrintable(QString("[%1] theme.danger() is pure red #FF6B6B!").arg(themeName)));
        QVERIFY2(theme.dangerText() != QStringLiteral("#FF6B6B"),
                 qPrintable(QString("[%1] theme.dangerText() is pure red #FF6B6B!").arg(themeName)));

        // Check 2: All status text colors must achieve >= 4.5:1 contrast against relevant surfaces
        const QStringList surfaces = { theme.canvas(), theme.surfaceTop(), theme.surface2(), theme.surface1() };
        for (const QString &surf : surfaces) {
            const double cDanger = Theme::contrast(theme.dangerText(), surf);
            const double cGood = Theme::contrast(theme.goodText(), surf);
            const double cWarning = Theme::contrast(theme.warningText(), surf);
            const double cAccent = Theme::contrast(theme.accentText(), surf);

            qDebug() << "    [Surfaces Test on" << surf << "]"
                     << "dangerText:" << cDanger
                     << "goodText:" << cGood
                     << "warningText:" << cWarning
                     << "accentText:" << cAccent;

            QVERIFY2(cDanger >= 4.50,
                     qPrintable(QString("[%1] dangerText contrast (%2) on surface %3 is < 4.5!")
                                .arg(themeName).arg(cDanger).arg(surf)));
            QVERIFY2(cGood >= 4.50,
                     qPrintable(QString("[%1] goodText contrast (%2) on surface %3 is < 4.5!")
                                .arg(themeName).arg(cGood).arg(surf)));
            QVERIFY2(cWarning >= 4.50,
                     qPrintable(QString("[%1] warningText contrast (%2) on surface %3 is < 4.5!")
                                .arg(themeName).arg(cWarning).arg(surf)));
            QVERIFY2(cAccent >= 4.50,
                     qPrintable(QString("[%1] accentText contrast (%2) on surface %3 is < 4.5!")
                                .arg(themeName).arg(cAccent).arg(surf)));
        }

        // Check 3: rowEven and rowOdd in this theme
        QVERIFY2(theme.rowEven() != theme.rowOdd(),
                 qPrintable(QString("[%1] rowEven and rowOdd collided! (%2)").arg(themeName, theme.rowEven())));
        QVERIFY2(theme.rowEven() != QStringLiteral("#000000"),
                 qPrintable(QString("[%1] rowEven evaluated to dead black #000000!").arg(themeName)));
        QVERIFY2(theme.rowOdd() != QStringLiteral("#000000"),
                 qPrintable(QString("[%1] rowOdd evaluated to dead black #000000!").arg(themeName)));

        // Check 4: TrackBg and PillBg format
        QVERIFY2(theme.trackBg().startsWith("#") && theme.trackBg().length() == 9,
                 qPrintable(QString("[%1] trackBg not 9-char hex: %2").arg(themeName, theme.trackBg())));
        QVERIFY2(theme.pillBg().startsWith("#") && theme.pillBg().length() == 9,
                 qPrintable(QString("[%1] pillBg not 9-char hex: %2").arg(themeName, theme.pillBg())));
    }
}

// -----------------------------------------------------------------------------
// 5. rowEven and rowOdd in all 5 themes and edge cases
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testZebraStripingInAllThemes() {
    const QStringList themeNames = {
        "jade-horse", "tokyo-night", "gruvbox", "catppuccin-latte", "white"
    };

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    for (const QString &themeName : themeNames) {
        setupThemeDir(tempDir.path(), QString("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName));
        Theme theme(tempDir.path());

        const QString even = theme.rowEven();
        const QString odd = theme.rowOdd();

        QVERIFY(QColor(even).isValid());
        QVERIFY(QColor(odd).isValid());
        QVERIFY(even != odd);
        QVERIFY(even != "#000000");
        QVERIFY(odd != "#000000");

        const double stripingContrast = Theme::contrast(even, odd);
        qDebug() << "[Zebra Striping -" << themeName << "] even:" << even
                 << "odd:" << odd << "contrast delta:" << stripingContrast;

        // Striping must provide visible distinction (contrast delta > 1.01)
        QVERIFY2(stripingContrast > 1.01,
                 qPrintable(QString("[%1] Zebra striping contrast between even and odd is invisible (%2)")
                            .arg(themeName).arg(stripingContrast)));
    }
}

// -----------------------------------------------------------------------------
// 6. Tri-state themeMode transitions across all themes
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testTriStateModeTransitions() {
    const QStringList themeNames = {
        "jade-horse", "tokyo-night", "gruvbox", "catppuccin-latte", "white"
    };

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    for (const QString &themeName : themeNames) {
        setupThemeDir(tempDir.path(), QString("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName));
        Theme theme(tempDir.path());

        // 6.1 Forced Light Mode
        theme.setThemeMode("light");
        QCOMPARE(theme.themeMode(), QString("light"));
        QCOMPARE(theme.mode(), QString("light"));
        QVERIFY(theme.rowEven() != theme.rowOdd());
        QVERIFY(theme.rowEven() != "#000000");
        QVERIFY(theme.rowOdd() != "#000000");
        const double cText1Light = Theme::contrast(theme.text1(), theme.background());
        qDebug() << "[TriState Light -" << themeName << "] text1:" << theme.text1()
                 << "bg:" << theme.background() << "contrast:" << cText1Light;
        QVERIFY2(cText1Light >= 4.5,
                 qPrintable(QString("[%1 forced light] text1 contrast on background is %2 < 4.5")
                            .arg(themeName).arg(cText1Light)));

        // 6.2 Forced Dark Mode
        theme.setThemeMode("dark");
        QCOMPARE(theme.themeMode(), QString("dark"));
        QCOMPARE(theme.mode(), QString("dark"));
        QVERIFY(theme.rowEven() != theme.rowOdd());
        QVERIFY(theme.rowEven() != "#000000");
        QVERIFY(theme.rowOdd() != "#000000");
        const double cText1Dark = Theme::contrast(theme.text1(), theme.background());
        qDebug() << "[TriState Dark -" << themeName << "] text1:" << theme.text1()
                 << "bg:" << theme.background() << "contrast:" << cText1Dark;

        // AUDIT CHECK: Does forced dark mode on light themes maintain readability?
        if (cText1Dark < 4.5) {
            qCritical() << "!!! CRITICAL FINDING: Forced dark mode on theme" << themeName
                        << "failed contrast gate! text1:" << theme.text1()
                        << "background:" << theme.background()
                        << "contrast:" << cText1Dark;
        }
        // Let's record this finding!

        // 6.3 Auto Mode (reverts to colors.toml mode)
        theme.setThemeMode("auto");
        QCOMPARE(theme.themeMode(), QString("auto"));
    }
}

// -----------------------------------------------------------------------------
// 7. withAlpha() exact 9-character #AARRGGBB hex and clamping
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testWithAlphaHexFormatAndClamping() {
    static const QRegularExpression hexArgbRegex(R"(^#[0-9a-fA-F]{8}$)");

    const QStringList testColors = {
        "#ffffff", "#000000", "#142620", "#dfede5", "#d88d91", "#123456", "#abcdef"
    };

    const QList<double> testAlphas = {
        0.0, 0.08, 0.12, 0.16, 0.24, 0.32, 0.5, 0.75, 0.99, 1.0,
        -0.5, -100.0, // negative out-of-range -> clamp to 0.0
        1.5, 999.0    // excessive out-of-range -> clamp to 1.0
    };

    for (const QString &col : testColors) {
        for (double alpha : testAlphas) {
            const QString result = Theme::withAlpha(col, alpha);

            // Format invariant: must match ^#[0-9a-fA-F]{8}$ (exactly 9 chars)
            QVERIFY2(hexArgbRegex.match(result).hasMatch(),
                     qPrintable(QString("withAlpha(%1, %2) produced invalid format: '%3'")
                                .arg(col).arg(alpha).arg(result)));
            QCOMPARE(result.length(), 9);

            // Check clamping semantics
            if (alpha <= 0.0) {
                QVERIFY(result.mid(1, 2).toLower() == "00");
            } else if (alpha >= 1.0) {
                QVERIFY(result.mid(1, 2).toLower() == "ff");
            }
        }
    }

    // Specific reference tokens from Omarchy design spec
    QCOMPARE(Theme::withAlpha("#ffffff", 0.08).toLower(), QStringLiteral("#14ffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.12).toLower(), QStringLiteral("#1fffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.24).toLower(), QStringLiteral("#3dffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.16).toLower(), QStringLiteral("#29ffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.07).toLower(), QStringLiteral("#12ffffff"));
}

// -----------------------------------------------------------------------------
// 8. Zero presence of "rgba(" in any theme property getter
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testZeroPresenceOfRgba() {
    const QStringList themeNames = {
        "jade-horse", "tokyo-night", "gruvbox", "catppuccin-latte", "white"
    };

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    for (const QString &themeName : themeNames) {
        setupThemeDir(tempDir.path(), QString("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName));
        Theme theme(tempDir.path());

        const QList<QPair<QString, QString>> properties = {
            {"accent", theme.accent()},
            {"accentForeground", theme.accentForeground()},
            {"background", theme.background()},
            {"surface1", theme.surface1()},
            {"surface2", theme.surface2()},
            {"surface3", theme.surface3()},
            {"text1", theme.text1()},
            {"text2", theme.text2()},
            {"text3", theme.text3()},
            {"text4", theme.text4()},
            {"border", theme.border()},
            {"mode", theme.mode()},
            {"selection", theme.selection()},
            {"muted", theme.muted()},
            {"themeMode", theme.themeMode()},
            {"canvas", theme.canvas()},
            {"surfaceTop", theme.surfaceTop()},
            {"surfaceBottom", theme.surfaceBottom()},
            {"hairline", theme.hairline()},
            {"controlBorder", theme.controlBorder()},
            {"danger", theme.danger()},
            {"good", theme.good()},
            {"warning", theme.warning()},
            {"dangerText", theme.dangerText()},
            {"goodText", theme.goodText()},
            {"warningText", theme.warningText()},
            {"accentText", theme.accentText()},
            {"rowEven", theme.rowEven()},
            {"rowOdd", theme.rowOdd()},
            {"trackBg", theme.trackBg()},
            {"pillBg", theme.pillBg()}
        };

        for (const auto &pair : properties) {
            const QString &propName = pair.first;
            const QString &val = pair.second;

            QVERIFY2(!val.contains("rgba", Qt::CaseInsensitive),
                     qPrintable(QString("[%1] Property '%2' contains illegal 'rgba': %3")
                                .arg(themeName, propName, val)));

            // Color properties should start with # or be named colors (black/white)
            if (propName != "mode" && propName != "themeMode" && propName != "accentForeground") {
                QVERIFY2(val.startsWith("#"),
                         qPrintable(QString("[%1] Color property '%2' does not start with '#': %3")
                                    .arg(themeName, propName, val)));
                QVERIFY2(QColor(val).isValid(),
                         qPrintable(QString("[%1] Property '%2' is not a valid QColor: %3")
                                    .arg(themeName, propName, val)));
            }
        }
    }
}

// -----------------------------------------------------------------------------
// 9. Malformed TOML stress test
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testMalformedColorsTomlStress() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString tomlPath = setupThemeDir(tempDir.path(), QString());
    QFile file(tomlPath);
    QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Text));
    file.write(
        "# Adversarial Malformed TOML\n"
        "random junk without keys\n"
        "accent = \"#112233\"\n"
        "weird-spacing  =   '#8899aa'   \n"
        "binary_junk = \x01\x02\x03\n"
        "number_val = 12345\n"
        "red = \"#ff0033\"\n"
    );
    file.close();

    const auto parsed = Theme::readColors(tomlPath);
    QVERIFY(parsed.contains("accent"));
    QCOMPARE(parsed.value("accent"), QString("#112233"));
    QVERIFY(parsed.contains("weird-spacing"));
    QCOMPARE(parsed.value("weird-spacing"), QString("#8899aa"));
    QVERIFY(parsed.contains("red"));
    QCOMPARE(parsed.value("red"), QString("#ff0033"));

    // Theme initialization with malformed file
    Theme theme(tempDir.path());
    QVERIFY(QColor(theme.background()).isValid());
    QVERIFY(QColor(theme.text1()).isValid());
    QVERIFY(theme.rowEven() != theme.rowOdd());
    QVERIFY(theme.rowEven() != "#000000");
    QVERIFY(theme.rowOdd() != "#000000");
}

// -----------------------------------------------------------------------------
// 10. Empirical Bug Reproduction: Forced Dark Mode on Light Themes Defect
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testForcedDarkModeOnLightThemesDefect() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // Setup 'white' theme
    setupThemeDir(tempDir.path(), "/usr/share/omarchy/themes/white/colors.toml");
    Theme theme(tempDir.path());

    // Switch to forced dark mode
    theme.setThemeMode("dark");

    // Empirical observation of values:
    const QString bg = theme.background();
    const QString text1 = theme.text1();
    const double contrastVal = Theme::contrast(text1, bg);

    qDebug() << "=================================================================";
    qDebug() << "[Bug Reproduction 1] Forced Dark Mode on 'white' theme:";
    qDebug() << "  background:" << bg << "(expected dark tone like #0e0e14)";
    qDebug() << "  text1:" << text1 << "(hardcoded #FFFFFF)";
    qDebug() << "  contrast ratio:" << contrastVal << ": 1 (WCAG threshold: >= 4.5:1)";
    qDebug() << "  rowEven:" << theme.rowEven() << "contrast with text1:" << Theme::contrast(text1, theme.rowEven());
    qDebug() << "=================================================================";

    // We empirically record that contrastVal is 1.00 (white on white)
    QVERIFY(contrastVal < 4.5);
    QCOMPARE(contrastVal, 1.0);
}

// -----------------------------------------------------------------------------
// 11. Empirical Bug Reproduction: Multiline Quote Bleed in readColors
// -----------------------------------------------------------------------------
void M1ChallengerStressTest::testUnclosedQuoteBleedDefect() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    const QString tomlPath = setupThemeDir(tempDir.path(), QString());
    QFile file(tomlPath);
    QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Text));
    file.write(
        "accent = \"#112233\"\n"
        "broken = \"unclosed string\n"
        "important_key = '#8899aa'\n"
        "red = \"#ff0033\"\n"
    );
    file.close();

    const auto parsed = Theme::readColors(tomlPath);
    qDebug() << "=================================================================";
    qDebug() << "[Bug Reproduction 2] Unclosed quote bleed in readColors():";
    qDebug() << "  parsed keys:" << parsed.keys();
    qDebug() << "  broken value:" << parsed.value("broken");
    qDebug() << "  important_key present?:" << parsed.contains("important_key");
    qDebug() << "=================================================================";

    // Empirical verification: important_key was swallowed into broken
    QVERIFY(!parsed.contains("important_key"));
    QVERIFY(parsed.value("broken").contains("important_key"));
}

void M1ChallengerStressTest::cleanupTestCase() {
    qDebug() << "=================================================================";
    qDebug() << "Antigravity Hub — Challenger 1 Adversarial Stress Test Completed.";
    qDebug() << "=================================================================";
}

QTEST_MAIN(M1ChallengerStressTest)
#include "m1_challenger_stress_test.moc"
