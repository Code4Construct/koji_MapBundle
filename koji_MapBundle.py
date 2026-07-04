# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .koji_MapBundle_tool import MapSharingTool


class KojiMapBundle:
    """QGIS plugin entry point for 地図バンドル."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.tool = None
        self.menu_title = self.tr(u'&地図バンドル')

        locale = QSettings().value('locale/userLocale', '')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'KojiMapBundle_{}.qm'.format(locale),
        )

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

    def tr(self, message):
        return QCoreApplication.translate('KojiMapBundle', message)

    def initGui(self):
        icon = QIcon(os.path.join(self.plugin_dir, 'icon.png'))
        self.main_action = QAction(
            icon,
            self.tr(u'地図バンドル'),
            self.iface.mainWindow(),
        )
        self.main_action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.main_action)
        self.iface.addPluginToMenu(self.menu_title, self.main_action)
        self.actions.append(self.main_action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu_title, action)
            self.iface.removeToolBarIcon(action)

        if self.tool is not None and getattr(self.tool, 'dlg', None) is not None:
            self.tool.dlg.close()
            self.tool.dlg = None

    def run(self):
        try:
            if self.tool is None:
                self.tool = MapSharingTool(self.iface)
            self.tool.run()
        except Exception as exc:  # pragma: no cover - shown inside QGIS
            QMessageBox.critical(
                self.iface.mainWindow(),
                self.tr(u'地図バンドル'),
                self.tr(u'Failed to start tool: {0}').format(exc),
            )

