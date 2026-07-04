# -*- coding: utf-8 -*-

from qgis.PyQt.QtGui import QGuiApplication


def display_metrics_text():
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 'DPI: - / 表示倍率: -'
    dpi = screen.logicalDotsPerInch()
    scale = dpi / 96.0 * 100.0
    return 'DPI: {0:.0f} / 表示倍率: {1:.0f}%'.format(dpi, scale)


def dpi_scale_factor():
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0
    return max(0.75, screen.logicalDotsPerInch() / 96.0)


def dpi_px(value):
    return max(1, int(round(value * dpi_scale_factor())))
