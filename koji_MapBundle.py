# -*- coding: utf-8 -*-

import os

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from . import koji_MapBundle_i18n as i18n
from .koji_MapBundle_tool import MapSharingTool


class KojiMapBundle:
    """QGIS plugin entry point for 地図バンドル."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.tool = None
        self.menu_title = i18n.tr('menu_title')

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
            i18n.tr('tool_title'),
            self.iface.mainWindow(),
        )
        self.main_action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.main_action)
        self.iface.addPluginToMenu(self.menu_title, self.main_action)
        self.actions.append(self.main_action)

    def refresh_language(self):
        old_menu_title = self.menu_title
        self.menu_title = i18n.tr('menu_title')
        if hasattr(self, 'main_action'):
            self.main_action.setText(i18n.tr('tool_title'))
            if old_menu_title != self.menu_title:
                try:
                    self.iface.removePluginMenu(old_menu_title, self.main_action)
                    self.iface.addPluginToMenu(self.menu_title, self.main_action)
                except Exception:
                    pass

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
                self.tool = MapSharingTool(self.iface, self.refresh_language)
            self.tool.run()
        except Exception as exc:  # pragma: no cover - shown inside QGIS
            QMessageBox.critical(
                self.iface.mainWindow(),
                i18n.tr('tool_title'),
                i18n.tr('startup_failed', error=exc),
            )

