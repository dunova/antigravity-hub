#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QIcon>

#include "theme.h"
#include "translator.h"
#include "backend.h"
#include "models.h"
#include "iconprovider.h"

int main(int argc, char *argv[])
{
    // 1. Initialize GUI Application
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("antigravity-hub"));
    app.setApplicationVersion(QStringLiteral("2.47.0"));
    app.setOrganizationName(QStringLiteral("Omarchy"));
    app.setOrganizationDomain(QStringLiteral("omarchy.org"));

    // Crucial Omarchy / Wayland desktop binding:
    // Guarantees Hyprland window rules 'class:^(antigravity-hub)$' and XDG taskbar matching
    app.setDesktopFileName(QStringLiteral("antigravity-hub"));
    app.setWindowIcon(QIcon::fromTheme(QStringLiteral("antigravity-hub")));

    // 2. Set Qt Quick Controls 2 Style (must precede QML engine creation)
    QQuickStyle::setStyle(QStringLiteral("Material"));

    // 3. Register QML Types for QML Type System & Enums
    qmlRegisterType<AccountModel>("AntigravityHub", 1, 0, "AccountModel");
    qmlRegisterType<AccountFilterProxyModel>("AntigravityHub", 1, 0, "AccountFilterProxyModel");
    qmlRegisterType<BackendController>("AntigravityHub", 1, 0, "BackendController");
    qmlRegisterUncreatableType<Theme>("AntigravityHub", 1, 0, "Theme",
        QStringLiteral("Theme is instantiated in C++ and exposed via contextProperty"));
    qmlRegisterUncreatableType<Translator>("AntigravityHub", 1, 0, "Translator",
        QStringLiteral("Translator is instantiated in C++ and exposed via contextProperty"));

    // 4. Instantiate Core C++ Engines & Controllers (RAII on stack)
    Theme theme;

    Translator translator;
    app.installTranslator(&translator);

    BackendController backend;

    AccountModel accountModel;
    AccountFilterProxyModel proxyModel;
    proxyModel.setSourceModel(&accountModel);

    // Synchronize masking toggle between BackendController and AccountModel
    QObject::connect(&backend, &BackendController::maskedChanged,
                     [&backend, &accountModel]() {
        accountModel.setIsMasked(backend.isMasked());
    });
    QObject::connect(&accountModel, &AccountModel::isMaskedChanged,
                     [&backend](bool masked) {
        if (backend.isMasked() != masked) {
            backend.setMasked(masked);
        }
    });

    // Synchronize themeMode between BackendController and Theme
    QObject::connect(&backend, &BackendController::themeModeChanged,
                     [&backend, &theme]() {
        theme.setThemeMode(backend.themeMode());
    });

    // 5. Initialize QML Application Engine
    QQmlApplicationEngine engine;
    engine.addImageProvider(QStringLiteral("icons"), new IconProvider());

    // Zero-restart dynamic internationalization hot-reload
    QObject::connect(&translator, &Translator::changed,
                     &engine, &QQmlEngine::retranslate);

    // 6. Inject Singletons and Models into QML Root Context
    QQmlContext *rootCtx = engine.rootContext();
    rootCtx->setContextProperty(QStringLiteral("theme"), &theme);
    rootCtx->setContextProperty(QStringLiteral("translator"), &translator);
    rootCtx->setContextProperty(QStringLiteral("backend"), &backend);
    rootCtx->setContextProperty(QStringLiteral("backendController"), &backend); // Defensive alias
    rootCtx->setContextProperty(QStringLiteral("accountModel"), &accountModel);
    rootCtx->setContextProperty(QStringLiteral("proxyModel"), &proxyModel);
    rootCtx->setContextProperty(QStringLiteral("accountFilterProxyModel"), &proxyModel); // Defensive alias

    // 7. Load Main QML Scene
    const QUrl url(QStringLiteral("qrc:/Main.qml"));
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreated,
                     &app, [url](QObject *obj, const QUrl &objUrl) {
        if (!obj && url == objUrl) {
            QCoreApplication::exit(-1);
        }
    }, Qt::QueuedConnection);

    engine.load(url);
    if (engine.rootObjects().isEmpty()) {
        return -1;
    }

    // 8. Execute Application Event Loop
    return app.exec();
}
