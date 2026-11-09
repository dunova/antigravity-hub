#include "iconprovider.h"

#include <QFile>
#include <QImage>
#include <QPainter>
#include <QSvgRenderer>

IconProvider::IconProvider() : QQuickImageProvider(QQuickImageProvider::Image) {}

QImage IconProvider::requestImage(const QString &id, QSize *size, const QSize &requestedSize) {
    const QString name = id.section('?', 0, 0);
    const QString color = id.section("color=", 1, 1);
    const QSize target = requestedSize.isValid() && !requestedSize.isEmpty() ? requestedSize : QSize(48, 48);

    QImage image(target, QImage::Format_ARGB32_Premultiplied);
    image.fill(Qt::transparent);

    QFile file(":/assets/icons/" + name + ".svg");
    if (file.open(QIODevice::ReadOnly)) {
        QByteArray svg = file.readAll();
        QByteArray replaceColor = color.isEmpty() ? QByteArray("#ffffff") : ("#" + color.toLatin1());
        svg.replace("currentColor", replaceColor);
        QSvgRenderer renderer(svg);
        QPainter painter(&image);
        renderer.render(&painter);
    }
    if (size)
        *size = target;
    return image;
}
