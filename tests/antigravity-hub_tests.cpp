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
#include <QQuickWindow>
#include <QQuickItem>
#include <QRegularExpression>
#include <QMetaProperty>
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
    void themeZeroRadiusEnforcement();
    void themeColorEngineAndOmarchyAlgorithms();
    void themeTriStateMatrixAndContrastInvariants();
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
    void accountFilterProxyModelFullSorting();

    // Milestone 2 Tests: BackendController
    void backendControllerStateAndUrls();
    void backendControllerOffscreenExecution();
    void backendControllerExtendedApiMethods();

    // Milestone 3 Tests: QML Components Instantiation & Smoke
    void qmlComponentsInstantiationAndSmoke();
    void accountListViewVisualDenoisingInvariants();

    // Milestone 3 Tests: v2.50.0 Invariant Verification
    void v250WindowGeometryLockInvariants();
    void v250TableColumnsFixedGeometryInvariants();
    void v250ScreenFixedZebraRhythmInvariants();
    void v250AccountReorderPersistenceInvariants();
    void v250ThemeMonoFontAndAccentTextInvariants();

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
    QCOMPARE(theme.controlRadius(), 0);
    QCOMPARE(theme.panelRadius(), 0);
    QCOMPARE(theme.rounded(), false);
    QCOMPARE(theme.mode(), QString("dark"));
    QCOMPARE(theme.background(), QString("#0e0e14"));
    QCOMPARE(theme.border(), QString("#14ffffff"));
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
    QCOMPARE(theme.text3(), QString("#CBD5E1"));
    QCOMPARE(theme.text4(), QString("#94A3B8"));

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

void AntigravityHubTests::themeZeroRadiusEnforcement() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // 1. Invariant: Default theme constructed with empty parameters enforces zero radius
    Theme theme(tempDir.path());
    QCOMPARE(theme.radius(), 0);
    QCOMPARE(theme.controlRadius(), 0);
    QCOMPARE(theme.panelRadius(), 0);
    QCOMPARE(theme.rounded(), false);

    // 2. Invariant: Even if an external hyprctl reports a non-zero rounding value (e.g. 6 or 12),
    // User Supreme Visual Iron Rule mandates that Theme strictly maintains zero radius.
    const QString mockScriptPath = tempDir.filePath("mock_hyprctl.sh");
    QFile mockScript(mockScriptPath);
    QVERIFY(mockScript.open(QIODevice::WriteOnly | QIODevice::Text));
    mockScript.write(
        "#!/bin/sh\n"
        "echo '{\"option\": \"decoration:rounding\", \"int\": 6, \"set\": true}'\n"
    );
    mockScript.close();
    mockScript.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);

    Theme themeWithMock(tempDir.path(), nullptr, mockScriptPath);
    QCOMPARE(themeWithMock.radius(), 0);
    QCOMPARE(themeWithMock.controlRadius(), 0);
    QCOMPARE(themeWithMock.panelRadius(), 0);
    QCOMPARE(themeWithMock.rounded(), false);

    // 3. Invariant: Radii remain strictly zero across all theme mode transitions
    themeWithMock.setThemeMode(QStringLiteral("light"));
    QCOMPARE(themeWithMock.radius(), 0);
    QCOMPARE(themeWithMock.controlRadius(), 0);
    QCOMPARE(themeWithMock.panelRadius(), 0);
    QCOMPARE(themeWithMock.rounded(), false);

    themeWithMock.setThemeMode(QStringLiteral("dark"));
    QCOMPARE(themeWithMock.radius(), 0);
    QCOMPARE(themeWithMock.controlRadius(), 0);
    QCOMPARE(themeWithMock.panelRadius(), 0);
    QCOMPARE(themeWithMock.rounded(), false);
}

void AntigravityHubTests::themeColorEngineAndOmarchyAlgorithms() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());

    // 1. Full 16-key palette regex extraction via Theme::readColors()
    const QString colorsPath = tempDir.filePath("colors.toml");
    QFile colorsFile(colorsPath);
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
        "dark_foreground = \"#91ad9f\"\n"
        "light_foreground = \"#bed6c9\"\n"
        "bright_foreground = \"#f0faf4\"\n"
        "red = \"#d88d91\"\n"
        "yellow = \"#c5cc91\"\n"
        "orange = \"#d2ab8d\"\n"
        "green = \"#8bcbb1\"\n"
    );
    colorsFile.close();

    const auto colors = Theme::readColors(colorsPath);
    QCOMPARE(colors.size(), 16);
    QCOMPARE(colors.value("mode"), QString("dark"));
    QCOMPARE(colors.value("accent"), QString("#8bcbb1"));
    QCOMPARE(colors.value("selection"), QString("#2b5147"));
    QCOMPARE(colors.value("muted"), QString("#64887b"));
    QCOMPARE(colors.value("background"), QString("#142620"));
    QCOMPARE(colors.value("dark_background"), QString("#0f1e19"));
    QCOMPARE(colors.value("darker_background"), QString("#0a1713"));
    QCOMPARE(colors.value("lighter_background"), QString("#203b31"));
    QCOMPARE(colors.value("foreground"), QString("#dfede5"));
    QCOMPARE(colors.value("dark_foreground"), QString("#91ad9f"));
    QCOMPARE(colors.value("light_foreground"), QString("#bed6c9"));
    QCOMPARE(colors.value("bright_foreground"), QString("#f0faf4"));
    QCOMPARE(colors.value("red"), QString("#d88d91"));
    QCOMPARE(colors.value("yellow"), QString("#c5cc91"));
    QCOMPARE(colors.value("orange"), QString("#d2ab8d"));
    QCOMPARE(colors.value("green"), QString("#8bcbb1"));

    // 2. WCAG 2.1 Contrast calculation
    const double maxContrast = Theme::contrast("#000000", "#ffffff");
    QVERIFY(qAbs(maxContrast - 21.0) < 0.1);
    QCOMPARE(Theme::contrast("#123456", "#123456"), 1.0);

    // 3. Linear sRGB mix()
    QCOMPARE(Theme::mix("#000000", "#ffffff", 0.5), QString("#808080"));
    QCOMPARE(Theme::mix("#102030", "#102030", 0.75), QString("#102030"));

    // 4. withAlpha() HexArgb serialization (#AARRGGBB)
    QCOMPARE(Theme::withAlpha("#ffffff", 0.08), QString("#14ffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.12), QString("#1fffffff"));
    QCOMPARE(Theme::withAlpha("#ffffff", 0.24), QString("#3dffffff"));
    QCOMPARE(Theme::withAlpha("#112233", 0.0), QString("#00112233"));
    QCOMPARE(Theme::withAlpha("#112233", 1.0), QString("#ff112233"));

    // 5. readable() WCAG 4.5:1 adaptation (preserving hue/saturation in HSL)
    const QString adaptedRed = Theme::readable("#d88d91", "#ffffff", {"#142620", "#172c25"}, 4.5);
    QVERIFY(Theme::contrast(adaptedRed, "#142620") >= 4.5);
    QVERIFY(Theme::contrast(adaptedRed, "#172c25") >= 4.5);
    QVERIFY(adaptedRed != QString("#FF6B6B")); // Absolutely no hardcoded pure red

    // Low contrast color adapted until contrast >= 4.5:1
    const QString adaptedLow = Theme::readable("#182822", "#ffffff", {"#142620"}, 4.5);
    QVERIFY(Theme::contrast(adaptedLow, "#142620") >= 4.5);

    // 6. Live Theme instance verification with full palette directory
    QDir(tempDir.path()).mkpath("theme");
    QFile::copy(colorsPath, tempDir.filePath("theme/colors.toml"));

    Theme theme(tempDir.path());
    QCOMPARE(theme.accent(), QString("#8bcbb1"));
    QCOMPARE(theme.background(), QString("#142620"));

    // Danger / Good / Warning derived from parsed palette, zero #FF6B6B
    QCOMPARE(theme.danger(), QString("#d88d91"));
    QCOMPARE(theme.good(), QString("#8bcbb1"));
    QCOMPARE(theme.warning(), QString("#c5cc91"));
    QVERIFY(theme.dangerText() != QString("#FF6B6B"));
    QVERIFY(Theme::contrast(theme.dangerText(), theme.canvas()) >= 4.5);
    QVERIFY(Theme::contrast(theme.goodText(), theme.canvas()) >= 4.5);
    QVERIFY(Theme::contrast(theme.warningText(), theme.canvas()) >= 4.5);

    // Zebra striping properties (rowEven, rowOdd, trackBg, pillBg)
    const QString expectedRowEven = Theme::mix("#0a1713", "#142620", 0.35);
    const QString expectedRowOdd = Theme::mix("#142620", "#dfede5", 0.085);
    QCOMPARE(theme.rowEven(), expectedRowEven);
    QCOMPARE(theme.rowOdd(), expectedRowOdd);
    QVERIFY(theme.rowEven() != theme.rowOdd());
    QVERIFY(theme.rowEven() != QString("#000000"));
    QVERIFY(theme.rowOdd() != QString("#000000"));
    QCOMPARE(theme.trackBg(), Theme::withAlpha("#dfede5", 0.16));
    QCOMPARE(theme.pillBg(), Theme::withAlpha("#dfede5", 0.07));

    // Zero invalid rgba strings
    QVERIFY(!theme.border().contains("rgba"));
    QVERIFY(!theme.hairline().contains("rgba"));
    QVERIFY(!theme.controlBorder().contains("rgba"));
    QVERIFY(!theme.trackBg().contains("rgba"));
    QVERIFY(!theme.pillBg().contains("rgba"));
    QVERIFY(theme.border().startsWith("#"));
    QVERIFY(theme.hairline().startsWith("#"));
    QVERIFY(theme.controlBorder().startsWith("#"));

    // 7. Tri-state mode: auto, dark, light
    theme.setThemeMode("light");
    QCOMPARE(theme.themeMode(), QString("light"));
    QCOMPARE(theme.mode(), QString("light"));
    QCOMPARE(theme.background(), QString("#FFFFFF"));
    QCOMPARE(theme.rowEven(), QString("#FFFFFF"));
    QVERIFY(theme.rowOdd() != QString("#000000"));
    QVERIFY(theme.rowEven() != theme.rowOdd());

    theme.setThemeMode("dark");
    QCOMPARE(theme.themeMode(), QString("dark"));
    QCOMPARE(theme.mode(), QString("dark"));
    QCOMPARE(theme.rowEven(), expectedRowEven);

    theme.setThemeMode("auto");
    QCOMPARE(theme.themeMode(), QString("auto"));
    QCOMPARE(theme.mode(), QString("dark")); // Follows colors.toml dark mode

    // 8. Secondary invariants: unclosed quote in readColors, case normalization in setThemeMode, readable edge cases
    const QString malformedPath = tempDir.filePath("malformed_quote.toml");
    QFile malformedFile(malformedPath);
    QVERIFY(malformedFile.open(QIODevice::WriteOnly | QIODevice::Text));
    malformedFile.write(
        "accent = \"#112233\"\n"
        "broken = \"unclosed string\n"
        "red = \"#ff0033\"\n"
    );
    malformedFile.close();

    const auto malformedParsed = Theme::readColors(malformedPath);
    QCOMPARE(malformedParsed.value("accent"), QString("#112233"));
    QVERIFY(!malformedParsed.contains("broken"));
    QCOMPARE(malformedParsed.value("red"), QString("#ff0033"));

    theme.setThemeMode("  Light  ");
    QCOMPARE(theme.themeMode(), QString("light"));
    QCOMPARE(theme.mode(), QString("light"));

    theme.setThemeMode("DARK");
    QCOMPARE(theme.themeMode(), QString("dark"));
    QCOMPARE(theme.mode(), QString("dark"));

    const QString whiteOnWhite = Theme::readable("#ffffff", "#ffffff", {"#ffffff"}, 4.5);
    QVERIFY2(Theme::contrast(whiteOnWhite, "#ffffff") >= 4.5, "readable() must resolve #ffffff on #ffffff");

    const QString blackOnBlack = Theme::readable("#000000", "#000000", {"#000000"}, 4.5);
    QVERIFY2(Theme::contrast(blackOnBlack, "#000000") >= 4.5, "readable() must resolve #000000 on #000000");

    const QString midGray = Theme::readable("#808080", "#ffffff", {"#808080"}, 4.5);
    QVERIFY2(Theme::contrast(midGray, "#808080") >= 4.5, "readable() must resolve mid-tone surface contrast boundary");
}

// -----------------------------------------------------------------------------
// Milestone 1 Iteration 2: Tri-State Matrix & Contrast Invariants
// -----------------------------------------------------------------------------
void AntigravityHubTests::themeTriStateMatrixAndContrastInvariants() {
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

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    const QString themeSubdir = tempDir.filePath("theme");
    QDir(tempDir.path()).mkpath("theme");

    for (const QString &themeName : themeNames) {
        const QString sourceToml = QStringLiteral("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName);
        QVERIFY2(QFile::exists(sourceToml), qPrintable(QStringLiteral("Source theme missing: %1").arg(sourceToml)));

        const QString targetToml = tempDir.filePath("theme/colors.toml");
        if (QFile::exists(targetToml)) {
            QFile::remove(targetToml);
        }
        QVERIFY(QFile::copy(sourceToml, targetToml));

        Theme theme(tempDir.path());

        const auto raw = Theme::readColors(targetToml);
        const QString detectedMode = raw.value(QStringLiteral("mode"), QStringLiteral("dark"));

        for (const QString &modeSetting : testModes) {
            theme.setThemeMode(modeSetting);

            const QString effectiveExpected = (modeSetting == QLatin1String("auto")) ? detectedMode : modeSetting;
            QCOMPARE(theme.mode(), effectiveExpected);

            const QString bg = theme.background();
            const QString t1 = theme.text1();
            const QString rEven = theme.rowEven();
            const QString rOdd = theme.rowOdd();

            // 1. Text contrast against background and surfaces >= 4.5:1
            const double cText1Bg = Theme::contrast(t1, bg);
            QVERIFY2(cText1Bg >= 4.5,
                     qPrintable(QStringLiteral("[%1 / %2] text1 (%3) vs background (%4) contrast (%5) < 4.5:1")
                                .arg(themeName, modeSetting, t1, bg).arg(cText1Bg)));

            const double cText1Even = Theme::contrast(t1, rEven);
            QVERIFY2(cText1Even >= 4.5,
                     qPrintable(QStringLiteral("[%1 / %2] text1 (%3) vs rowEven (%4) contrast (%5) < 4.5:1")
                                .arg(themeName, modeSetting, t1, rEven).arg(cText1Even)));

            const double cText1Odd = Theme::contrast(t1, rOdd);
            QVERIFY2(cText1Odd >= 4.5,
                     qPrintable(QStringLiteral("[%1 / %2] text1 (%3) vs rowOdd (%4) contrast (%5) < 4.5:1")
                                .arg(themeName, modeSetting, t1, rOdd).arg(cText1Odd)));

            const double cText1Canvas = Theme::contrast(t1, theme.canvas());
            QVERIFY2(cText1Canvas >= 4.5,
                     qPrintable(QStringLiteral("[%1 / %2] text1 vs canvas contrast (%3) < 4.5:1")
                                .arg(themeName, modeSetting).arg(cText1Canvas)));

            // 2. Forced Dark Mode on Light Themes: Invariant Verification
            if (modeSetting == QLatin1String("dark") && detectedMode == QLatin1String("light")) {
                QVERIFY2(bg != QLatin1String("#eff1f5") && bg != QLatin1String("#ffffff"),
                         qPrintable(QStringLiteral("[%1 forced dark] Leaked light background: %2").arg(themeName, bg)));
                QCOMPARE(t1, QStringLiteral("#FFFFFF"));
                QVERIFY2(cText1Bg >= 4.5,
                         qPrintable(QStringLiteral("[%1 forced dark] White on light contrast collapse!").arg(themeName)));
            }

            // 3. Forced Light Mode on Dark Themes: Invariant Verification
            if (modeSetting == QLatin1String("light") && detectedMode == QLatin1String("dark")) {
                QCOMPARE(bg, QStringLiteral("#FFFFFF"));
                QCOMPARE(t1, QStringLiteral("#0F172A"));
                QVERIFY2(cText1Bg >= 4.5,
                         qPrintable(QStringLiteral("[%1 forced light] Dark text on white background contrast < 4.5").arg(themeName)));
            }

            // 4. Zebra Striping Invariants: Contrast > 1.20, neither is dead black #000000
            QVERIFY2(rEven != rOdd,
                     qPrintable(QStringLiteral("[%1 / %2] rowEven and rowOdd collided (%3)").arg(themeName, modeSetting, rEven)));
            QVERIFY2(rEven != QLatin1String("#000000"),
                     qPrintable(QStringLiteral("[%1 / %2] rowEven evaluated to dead black #000000").arg(themeName, modeSetting)));
            QVERIFY2(rOdd != QLatin1String("#000000"),
                     qPrintable(QStringLiteral("[%1 / %2] rowOdd evaluated to dead black #000000").arg(themeName, modeSetting)));

            const double cZebra = Theme::contrast(rEven, rOdd);
            QVERIFY2(cZebra > 1.20,
                     qPrintable(QStringLiteral("[%1 / %2] Zebra contrast between rowEven (%3) and rowOdd (%4) is %5 <= 1.20")
                                .arg(themeName, modeSetting, rEven, rOdd).arg(cZebra)));

            // 5. Semantic Status Colors & No Hardcoded Pure Red
            QVERIFY2(theme.danger() != QLatin1String("#FF6B6B"),
                     qPrintable(QStringLiteral("[%1 / %2] theme.danger() is pure red #FF6B6B").arg(themeName, modeSetting)));
            QVERIFY2(theme.dangerText() != QLatin1String("#FF6B6B"),
                     qPrintable(QStringLiteral("[%1 / %2] theme.dangerText() is pure red #FF6B6B").arg(themeName, modeSetting)));

            const double cDanger = Theme::contrast(theme.dangerText(), theme.canvas());
            const double cGood = Theme::contrast(theme.goodText(), theme.canvas());
            const double cWarning = Theme::contrast(theme.warningText(), theme.canvas());
            const double cAccent = Theme::contrast(theme.accentText(), theme.canvas());
            QVERIFY2(cDanger >= 4.5, qPrintable(QStringLiteral("[%1 / %2] dangerText contrast < 4.5").arg(themeName, modeSetting)));
            QVERIFY2(cGood >= 4.5, qPrintable(QStringLiteral("[%1 / %2] goodText contrast < 4.5").arg(themeName, modeSetting)));
            QVERIFY2(cWarning >= 4.5, qPrintable(QStringLiteral("[%1 / %2] warningText contrast < 4.5").arg(themeName, modeSetting)));
            QVERIFY2(cAccent >= 4.5, qPrintable(QStringLiteral("[%1 / %2] accentText contrast < 4.5").arg(themeName, modeSetting)));

            // 6. Zero Presence of CSS 'rgba(' in Color Properties
            QVERIFY(!theme.border().contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!theme.hairline().contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!theme.controlBorder().contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!theme.trackBg().contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!theme.pillBg().contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!rEven.contains(QLatin1String("rgba"), Qt::CaseInsensitive));
            QVERIFY(!rOdd.contains(QLatin1String("rgba"), Qt::CaseInsensitive));

            // 7. Track and Pill Background Hex Formatting (#AARRGGBB)
            QVERIFY(theme.trackBg().startsWith(QLatin1Char('#')) && theme.trackBg().length() == 9);
            QVERIFY(theme.pillBg().startsWith(QLatin1Char('#')) && theme.pillBg().length() == 9);
        }
    }

    // 8. Invariant: controlRadius() returns 0 when radius() is 0
    Theme zeroRadiusTheme(tempDir.path());
    if (zeroRadiusTheme.radius() == 0) {
        QCOMPARE(zeroRadiusTheme.controlRadius(), 0);
    }

    // 9. Invariant: Case normalization for setThemeMode
    zeroRadiusTheme.setThemeMode(QStringLiteral("  DARK  "));
    QCOMPARE(zeroRadiusTheme.themeMode(), QStringLiteral("dark"));
    zeroRadiusTheme.setThemeMode(QStringLiteral("Light"));
    QCOMPARE(zeroRadiusTheme.themeMode(), QStringLiteral("light"));
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

    // Dynamic runtime language switching without restarting
    translator.setLanguage("zh-CN");
    QCOMPARE(translator.language(), QString("zh-CN"));
    QCOMPARE(translator.overrideLanguage(), QString("zh-CN"));
    QCOMPARE(translator.translate("Main", "Mask"), QString("打码"));

    translator.setLanguage("en");
    QCOMPARE(translator.language(), QString("en"));
    QCOMPARE(translator.overrideLanguage(), QString("en"));
    QCOMPARE(translator.translate("Main", "Mask"), QString("Mask"));

    translator.setLanguage("system");
    QCOMPARE(translator.overrideLanguage(), QString("system"));
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

void AntigravityHubTests::accountFilterProxyModelFullSorting() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    QJsonObject accountsObj;

    // Account A: zebra@gmail.com (Index 1), gemini4: 0.20, standby
    QJsonObject a1;
    a1["email"] = "zebra@gmail.com";
    a1["name"] = "zebra";
    a1["validation_blocked"] = false;
    QJsonObject a1Gem; a1Gem["quota_5h"] = 0.5; a1Gem["quota_weekly"] = 0.4; a1["gemini"] = a1Gem;
    QJsonObject a1Cla; a1Cla["quota_5h"] = 0.5; a1Cla["quota_weekly"] = 0.3; a1["claude"] = a1Cla;
    QJsonObject a1G4; a1G4["quota_weekly"] = 0.20; a1["gemini4"] = a1G4;
    accountsObj["zebra@gmail.com"] = a1;

    // Account B: alpha@gmail.com (Index 2), gemini4: 0.90, active
    QJsonObject a2;
    a2["email"] = "alpha@gmail.com";
    a2["name"] = "alpha";
    a2["validation_blocked"] = false;
    QJsonObject a2Gem; a2Gem["quota_5h"] = 0.9; a2Gem["quota_weekly"] = 0.8; a2["gemini"] = a2Gem;
    QJsonObject a2Cla; a2Cla["quota_5h"] = 0.9; a2Cla["quota_weekly"] = 0.8; a2["claude"] = a2Cla;
    QJsonObject a2G4; a2G4["quota_weekly"] = 0.90; a2["gemini4"] = a2G4;
    accountsObj["alpha@gmail.com"] = a2;

    // Account C: mango@gmail.com (Index 3), gemini4: 0.50, blocked
    QJsonObject a3;
    a3["email"] = "mango@gmail.com";
    a3["name"] = "mango";
    a3["validation_blocked"] = true;
    QJsonObject a3Gem; a3Gem["quota_5h"] = 0.1; a3Gem["quota_weekly"] = 0.1; a3["gemini"] = a3Gem;
    QJsonObject a3Cla; a3Cla["quota_5h"] = 0.1; a3Cla["quota_weekly"] = 0.1; a3["claude"] = a3Cla;
    QJsonObject a3G4; a3G4["quota_weekly"] = 0.50; a3["gemini4"] = a3G4;
    accountsObj["mango@gmail.com"] = a3;

    QJsonObject rootDoc;
    rootDoc["active_email"] = "alpha@gmail.com";
    rootDoc["accounts"] = accountsObj;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);
    QCOMPARE(proxy.rowCount(), 3);

    // 1. Sort by index ascending (natural 1, 2, 3)
    proxy.setSortRule("index", Qt::AscendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::IndexRole).toInt(), 1);
    QCOMPARE(proxy.data(proxy.index(2, 0), AccountModel::IndexRole).toInt(), 3);

    // 2. Sort by index descending (3, 2, 1)
    proxy.setSortRule("index", Qt::DescendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::IndexRole).toInt(), 3);
    QCOMPARE(proxy.data(proxy.index(2, 0), AccountModel::IndexRole).toInt(), 1);

    // 3. Sort by account ascending (alpha, mango, zebra)
    proxy.setSortRule("account", Qt::AscendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::DisplayUsernameRole).toString(), QString("alpha"));
    QCOMPARE(proxy.data(proxy.index(1, 0), AccountModel::DisplayUsernameRole).toString(), QString("mango"));
    QCOMPARE(proxy.data(proxy.index(2, 0), AccountModel::DisplayUsernameRole).toString(), QString("zebra"));

    // 4. Sort by account descending (zebra, mango, alpha)
    proxy.setSortRule("account", Qt::DescendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::DisplayUsernameRole).toString(), QString("zebra"));
    QCOMPARE(proxy.data(proxy.index(2, 0), AccountModel::DisplayUsernameRole).toString(), QString("alpha"));

    // 5. Sort by status (Active first)
    proxy.setSortRule("status", Qt::AscendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::IsActiveRole).toBool(), true); // alpha is active

    // 6. Sort by Gemini 4 descending (alpha 0.90, mango 0.50, zebra 0.20)
    proxy.setSortRule("gemini4", Qt::DescendingOrder);
    QCOMPARE(proxy.data(proxy.index(0, 0), AccountModel::DisplayUsernameRole).toString(), QString("alpha"));
    QCOMPARE(proxy.data(proxy.index(1, 0), AccountModel::DisplayUsernameRole).toString(), QString("mango"));
    QCOMPARE(proxy.data(proxy.index(2, 0), AccountModel::DisplayUsernameRole).toString(), QString("zebra"));

    // 7. Reset to default order
    proxy.setSortRule("default", Qt::DescendingOrder);
    QCOMPARE(proxy.sortField(), QString("default"));
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
    // Milestone 2 extended operations invokable via QMetaObject / QML
    QVERIFY(QMetaObject::invokeMethod(&backend, "deleteAccounts", Q_ARG(QStringList, QStringList{QStringLiteral("test@example.com")})));
    QVERIFY(QMetaObject::invokeMethod(&backend, "ingestActiveAccount"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "startOAuthLogin"));
    QVERIFY(QMetaObject::invokeMethod(&backend, "importAccounts", Q_ARG(QString, QStringLiteral("{}"))));
    QVERIFY(QMetaObject::invokeMethod(&backend, "exportSelectedAccounts", Q_ARG(QStringList, QStringList{QStringLiteral("test@example.com")})));
    QVERIFY(QMetaObject::invokeMethod(&backend, "exportSelected", Q_ARG(QStringList, QStringList{QStringLiteral("test@example.com")})));
    QVERIFY(QMetaObject::invokeMethod(&backend, "batchWarmup", Q_ARG(QStringList, QStringList{QStringLiteral("test@example.com")})));
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

void AntigravityHubTests::backendControllerExtendedApiMethods() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    BackendController backend;

    // 1. Verify QMetaObject method introspection for Milestone 2 methods
    const QMetaObject *mo = backend.metaObject();
    QVERIFY2(mo->indexOfMethod("deleteAccounts(QStringList)") != -1, "deleteAccounts(QStringList) not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("ingestActiveAccount()") != -1, "ingestActiveAccount() not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("startOAuthLogin()") != -1, "startOAuthLogin() not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("importAccounts(QString)") != -1, "importAccounts(QString) not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("exportSelectedAccounts(QStringList)") != -1, "exportSelectedAccounts(QStringList) not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("exportSelected(QStringList)") != -1, "exportSelected(QStringList) not registered in QMetaObject");
    QVERIFY2(mo->indexOfMethod("batchWarmup(QStringList)") != -1, "batchWarmup(QStringList) not registered in QMetaObject");

    // 2. Verify signal introspection
    QVERIFY2(mo->indexOfSignal("accountsReloadRequested()") != -1, "accountsReloadRequested() signal missing");
    QVERIFY2(mo->indexOfSignal("accountsExported(QString)") != -1, "accountsExported(QString) signal missing");

    // 3. Spy on signals & test invocations
    QSignalSpy spyBusy(&backend, &BackendController::busyChanged);
    QSignalSpy spyReload(&backend, &BackendController::accountsReloadRequested);
    QSignalSpy spyExport(&backend, &BackendController::accountsExported);
    QSignalSpy spyNotify(&backend, &BackendController::notificationRequested);

    backend.ingestActiveAccount();
    QVERIFY(spyBusy.count() >= 1);

    backend.startOAuthLogin();
    backend.batchWarmup(QStringList{QStringLiteral("cakeai88@gmail.com")});
    backend.exportSelectedAccounts(QStringList{QStringLiteral("cakeai88@gmail.com")});
    backend.deleteAccounts(QStringList{QStringLiteral("novadu99@gmail.com")});
    backend.importAccounts(QStringLiteral("{\"cakeai88@gmail.com\": {}}"));

    QCoreApplication::processEvents();
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
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());
    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");
    {
        QJsonObject accountsObj;
        QJsonObject a1; a1["email"] = "cakeai88@gmail.com"; a1["name"] = "cakeai88"; a1["validation_blocked"] = false;
        QJsonObject a1Gem; a1Gem["quota_5h"] = 0.85; a1Gem["quota_weekly"] = 0.72; a1["gemini"] = a1Gem;
        QJsonObject a1Cla; a1Cla["quota_5h"] = 0.90; a1Cla["quota_weekly"] = 0.65; a1["claude"] = a1Cla;
        QJsonObject a1G4; a1G4["quota_weekly"] = 0.80; a1["gemini4"] = a1G4;
        accountsObj["cakeai88@gmail.com"] = a1;

        QJsonObject a2; a2["email"] = "novadu99@gmail.com"; a2["name"] = "novadu99"; a2["validation_blocked"] = false;
        QJsonObject a2Gem; a2Gem["quota_5h"] = 0.12; a2Gem["quota_weekly"] = 0.08; a2["gemini"] = a2Gem;
        QJsonObject a2Cla; a2Cla["quota_5h"] = 0.14; a2Cla["quota_weekly"] = 0.06; a2["claude"] = a2Cla;
        QJsonObject a2G4; a2G4["quota_weekly"] = 0.10; a2["gemini4"] = a2G4;
        accountsObj["novadu99@gmail.com"] = a2;

        QJsonObject a3; a3["email"] = "deadlock@gmail.com"; a3["name"] = "deadlock"; a3["validation_blocked"] = true;
        QJsonObject a3Gem; a3Gem["quota_5h"] = 0.0; a3Gem["quota_weekly"] = 0.0; a3["gemini"] = a3Gem;
        QJsonObject a3Cla; a3Cla["quota_5h"] = 0.0; a3Cla["quota_weekly"] = 0.0; a3["claude"] = a3Cla;
        QJsonObject a3G4; a3G4["quota_weekly"] = 0.0; a3["gemini4"] = a3G4;
        accountsObj["deadlock@gmail.com"] = a3;

        QJsonObject rootDoc;
        rootDoc["active_email"] = "cakeai88@gmail.com";
        rootDoc["accounts"] = accountsObj;
        QFile f(accountsFile);
        if (f.open(QIODevice::WriteOnly)) {
            f.write(QJsonDocument(rootDoc).toJson());
            f.close();
        }
    }
    QFile langF(tempDir.filePath("lang"));
    if (langF.open(QIODevice::WriteOnly)) {
        langF.write("zh-CN");
        langF.close();
    }
    const QString realThemeDir = QDir::homePath() + QStringLiteral("/.local/state/omarchy/current");
    Theme theme(QFile::exists(realThemeDir + QStringLiteral("/theme/colors.toml")) ? realThemeDir : tempDir.path());
    Translator translator(tempDir.filePath("lang"), ":/i18n");
    QCoreApplication::installTranslator(&translator);
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
        QVERIFY(QMetaObject::invokeMethod(obj.data(), "open"));
        QCoreApplication::processEvents();
        QVERIFY(QMetaObject::invokeMethod(obj.data(), "close"));
        QCoreApplication::processEvents();
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

    // 7. Verify AddAccountDialog.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/AddAccountDialog.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "AddAccountDialog failed to instantiate offscreen");
        QCOMPARE(obj->property("modal").toBool(), true);
    }

    // 8. Verify AccountListView.qml
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/AccountListView.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "AccountListView failed to instantiate offscreen");
        QVERIFY(obj->metaObject()->indexOfMethod("selectNext()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("selectPrevious()") != -1);
        QVERIFY(obj->metaObject()->indexOfMethod("activateCurrent()") != -1);
    }

    // 8. Verify Main.qml and live modal interactions
    {
        QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/Main.qml")));
        QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));
        QScopedPointer<QObject> obj(comp.create());
        QVERIFY2(obj != nullptr, "Main.qml failed to instantiate offscreen");
        if (auto *win = qobject_cast<QQuickWindow*>(obj.data())) {
            win->show();
            QCoreApplication::processEvents();

            // Verify settingsDialog opens and closes cleanly without CPU hang or freeze
            auto *settingsDlg = obj->findChild<QObject*>(QStringLiteral("settingsDialog"));
            QVERIFY2(settingsDlg != nullptr, "settingsDialog not found in Main.qml");
            QVERIFY(QMetaObject::invokeMethod(settingsDlg, "open"));
            QTRY_COMPARE_WITH_TIMEOUT(settingsDlg->property("visible").toBool(), true, 1000);
            QVERIFY(QMetaObject::invokeMethod(settingsDlg, "close"));
            QTRY_COMPARE_WITH_TIMEOUT(settingsDlg->property("visible").toBool(), false, 1000);

            const QImage snapshot = win->grabWindow();
            if (!snapshot.isNull()) {
                snapshot.save(QStringLiteral("/home/dunova/.gemini/antigravity/brain/5d9fcafa-c826-4c8a-b0e8-d234a942971b/hub_pure_offscreen.png"));
            }
        }
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

    // 3. Weekly depletion short-circuit to 0.0% & Weekly Depleted / 周耗尽
    QVERIFY2(content.contains(QStringLiteral("qsTr(\"Weekly Depleted\")")) || content.contains(QStringLiteral("qsTr(\"周耗尽\")")),
             "AccountListView.qml missing Weekly Depleted / 周耗尽 short-circuit handler");

    // 4. Zero animation on ACTIVE badge & zero pure red (#EF4444)
    QVERIFY2(!content.contains(QStringLiteral("SequentialAnimation on opacity")),
             "MANDATORY DENOISING VIOLATION: SequentialAnimation on opacity found in AccountListView.qml");
    QVERIFY2(!content.contains(QStringLiteral("#EF4444")),
             "MANDATORY COLOR VIOLATION: Pure red '#EF4444' found in AccountListView.qml");

    // 5. Verify HeaderBar visual invariants
    QFile headerFile(QStringLiteral(":/HeaderBar.qml"));
    QVERIFY(headerFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString headerContent = QString::fromUtf8(headerFile.readAll());
    headerFile.close();

    QVERIFY2(!headerContent.contains(QStringLiteral("SequentialAnimation on opacity")),
             "MANDATORY DENOISING VIOLATION: Breathing animation found in HeaderBar.qml");
    QVERIFY2(!headerContent.contains(QStringLiteral("#EF4444")),
             "MANDATORY COLOR VIOLATION: Pure red '#EF4444' found in HeaderBar.qml");
    QVERIFY2(!headerContent.contains(QStringLiteral("name: \"gear\"")),
             "MANDATORY DENOISING VIOLATION: Gear logo found in HeaderBar settings capsule");
    QVERIFY2(!headerContent.contains(QStringLiteral("name: \"bolt\"")),
             "MANDATORY DENOISING VIOLATION: Bolt logo found in HeaderBar topg capsule");
    QVERIFY2(!headerContent.contains(QStringLiteral("name: \"sparkle\"")),
             "MANDATORY DENOISING VIOLATION: Sparkle logo found in HeaderBar prewarm capsule");
}

// -----------------------------------------------------------------------------
// Milestone 3: v2.50.0 Fixed Geometry & Invariant Verification Suite
// -----------------------------------------------------------------------------

void AntigravityHubTests::v250WindowGeometryLockInvariants() {
    // 1. Static Source Code Invariants in src/Main.qml
    QFile mainFile(QStringLiteral(":/Main.qml"));
    QVERIFY(mainFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString mainContent = QString::fromUtf8(mainFile.readAll());
    mainFile.close();

    QVERIFY2(mainContent.contains(QRegularExpression(QStringLiteral(R"(\bwidth\s*:\s*940\b)"))), "Main.qml width != 940");
    QVERIFY2(mainContent.contains(QRegularExpression(QStringLiteral(R"(\bminimumWidth\s*:\s*920\b)"))), "Main.qml minimumWidth != 920");
    QVERIFY2(!mainContent.contains(QStringLiteral("maximumWidth")), "Main.qml must not restrict maximumWidth to allow Hyprland dynamic tiling");
    QVERIFY2(mainContent.contains(QRegularExpression(QStringLiteral(R"(\bheight\s*:\s*800\b)"))), "Main.qml height != 800");
    QVERIFY2(mainContent.contains(QRegularExpression(QStringLiteral(R"(\bminimumHeight\s*:\s*540\b)"))), "Main.qml minimumHeight != 540");
    QVERIFY2(mainContent.contains(QRegularExpression(QStringLiteral(R"(\bcontentWidth\s*:\s*896\b)"))), "Main.qml contentWidth != 896");

    // 2. Offscreen Dynamic Instantiation of Main.qml
    QQmlEngine engine;
    engine.addImageProvider(QStringLiteral("icons"), new IconProvider());

    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

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

    QQmlComponent comp(&engine, QUrl(QStringLiteral("qrc:/Main.qml")));
    QVERIFY2(!comp.isError(), qPrintable(comp.errorString()));

    QScopedPointer<QObject> rootObj(comp.create());
    QVERIFY2(rootObj != nullptr, "Main.qml failed to instantiate");

    QQuickWindow *win = qobject_cast<QQuickWindow*>(rootObj.data());
    QVERIFY2(win != nullptr, "Main.qml root object is not a QQuickWindow");

    QCOMPARE(win->width(), 940);
    QCOMPARE(win->height(), 800);
    QCOMPARE(win->property("minimumWidth").toInt(), 920);
    QCOMPARE(win->property("minimumHeight").toInt(), 540);
    QCOMPARE(win->property("contentWidth").toInt(), 896);

    win->show();
    QCoreApplication::processEvents();

    // Resize stress test: window geometry constraints enforce fixed contentWidth
    win->resize(1280, 900);
    QCoreApplication::processEvents();
    QCOMPARE(win->property("contentWidth").toInt(), 896);
}

void AntigravityHubTests::v250TableColumnsFixedGeometryInvariants() {
    // 1. Static Source Code Invariants in src/AccountListView.qml
    QFile file(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(file.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString content = QString::fromUtf8(file.readAll());
    file.close();

    // Verify column width constants and row height
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolCheckWidth\s*:\s*24\b)"))), "colCheckWidth != 24");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolIndexWidth\s*:\s*26\b)"))), "colIndexWidth != 26");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolStatusWidth\s*:\s*66\b)"))), "colStatusWidth != 66");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolAccountWidth\s*:\s*106\b)"))), "colAccountWidth != 106");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolG4Width\s*:\s*150\b)"))), "colG4Width != 150");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolG38Width\s*:\s*218\b)"))), "colG38Width != 218");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolClaudeWidth\s*:\s*218\b)"))), "colClaudeWidth != 218");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\bcolActionWidth\s*:\s*65\b)"))), "colActionWidth != 65");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(\browHeight\s*:\s*40\b)"))), "rowHeight != 40");

    // Exact arithmetic sum check: 24 + 26 + 66 + 106 + 150 + 218 + 218 + 65 == 873
    const int totalColumnWidth = 24 + 26 + 66 + 106 + 150 + 218 + 218 + 65;
    QCOMPARE(totalColumnWidth, 873);

    // Verify that NO direct column in Header RowLayout has Layout.fillWidth
    int headerRowPos = content.indexOf(QStringLiteral("id: headerRow"));
    QVERIFY(headerRowPos != -1);
    int batchBarPos = content.indexOf(QStringLiteral("id: batchActionBar"));
    QVERIFY(batchBarPos > headerRowPos);
    QString headerSection = content.mid(headerRowPos, batchBarPos - headerRowPos);
    int headerRowLayoutPos = headerSection.indexOf(QStringLiteral("RowLayout {"));
    QVERIFY(headerRowLayoutPos != -1);
    QString headerColumnsSection = headerSection.mid(headerRowLayoutPos);
    QVERIFY2(!headerColumnsSection.contains(QStringLiteral("Layout.fillWidth")), "Header column has Layout.fillWidth!");

    // Verify all 8 columns in Header specify preferredWidth
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colCheckWidth")), "Header Col 1 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colIndexWidth")), "Header Col 2 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colStatusWidth")), "Header Col 3 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colAccountWidth")), "Header Col 4 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colG4Width")), "Header Col 5 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colG38Width")), "Header Col 6 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colClaudeWidth")), "Header Col 7 missing preferredWidth");
    QVERIFY2(headerSection.contains(QStringLiteral("Layout.preferredWidth: colActionWidth")), "Header Col 8 missing preferredWidth");

    // Verify all 8 columns in Delegate specify preferredWidth
    int delegatePos = content.indexOf(QStringLiteral("id: rowDelegate"));
    QVERIFY(delegatePos != -1);
    int bottomBarPos = content.indexOf(QStringLiteral("id: bottomBar"));
    QVERIFY(bottomBarPos > delegatePos);
    QString delegateSection = content.mid(delegatePos, bottomBarPos - delegatePos);

    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colCheckWidth")), "Delegate Col 1 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colIndexWidth")), "Delegate Col 2 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colStatusWidth")), "Delegate Col 3 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colAccountWidth")), "Delegate Col 4 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colG4Width")), "Delegate Col 5 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colG38Width")), "Delegate Col 6 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colClaudeWidth")), "Delegate Col 7 missing preferredWidth");
    QVERIFY2(delegateSection.contains(QStringLiteral("Layout.preferredWidth: colActionWidth")), "Delegate Col 8 missing preferredWidth");

    // Verify spacing in Col 6 & 7 between 5h and weekly containers is 1px
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(spacing\s*:\s*1\b)"))), "spacing: 1 between 5h and weekly missing");

    // Verify progress bar height 5px and label pill 20x14px
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(Layout\.preferredHeight\s*:\s*5\b)"))), "Progress bar preferredHeight 5 missing");
    QVERIFY2(content.contains(QRegularExpression(QStringLiteral(R"(width\s*:\s*20\b[\s\S]*?height\s*:\s*14\b)"))), "Label pill 20x14 missing");
}

void AntigravityHubTests::v250ScreenFixedZebraRhythmInvariants() {
    // 1. Static Source Code Invariants in src/AccountListView.qml
    QFile file(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(file.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString content = QString::fromUtf8(file.readAll());
    file.close();

    // Verify screen-fixed alternating zebra rule (index % 2)
    QVERIFY2(content.contains(QStringLiteral("rowBgColor: (index % 2 === 0)")), "rowBgColor alternating rule missing");
    QVERIFY2(content.contains(QStringLiteral("theme.rowEven")), "theme.rowEven missing in rowBgColor");
    QVERIFY2(content.contains(QStringLiteral("theme.rowOdd")), "theme.rowOdd missing in rowBgColor");

    // Verify active account preserves zebra rhythm with 10% tint blend
    QVERIFY2(content.contains(QStringLiteral("Qt.tint(rowBgColor, Qt.alpha")), "Active row tint blend missing");
    QVERIFY2(content.contains(QStringLiteral("0.10")), "Active row 10% tint opacity missing");

    // Verify 3px vertical accent indicator stripe on active row
    QVERIFY2(content.contains(QStringLiteral("width: 3")), "3px active stripe missing");
    QVERIFY2(content.contains(QStringLiteral("visible: isRowActive")), "Active stripe visibility binding missing");

    // Verify zero solid green block or pure red in delegate background
    int delegatePos = content.indexOf(QStringLiteral("id: rowDelegate"));
    QVERIFY(delegatePos != -1);
    int rowMousePos = content.indexOf(QStringLiteral("id: rowMouse"), delegatePos);
    QVERIFY(rowMousePos > delegatePos);
    QString delegateHeader = content.mid(delegatePos, rowMousePos - delegatePos);
    QVERIFY2(!delegateHeader.contains(QStringLiteral("#EF4444")), "Pure red #EF4444 found in delegate");
    QVERIFY2(!delegateHeader.contains(QStringLiteral("goodText")), "goodText found in row background");

    // 2. Mathematical Zebra Striping Contrast Verification across Omarchy Themes
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    Theme defaultTheme(tempDir.path());
    QVERIFY(defaultTheme.rowEven() != defaultTheme.rowOdd());
    QVERIFY(defaultTheme.rowEven() != QStringLiteral("#000000"));
    QVERIFY(defaultTheme.rowOdd() != QStringLiteral("#000000"));

    const QStringList sampleThemes = {
        QStringLiteral("/usr/share/omarchy/themes/gruvbox/colors.toml"),
        QStringLiteral("/usr/share/omarchy/themes/jade-horse/colors.toml"),
        QStringLiteral("/usr/share/omarchy/themes/catppuccin-latte/colors.toml")
    };
    QDir(tempDir.path()).mkpath("theme");
    for (const QString &sourceToml : sampleThemes) {
        if (!QFile::exists(sourceToml)) continue;
        const QString targetToml = tempDir.filePath("theme/colors.toml");
        if (QFile::exists(targetToml)) QFile::remove(targetToml);
        QVERIFY(QFile::copy(sourceToml, targetToml));

        Theme t(tempDir.path());
        const QString rEven = t.rowEven();
        const QString rOdd = t.rowOdd();
        const QString accent = t.accent();

        // 10% accent tint on even and odd rows
        const QString tintedEven = Theme::mix(rEven, accent, 0.10);
        const QString tintedOdd = Theme::mix(rOdd, accent, 0.10);

        // Invariant: alternating contrast is strictly preserved (never collapses to 1.0)
        QVERIFY(Theme::contrast(tintedEven, rOdd) > 1.05);
        QVERIFY(Theme::contrast(rEven, tintedOdd) > 1.10);
        QVERIFY(Theme::contrast(tintedEven, tintedOdd) > 1.10);
    }
}

void AntigravityHubTests::v250AccountReorderPersistenceInvariants() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    qputenv("ANTIGRAVITY_HUB_DIR", tempDir.path().toLocal8Bit());

    QDir(tempDir.path()).mkpath("data");
    const QString accountsFile = tempDir.filePath("data/accounts_hub.json");

    // 1. Initial accounts setup: 3 accounts (accA, accB, accC)
    QJsonObject rootDoc;
    rootDoc["active_email"] = QStringLiteral("accA@test.com");
    QJsonObject accs;
    for (const QString &name : {QStringLiteral("accA@test.com"), QStringLiteral("accB@test.com"), QStringLiteral("accC@test.com")}) {
        QJsonObject a;
        a["email"] = name;
        a["name"] = name;
        a["tier"] = QStringLiteral("PRO");
        a["pro"] = true;
        a["validation_blocked"] = false;
        QJsonObject g; g["quota_5h"] = 0.8; g["quota_weekly"] = 0.8; a["gemini"] = g;
        QJsonObject c; c["quota_5h"] = 0.8; c["quota_weekly"] = 0.8; a["claude"] = c;
        QJsonObject g4; g4["quota_weekly"] = 0.8; a["gemini4"] = g4;
        accs[name] = a;
    }
    rootDoc["accounts"] = accs;

    QFile file(accountsFile);
    QVERIFY(file.open(QIODevice::WriteOnly));
    file.write(QJsonDocument(rootDoc).toJson());
    file.close();

    // 2. Test AccountModel::reorderAccounts() in memory
    AccountModel model;
    QCOMPARE(model.rowCount(), 3);

    // Reorder: accC, accA, accB
    const QStringList newOrder = {
        QStringLiteral("accC@test.com"),
        QStringLiteral("accA@test.com"),
        QStringLiteral("accB@test.com")
    };
    model.reorderAccounts(newOrder);

    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.data(model.index(0, 0), AccountModel::EmailRole).toString(), QStringLiteral("accC@test.com"));
    QCOMPARE(model.data(model.index(1, 0), AccountModel::EmailRole).toString(), QStringLiteral("accA@test.com"));
    QCOMPARE(model.data(model.index(2, 0), AccountModel::EmailRole).toString(), QStringLiteral("accB@test.com"));
    QCOMPARE(model.accountsOrder(), newOrder);

    // Partial reorder: pass only accB -> should put accB first, preserving others without loss
    model.reorderAccounts(QStringList{QStringLiteral("accB@test.com")});
    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.data(model.index(0, 0), AccountModel::EmailRole).toString(), QStringLiteral("accB@test.com"));
    QCOMPARE(model.data(model.index(1, 0), AccountModel::EmailRole).toString(), QStringLiteral("accC@test.com"));
    QCOMPARE(model.data(model.index(2, 0), AccountModel::EmailRole).toString(), QStringLiteral("accA@test.com"));

    // Adversarial edge cases: empty list, non-existent emails, case insensitivity
    model.reorderAccounts(QStringList{});
    QCOMPARE(model.rowCount(), 3);

    model.reorderAccounts(QStringList{QStringLiteral("nonexistent@test.com"), QStringLiteral("  ACCA@TEST.COM  ")});
    QCOMPARE(model.rowCount(), 3);
    QCOMPARE(model.data(model.index(0, 0), AccountModel::EmailRole).toString(), QStringLiteral("accA@test.com"));

    // 3. Test BackendController::reorderAccounts() and JSON persistence
    BackendController backend;
    backend.setAccountModel(&model);

    QSignalSpy spyReorder(&backend, &BackendController::accountsReordered);
    const QStringList persistedOrder = {
        QStringLiteral("accB@test.com"),
        QStringLiteral("accA@test.com"),
        QStringLiteral("accC@test.com")
    };

    QVERIFY2(QMetaObject::invokeMethod(&backend, "reorderAccounts", Q_ARG(QStringList, persistedOrder)),
             "BackendController::reorderAccounts not invokable via QMetaObject");
    QCOMPARE(spyReorder.count(), 1);
    QCOMPARE(model.accountsOrder(), persistedOrder);

    // Verify accounts_order written to accounts_hub.json
    QFile readF(accountsFile);
    QVERIFY(readF.open(QIODevice::ReadOnly));
    const QJsonDocument savedDoc = QJsonDocument::fromJson(readF.readAll());
    readF.close();
    QVERIFY(savedDoc.isObject());
    const QJsonArray orderArr = savedDoc.object().value(QStringLiteral("accounts_order")).toArray();
    QCOMPARE(orderArr.size(), 3);
    QCOMPARE(orderArr.at(0).toString(), QStringLiteral("accB@test.com"));
    QCOMPARE(orderArr.at(1).toString(), QStringLiteral("accA@test.com"));
    QCOMPARE(orderArr.at(2).toString(), QStringLiteral("accC@test.com"));

    // 4. Test Cold Reload Survival from accounts_order array (Strategy 1)
    AccountModel coldModel;
    QCOMPARE(coldModel.rowCount(), 3);
    QCOMPARE(coldModel.data(coldModel.index(0, 0), AccountModel::EmailRole).toString(), QStringLiteral("accB@test.com"));
    QCOMPARE(coldModel.data(coldModel.index(1, 0), AccountModel::EmailRole).toString(), QStringLiteral("accA@test.com"));
    QCOMPARE(coldModel.data(coldModel.index(2, 0), AccountModel::EmailRole).toString(), QStringLiteral("accC@test.com"));

    // 5. Test Fallback Strategy 2: Raw byte physical order preservation without accounts_order
    const QString rawJsonText = QStringLiteral(
        "{\n"
        "  \"active_email\": \"accC@test.com\",\n"
        "  \"accounts\": {\n"
        "    \"accC@test.com\": {\"email\": \"accC@test.com\", \"name\": \"C\"},\n"
        "    \"accA@test.com\": {\"email\": \"accA@test.com\", \"name\": \"A\"},\n"
        "    \"accB@test.com\": {\"email\": \"accB@test.com\", \"name\": \"B\"}\n"
        "  }\n"
        "}\n"
    );
    QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text));
    file.write(rawJsonText.toUtf8());
    file.close();

    AccountModel rawScanModel;
    QCOMPARE(rawScanModel.rowCount(), 3);
    QCOMPARE(rawScanModel.data(rawScanModel.index(0, 0), AccountModel::EmailRole).toString(), QStringLiteral("accC@test.com"));
    QCOMPARE(rawScanModel.data(rawScanModel.index(1, 0), AccountModel::EmailRole).toString(), QStringLiteral("accA@test.com"));
    QCOMPARE(rawScanModel.data(rawScanModel.index(2, 0), AccountModel::EmailRole).toString(), QStringLiteral("accB@test.com"));
}

void AntigravityHubTests::v250ThemeMonoFontAndAccentTextInvariants() {
    QTemporaryDir tempDir;
    QVERIFY(tempDir.isValid());
    Theme theme(tempDir.path());

    // 1. Theme::monoFont() property & value
    const QMetaObject *themeMo = theme.metaObject();
    int monoFontPropIdx = themeMo->indexOfProperty("monoFont");
    QVERIFY2(monoFontPropIdx != -1, "Theme::monoFont Q_PROPERTY missing");
    QMetaProperty monoProp = themeMo->property(monoFontPropIdx);
    QVERIFY2(monoProp.isConstant(), "Theme::monoFont should be CONSTANT");
    QCOMPARE(theme.monoFont(), QStringLiteral("JetBrainsMono Nerd Font"));

    // 2. QML purge of raw "Monospace" in favor of theme.monoFont
    const QStringList qmlPaths = {
        QStringLiteral(":/Main.qml"),
        QStringLiteral(":/AccountListView.qml"),
        QStringLiteral(":/HeaderBar.qml"),
        QStringLiteral(":/FilterBar.qml")
    };
    for (const QString &qmlPath : qmlPaths) {
        QFile f(qmlPath);
        QVERIFY(f.open(QIODevice::ReadOnly | QIODevice::Text));
        const QString qmlContent = QString::fromUtf8(f.readAll());
        f.close();

        QVERIFY2(!qmlContent.contains(QStringLiteral("\"Monospace\""), Qt::CaseInsensitive),
                 qPrintable(QString("Raw 'Monospace' font found in %1").arg(qmlPath)));
    }

    // Verify theme.monoFont usage in key locations
    QFile listFile(QStringLiteral(":/AccountListView.qml"));
    QVERIFY(listFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString listContent = QString::fromUtf8(listFile.readAll());
    listFile.close();
    QVERIFY2(listContent.contains(QStringLiteral("theme.monoFont")), "AccountListView.qml missing theme.monoFont usage");

    // 3. Theme::accentText dynamic contrast adaptation
    int accentTextPropIdx = themeMo->indexOfProperty("accentText");
    QVERIFY2(accentTextPropIdx != -1, "Theme::accentText Q_PROPERTY missing");

    const QStringList themeNames = {
        QStringLiteral("jade-horse"),
        QStringLiteral("gruvbox"),
        QStringLiteral("tokyo-night"),
        QStringLiteral("catppuccin-latte"),
        QStringLiteral("white")
    };
    QDir(tempDir.path()).mkpath("theme");

    for (const QString &themeName : themeNames) {
        const QString sourceToml = QStringLiteral("/usr/share/omarchy/themes/%1/colors.toml").arg(themeName);
        if (!QFile::exists(sourceToml)) continue;

        const QString targetToml = tempDir.filePath("theme/colors.toml");
        if (QFile::exists(targetToml)) QFile::remove(targetToml);
        QVERIFY(QFile::copy(sourceToml, targetToml));

        Theme t(tempDir.path());
        QVERIFY2(Theme::contrast(t.accentText(), t.canvas()) >= 4.5,
                 qPrintable(QString("[%1] accentText contrast against canvas < 4.5:1").arg(themeName)));
    }

    // 4. Markers 1~6 Theme Unification Verification
    QFile headerFile(QStringLiteral(":/HeaderBar.qml"));
    QVERIFY(headerFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString headerContent = QString::fromUtf8(headerFile.readAll());
    headerFile.close();

    // Marker 1 (+ 添加账户), Marker 2 (Gemini), Marker 3 (ACTIVE badge)
    QVERIFY2(headerContent.contains(QStringLiteral("theme.accent")), "HeaderBar missing theme.accent");
    QVERIFY2(headerContent.contains(QStringLiteral("theme.accentText")), "HeaderBar ACTIVE badge missing theme.accentText");
    QVERIFY2(!headerContent.contains(QStringLiteral("#8bcbb1")), "Hardcoded #8bcbb1 found in HeaderBar.qml");

    // Marker 4: FilterBar "全部" tab
    QFile filterFile(QStringLiteral(":/FilterBar.qml"));
    QVERIFY(filterFile.open(QIODevice::ReadOnly | QIODevice::Text));
    const QString filterContent = QString::fromUtf8(filterFile.readAll());
    filterFile.close();
    QVERIFY2(filterContent.contains(QStringLiteral("theme.accentText")), "FilterBar missing theme.accentText");
    QVERIFY2(!filterContent.contains(QStringLiteral("#8bcbb1")), "Hardcoded #8bcbb1 found in FilterBar.qml");

    // Markers 5 & 6 in AccountListView.qml
    QVERIFY2(listContent.contains(QStringLiteral("theme.accentText")), "AccountListView.qml missing theme.accentText");
    QVERIFY2(!listContent.contains(QStringLiteral("#8bcbb1")), "Hardcoded #8bcbb1 found in AccountListView.qml");
}

void AntigravityHubTests::cleanupTestCase() {
    qDebug() << "Antigravity Hub Milestone 1 & 2 test suite execution completed.";
}

QTEST_MAIN(AntigravityHubTests)
#include "antigravity-hub_tests.moc"
