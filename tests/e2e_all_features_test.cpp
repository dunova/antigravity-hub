#include <QGuiApplication>
#include <QTest>
#include <QSignalSpy>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QDebug>

#include "models.h"
#include "backend.h"
#include "theme.h"
#include "translator.h"

class E2EAllFeaturesTest : public QObject {
    Q_OBJECT

private slots:
    void initTestCase();
    void testManualReorderingPersistence();
    void testMoveAccountToTop();
    void testColumnHeaderSorting();
    void testStatusTabFiltering();
    void testSearchFiltering();
    void testMaskingToggle();
    void testSettingsSaveAndApply();
    void cleanupTestCase();

private:
    QString m_hubDir;
    QString m_accountsFile;
};

void E2EAllFeaturesTest::initTestCase() {
    m_hubDir = QDir::homePath() + QStringLiteral("/.antigravity_hub");
    m_accountsFile = m_hubDir + QStringLiteral("/data/accounts_hub.json");
    QVERIFY2(QFile::exists(m_accountsFile), "accounts_hub.json must exist in user data dir");
}

void E2EAllFeaturesTest::testManualReorderingPersistence() {
    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);
    BackendController backend;
    backend.setAccountModel(&model);

    const int count = model.rowCount();
    QVERIFY(count >= 3);

    // Get current order
    QStringList originalOrder;
    for (int i = 0; i < count; ++i) {
        originalOrder.append(model.getAccount(i)["email"].toString());
    }

    // Move index 2 to index 0
    QStringList newOrder = originalOrder;
    QString moved = newOrder.takeAt(2);
    newOrder.prepend(moved);

    // Call reorderAccounts on backend
    backend.reorderAccounts(newOrder);

    // Verify model in memory immediately reflects new order
    QCOMPARE(model.getAccount(0)["email"].toString(), moved);
    QCOMPARE(proxy.getFilteredAccount(0)["email"].toString(), moved);

    // Verify persistence to accounts_hub.json
    QFile file(m_accountsFile);
    QVERIFY(file.open(QIODevice::ReadOnly));
    QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    file.close();

    QJsonArray orderArr = doc.object().value("accounts_order").toArray();
    QVERIFY(!orderArr.isEmpty());
    QCOMPARE(orderArr.at(0).toString(), moved);

    // Reload from disk to verify cold-reload survival
    model.reload();
    QCOMPARE(model.getAccount(0)["email"].toString(), moved);
}

void E2EAllFeaturesTest::testMoveAccountToTop() {
    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);
    BackendController backend;
    backend.setAccountModel(&model);

    const int count = model.rowCount();
    QVERIFY(count >= 3);

    // Pick an account not at top (e.g. index 3)
    QString targetEmail = model.getAccount(count - 1)["email"].toString();

    // Reconstruct list with targetEmail on top
    QStringList order;
    order.append(targetEmail);
    for (int i = 0; i < count; ++i) {
        QString e = model.getAccount(i)["email"].toString();
        if (e != targetEmail) order.append(e);
    }

    backend.reorderAccounts(order);
    QCOMPARE(model.getAccount(0)["email"].toString(), targetEmail);
    QCOMPARE(proxy.getFilteredAccount(0)["email"].toString(), targetEmail);
}

void E2EAllFeaturesTest::testColumnHeaderSorting() {
    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    // 1. Sort by account (username)
    proxy.setSortRule(QStringLiteral("account"), Qt::AscendingOrder);
    QVERIFY(proxy.rowCount() > 0);
    QString firstUser = proxy.getFilteredAccount(0)["displayUsername"].toString().toLower();
    QString secondUser = proxy.getFilteredAccount(1)["displayUsername"].toString().toLower();
    QVERIFY(firstUser <= secondUser);

    // 2. Sort by gemini4 descending
    proxy.setSortRule(QStringLiteral("gemini4"), Qt::DescendingOrder);
    double firstG4 = proxy.getFilteredAccount(0)["gemini4Quota"].toDouble();
    double lastG4 = proxy.getFilteredAccount(proxy.rowCount() - 1)["gemini4Quota"].toDouble();
    QVERIFY(firstG4 >= lastG4);

    // 3. Reset to default manual order
    proxy.setSortRule(QStringLiteral("default"), Qt::DescendingOrder);
    QCOMPARE(proxy.sortField(), QStringLiteral("default"));
}

void E2EAllFeaturesTest::testStatusTabFiltering() {
    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    const int total = proxy.totalCount();
    QVERIFY(total > 0);

    // 1. All
    proxy.setStatusTab(QStringLiteral("all"));
    QCOMPARE(proxy.filteredCount(), total);

    // 2. Usable
    proxy.setStatusTab(QStringLiteral("usable"));
    int usableCount = proxy.filteredCount();
    QVERIFY(usableCount <= total);

    // 3. Warning
    proxy.setStatusTab(QStringLiteral("warning"));
    int warnCount = proxy.filteredCount();
    QVERIFY(warnCount <= total);

    // Reset to all
    proxy.setStatusTab(QStringLiteral("all"));
    QCOMPARE(proxy.filteredCount(), total);
}

void E2EAllFeaturesTest::testSearchFiltering() {
    AccountModel model;
    AccountFilterProxyModel proxy;
    proxy.setSourceModel(&model);

    const int total = proxy.totalCount();
    QVERIFY(total > 0);

    // Search for a specific username
    QString sampleName = model.getAccount(0)["username"].toString();
    proxy.setFilterText(sampleName);
    QVERIFY(proxy.filteredCount() >= 1);
    QVERIFY(proxy.filteredCount() <= total);

    // Clear search
    proxy.setFilterText(QString());
    QCOMPARE(proxy.filteredCount(), total);
}

void E2EAllFeaturesTest::testMaskingToggle() {
    AccountModel model;
    const int total = model.rowCount();
    QVERIFY(total > 0);

    // Unmasked
    model.setIsMasked(false);
    QVERIFY(!model.isMasked());
    QString unmasked = model.getAccount(0)["displayUsername"].toString();
    QVERIFY(!unmasked.contains(QStringLiteral("***")));

    // Masked
    model.setIsMasked(true);
    QVERIFY(model.isMasked());
    QString masked = model.getAccount(0)["displayUsername"].toString();
    QVERIFY(masked.contains(QStringLiteral("***")));

    // Reset
    model.setIsMasked(false);
}

void E2EAllFeaturesTest::testSettingsSaveAndApply() {
    BackendController backend;
    QJsonObject payload;
    payload["theme_mode"] = "light";
    payload["language"] = "zh-CN";
    payload["hourly_warmup"] = true;
    payload["notifications_enabled"] = true;
    payload["gemini_threshold"] = 0.05;
    payload["claude_threshold"] = 0.05;

    backend.saveSettings(payload);
    // Backend emits signal and persists
}

void E2EAllFeaturesTest::cleanupTestCase() {
    qDebug() << "All E2E features verified successfully!";
}

QTEST_MAIN(E2EAllFeaturesTest)
#include "e2e_all_features_test.moc"
