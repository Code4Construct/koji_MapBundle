# -*- coding: utf-8 -*-

import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime

from qgis.core import (
    QgsMapLayer,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .koji_MapBundle_ui import display_metrics_text, dpi_px


class MapSharingLayerSelectionDialog(QDialog):
    """Select layers to include in a map sharing package."""

    def __init__(self, layers, layouts=None, checked_layer_ids=None, parent=None):
        super().__init__(parent)
        self.layers = layers
        self.layouts = layouts or []
        self.layer_by_id = {layer.id(): layer for layer in layers}
        self.checked_layer_ids = set(checked_layer_ids or [])
        self._changing_checks = False

        self.setWindowTitle('地図バンドルに入れるレイヤを選択')
        self.resize(780, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        lead = QLabel('地図バンドルに入れるレイヤだけチェックしてください。')
        lead.setWordWrap(True)
        layout.addWidget(lead)

        toolbar = QHBoxLayout()
        select_all_button = QPushButton('すべて選択')
        clear_button = QPushButton('選択解除')
        select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        clear_button.clicked.connect(lambda: self._set_all_checked(False))
        toolbar.addWidget(select_all_button)
        toolbar.addWidget(clear_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(['レイヤ構成', 'データソース'])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.itemChanged.connect(self._handle_item_changed)
        layout.addWidget(self.tree, 1)

        self._build_layer_tree()
        self.tree.expandAll()

        layout_label = QLabel('地図バンドルに入れるレイアウトを選択してください。')
        layout_label.setWordWrap(True)
        layout.addWidget(layout_label)

        self.layout_tree = QTreeWidget()
        self.layout_tree.setColumnCount(2)
        self.layout_tree.setHeaderLabels(['レイアウト', '種類'])
        self.layout_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.layout_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._build_layout_tree()
        layout.addWidget(self.layout_tree)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def selected_layers(self):
        selected_ids = set()
        self._collect_checked_layer_ids(self.tree.invisibleRootItem(), selected_ids)
        return [layer for layer in self.layers if layer.id() in selected_ids]

    def selected_layouts(self):
        selected_names = set()
        root_item = self.layout_tree.invisibleRootItem()
        for index in range(root_item.childCount()):
            item = root_item.child(index)
            if item.checkState(0) == Qt.Checked:
                selected_names.add(item.data(0, Qt.UserRole))
        return [layout for layout in self.layouts if layout.name() in selected_names]

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self._changing_checks = True
        root_item = self.tree.invisibleRootItem()
        for index in range(root_item.childCount()):
            self._set_item_checked_recursive(root_item.child(index), state)
        layout_root_item = self.layout_tree.invisibleRootItem()
        for index in range(layout_root_item.childCount()):
            layout_root_item.child(index).setCheckState(0, state)
        self._changing_checks = False

    def _build_layer_tree(self):
        added_ids = set()
        root_node = QgsProject.instance().layerTreeRoot()
        for child in root_node.children():
            self._add_layer_tree_node(self.tree.invisibleRootItem(), child, added_ids)

        for layer in self.layers:
            if layer.id() not in added_ids:
                self._add_layer_item(self.tree.invisibleRootItem(), layer)
                added_ids.add(layer.id())

        self._refresh_group_check_states(self.tree.invisibleRootItem())

    def _build_layout_tree(self):
        for layout in self.layouts:
            item = QTreeWidgetItem(self.layout_tree.invisibleRootItem(), [layout.name(), 'レイアウト'])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            item.setData(0, Qt.UserRole, layout.name())

    def _add_layer_tree_node(self, parent_item, node, added_ids):
        if hasattr(node, 'layerId'):
            layer = self.layer_by_id.get(node.layerId())
            if layer is None:
                return False
            self._add_layer_item(parent_item, layer)
            added_ids.add(layer.id())
            return True

        if not hasattr(node, 'children'):
            return False

        group_item = QTreeWidgetItem(parent_item, [node.name(), ''])
        group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
        group_item.setCheckState(0, Qt.Unchecked)
        group_item.setData(0, Qt.UserRole, '')

        has_layers = False
        for child in node.children():
            has_layers = self._add_layer_tree_node(group_item, child, added_ids) or has_layers

        if not has_layers:
            parent_item.removeChild(group_item)
        return has_layers

    def _add_layer_item(self, parent_item, layer):
        layer_item = QTreeWidgetItem(parent_item, [layer.name(), layer.source()])
        layer_item.setFlags(layer_item.flags() | Qt.ItemIsUserCheckable)
        checked = layer.id() in self.checked_layer_ids
        layer_item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        layer_item.setData(0, Qt.UserRole, layer.id())

    def _handle_item_changed(self, item, column):
        if self._changing_checks or column != 0:
            return

        self._changing_checks = True
        if item.childCount() > 0:
            state = item.checkState(0)
            if state in (Qt.Checked, Qt.Unchecked):
                for index in range(item.childCount()):
                    self._set_item_checked_recursive(item.child(index), state)
        self._refresh_parent_check_state(item.parent())
        self._changing_checks = False

    def _set_item_checked_recursive(self, item, state):
        item.setCheckState(0, state)
        for index in range(item.childCount()):
            self._set_item_checked_recursive(item.child(index), state)

    def _refresh_group_check_states(self, item):
        for index in range(item.childCount()):
            child = item.child(index)
            self._refresh_group_check_states(child)
        if item.childCount() > 0 and item is not self.tree.invisibleRootItem():
            self._apply_group_check_state(item)

    def _refresh_parent_check_state(self, item):
        while item is not None:
            self._apply_group_check_state(item)
            item = item.parent()

    def _apply_group_check_state(self, item):
        checked_count = 0
        partial_count = 0
        for index in range(item.childCount()):
            state = item.child(index).checkState(0)
            if state == Qt.Checked:
                checked_count += 1
            elif state == Qt.PartiallyChecked:
                partial_count += 1

        if checked_count == item.childCount():
            item.setCheckState(0, Qt.Checked)
        elif checked_count == 0 and partial_count == 0:
            item.setCheckState(0, Qt.Unchecked)
        else:
            item.setCheckState(0, Qt.PartiallyChecked)

    def _collect_checked_layer_ids(self, item, selected_ids):
        layer_id = item.data(0, Qt.UserRole)
        if layer_id and item.checkState(0) == Qt.Checked:
            selected_ids.add(layer_id)
        for index in range(item.childCount()):
            self._collect_checked_layer_ids(item.child(index), selected_ids)


class MapSharingDialog(QDialog):
    """Choose package export or import."""

    def __init__(self, export_callback, import_callback, parent=None):
        super().__init__(parent)
        self.export_callback = export_callback
        self.import_callback = import_callback

        plugin_icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.png'))
        self.setWindowTitle('koji_MapBundle')
        self.setWindowIcon(plugin_icon)
        self.setMinimumWidth(dpi_px(500))
        self.resize(dpi_px(620), dpi_px(430))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(dpi_px(18), dpi_px(18), dpi_px(18), dpi_px(18))
        layout.setSpacing(dpi_px(12))

        title_row = QHBoxLayout()
        title_row.setSpacing(dpi_px(10))

        brand_icon = QLabel()
        brand_pixmap = plugin_icon.pixmap(dpi_px(30), dpi_px(30))
        brand_icon.setPixmap(brand_pixmap)
        brand_icon.setFixedSize(dpi_px(34), dpi_px(34))
        brand_icon.setAlignment(Qt.AlignCenter)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(dpi_px(1))

        title = QLabel('koji_MapBundle')
        title_font = title.font()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet('color: #183a2f; letter-spacing: 0px;')

        lead = QLabel('地図バンドルを書き出し・読み込みします。')
        lead.setStyleSheet('color: #66726c;')

        metrics_label = QLabel(display_metrics_text())
        metrics_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        metrics_label.setStyleSheet('color: #66726c;')

        title_block.addWidget(title)
        title_block.addWidget(lead)

        title_row.addWidget(brand_icon)
        title_row.addLayout(title_block)
        title_row.addStretch(1)
        title_row.addWidget(metrics_label)
        layout.addLayout(title_row)

        accent_line = QFrame()
        accent_line.setFixedHeight(dpi_px(2))
        accent_line.setStyleSheet('background: #2f8f5b; border: none;')
        layout.addWidget(accent_line)

        icons_dir = os.path.join(os.path.dirname(__file__), 'icons')
        layout.addWidget(self._create_action_row(
            '地図バンドルを書き出し',
            '選択したレイヤ、スタイル、シンボル、レイアウトをZIP形式の地図バンドルとして保存します。',
            os.path.join(icons_dir, 'map_bundle_export.png'),
            self.export_callback,
        ))
        layout.addWidget(self._create_action_row(
            '地図バンドルを読み込み',
            '受け取った地図バンドルを展開し、GeoPackageをプロジェクトフォルダに保存してレイヤを追加します。',
            os.path.join(icons_dir, 'map_bundle_import.png'),
            self.import_callback,
        ))

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_action_row(self, text, description, icon_path, callback):
        row = QPushButton()
        row.setMinimumHeight(dpi_px(118))
        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        row.setCursor(Qt.PointingHandCursor)
        row.clicked.connect(callback)
        row.setStyleSheet(
            'QPushButton {{ text-align: left; border: {0}px solid #c8c8c8; border-radius: {1}px; background: #f7f7f7; }}'
            'QPushButton:hover {{ background: #eef5ff; border-color: #7aa7d9; }}'
            'QPushButton:pressed {{ background: #e0edf9; }}'
            'QLabel {{ border: none; background: transparent; }}'
            .format(dpi_px(1), dpi_px(4))
        )

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(dpi_px(12), dpi_px(10), dpi_px(12), dpi_px(10))
        row_layout.setSpacing(dpi_px(12))

        icon_label = QLabel()
        icon = QIcon(icon_path)
        icon_size = dpi_px(76)
        icon_box = dpi_px(88)
        icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
        icon_label.setFixedSize(icon_box, icon_box)
        icon_label.setAlignment(Qt.AlignCenter)
        row_layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(dpi_px(4))

        name_label = QLabel(text)
        name_label.setStyleSheet('font-weight: 600;')
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setMinimumHeight(description_label.fontMetrics().lineSpacing() * 3 + dpi_px(6))
        description_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        text_layout.addWidget(name_label)
        text_layout.addWidget(description_label)
        row_layout.addLayout(text_layout, 1)
        return row


class MapSharingPackagePreviewDialog(QDialog):
    """Show map sharing package contents before import."""

    def __init__(self, manifest, parent=None):
        super().__init__(parent)
        self.manifest = manifest

        self.setWindowTitle('地図バンドルから読み込むものを選択')
        self.resize(820, 560)
        self._changing_checks = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        package_name = manifest.get('package_name') or '名称未設定'
        layers = manifest.get('layers', [])
        layouts = manifest.get('layouts', [])
        title = QLabel('地図バンドルから読み込むものを選択')
        title.setStyleSheet('font-size: 18px; font-weight: 600;')
        layout.addWidget(title)

        summary = QLabel(
            'バンドル名: {0} / レイヤ数: {1} / レイアウト数: {2}'.format(
                package_name,
                len(layers),
                len(layouts),
            )
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        guide = QLabel('読み込むレイヤとレイアウトにチェックを入れてください。チェックを外したものは読み込みません。')
        guide.setWordWrap(True)
        layout.addWidget(guide)

        toolbar = QHBoxLayout()
        select_all_button = QPushButton('すべて選択')
        clear_button = QPushButton('選択解除')
        select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        clear_button.clicked.connect(lambda: self._set_all_checked(False))
        toolbar.addWidget(select_all_button)
        toolbar.addWidget(clear_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(['読み込む項目', '種類', 'データ', 'スタイル'])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._handle_item_changed)
        self.tree.setRootIsDecorated(True)
        layout.addWidget(self.tree, 1)

        self._populate_tree(layers)
        self._populate_layouts(layouts)
        self.tree.expandAll()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText('チェックしたものを読み込む')
        button_box.button(QDialogButtonBox.Cancel).setText('キャンセル')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_tree(self, layers):
        group_items = {}
        for index, layer_info in enumerate(layers):
            parent_item = self.tree.invisibleRootItem()
            group_path = layer_info.get('group_path')
            if not isinstance(group_path, list):
                group_name = layer_info.get('group')
                group_path = [group_name] if group_name else []

            path_key = []
            for group_name in group_path:
                if not group_name:
                    continue
                path_key.append(group_name)
                key = tuple(path_key)
                if key not in group_items:
                    group_items[key] = QTreeWidgetItem(parent_item, [group_name, 'フォルダ', '', ''])
                    self._make_checkable_group_item(group_items[key])
                parent_item = group_items[key]

            layer_type = layer_info.get('type') or ('ベクタ' if layer_info.get('path') else 'ラスタ')
            if layer_type == 'vector':
                display_type = 'ベクタ'
                data_value = layer_info.get('path', '')
            elif layer_type == 'raster':
                display_type = 'ラスタ/XYZ'
                data_value = layer_info.get('source', '')
            else:
                display_type = layer_type
                data_value = layer_info.get('path') or layer_info.get('source') or ''

            style_value = 'あり' if layer_info.get('style') else 'なし'
            item = QTreeWidgetItem(parent_item, [
                layer_info.get('name') or layer_info.get('layername') or '名称未設定',
                display_type,
                data_value,
                style_value,
            ])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setData(0, Qt.UserRole, 'layer')
            item.setData(0, Qt.UserRole + 1, index)

    def _populate_layouts(self, layouts):
        if not layouts:
            return

        layouts_item = QTreeWidgetItem(self.tree.invisibleRootItem(), ['レイアウト', 'フォルダ', '', ''])
        self._make_checkable_group_item(layouts_item)
        for index, layout_info in enumerate(layouts):
            item = QTreeWidgetItem(layouts_item, [
                layout_info.get('name') or '名称未設定',
                'レイアウト',
                layout_info.get('path') or '',
                '',
            ])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Checked)
            item.setData(0, Qt.UserRole, 'layout')
            item.setData(0, Qt.UserRole + 1, index)
        self._refresh_group_check_states(self.tree.invisibleRootItem())

    def selected_layer_indexes(self):
        selected = []
        self._collect_selected_indexes(self.tree.invisibleRootItem(), 'layer', selected)
        return selected

    def selected_layout_indexes(self):
        selected = []
        self._collect_selected_indexes(self.tree.invisibleRootItem(), 'layout', selected)
        return selected

    def _set_all_checked(self, checked):
        self._changing_checks = True
        state = Qt.Checked if checked else Qt.Unchecked
        root_item = self.tree.invisibleRootItem()
        for index in range(root_item.childCount()):
            self._set_item_checked_recursive(root_item.child(index), state)
        self._changing_checks = False

    def _make_checkable_group_item(self, item):
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked)

    def _handle_item_changed(self, item, column):
        if self._changing_checks or column != 0:
            return

        self._changing_checks = True
        if item.childCount() > 0:
            state = item.checkState(0)
            if state in (Qt.Checked, Qt.Unchecked):
                for index in range(item.childCount()):
                    self._set_item_checked_recursive(item.child(index), state)
        self._refresh_parent_check_state(item.parent())
        self._changing_checks = False

    def _set_item_checked_recursive(self, item, state):
        item.setCheckState(0, state)
        for index in range(item.childCount()):
            self._set_item_checked_recursive(item.child(index), state)

    def _refresh_parent_check_state(self, item):
        while item is not None:
            self._apply_group_check_state(item)
            item = item.parent()

    def _refresh_group_check_states(self, item):
        for index in range(item.childCount()):
            child = item.child(index)
            self._refresh_group_check_states(child)
        if item.childCount() > 0 and item is not self.tree.invisibleRootItem():
            self._apply_group_check_state(item)

    def _apply_group_check_state(self, item):
        checked_count = 0
        partial_count = 0
        for index in range(item.childCount()):
            state = item.child(index).checkState(0)
            if state == Qt.Checked:
                checked_count += 1
            elif state == Qt.PartiallyChecked:
                partial_count += 1

        if checked_count == item.childCount():
            item.setCheckState(0, Qt.Checked)
        elif checked_count == 0 and partial_count == 0:
            item.setCheckState(0, Qt.Unchecked)
        else:
            item.setCheckState(0, Qt.PartiallyChecked)

    def _collect_selected_indexes(self, item, item_type, selected):
        if item.data(0, Qt.UserRole) == item_type and item.checkState(0) == Qt.Checked:
            selected.append(item.data(0, Qt.UserRole + 1))
        for index in range(item.childCount()):
            self._collect_selected_indexes(item.child(index), item_type, selected)


class MapSharingLayoutImportDialog(QDialog):
    """Edit layout names before importing package layouts."""

    def __init__(self, layouts, parent=None):
        super().__init__(parent)
        self.layouts = layouts
        self.setWindowTitle('レイアウトの取り込み設定')
        self.resize(720, 420)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(10)

        title = QLabel('取り込むレイアウトを選択し、必要に応じて名前を変更してください。')
        title.setWordWrap(True)
        main_layout.addWidget(title)

        existing_names = [layout.name() for layout in QgsProject.instance().layoutManager().layouts()]
        existing_label = QLabel(
            '既存レイアウト: {0}'.format(', '.join(existing_names) if existing_names else 'なし')
        )
        existing_label.setWordWrap(True)
        main_layout.addWidget(existing_label)

        self.table = QTableWidget(len(layouts), 3)
        self.table.setHorizontalHeaderLabels(['取り込む', '元の名前', '取り込み後の名前'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.table, 1)

        for row, layout_info in enumerate(layouts):
            original_name = layout_info.get('name') or '地図バンドルレイアウト'
            import_item = QTableWidgetItem('')
            import_item.setFlags(import_item.flags() | Qt.ItemIsUserCheckable)
            import_item.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, import_item)

            original_item = QTableWidgetItem(original_name)
            original_item.setFlags(original_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, original_item)

            name_item = QTableWidgetItem(self._default_import_name(original_name, existing_names))
            self.table.setItem(row, 2, name_item)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText('取り込む')
        button_box.button(QDialogButtonBox.Cancel).setText('キャンセル')
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def selected_layouts(self):
        selected = []
        for row, layout_info in enumerate(self.layouts):
            import_item = self.table.item(row, 0)
            name_item = self.table.item(row, 2)
            if import_item is None or import_item.checkState() != Qt.Checked:
                continue
            new_name = name_item.text().strip() if name_item is not None else ''
            if not new_name:
                continue
            updated_info = dict(layout_info)
            updated_info['import_name'] = new_name
            selected.append(updated_info)
        return selected

    def _default_import_name(self, original_name, existing_names):
        if original_name not in existing_names:
            return original_name
        return original_name + '_取り込み'


class MapSharingTool:
    """Export and import koji_MapBundle ZIP packages."""

    def __init__(self, iface):
        self.iface = iface
        self.dlg = None
        self.plugin_dir = os.path.dirname(__file__)

    def run(self):
        if self.dlg is None:
            self.dlg = MapSharingDialog(
                self.export_package,
                self.import_package,
                self.iface.mainWindow(),
            )

        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def export_package(self):
        project = QgsProject.instance()
        available_layers = [
            layer
            for layer in project.mapLayers().values()
            if layer.type() in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer) and layer.isValid()
        ]
        available_layouts = project.layoutManager().layouts()
        if not available_layers and not available_layouts:
            QMessageBox.warning(
                self.iface.mainWindow(),
                '地図バンドル',
                '書き出せるレイヤまたはレイアウトがありません。',
            )
            return

        selection_dialog = MapSharingLayerSelectionDialog(
            available_layers,
            available_layouts,
            self._selected_layer_ids(),
            self.iface.mainWindow(),
        )
        if selection_dialog.exec_() != QDialog.Accepted:
            return

        layers = selection_dialog.selected_layers()
        layouts = selection_dialog.selected_layouts()
        if not layers and not layouts:
            QMessageBox.warning(
                self.iface.mainWindow(),
                '地図バンドル',
                '地図バンドルに入れるレイヤまたはレイアウトを1つ以上選択してください。',
            )
            return

        default_name = '地図バンドル.zip'
        zip_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            '地図バンドルを書き出し',
            default_name,
            '地図バンドル (*.zip);;All files (*.*)',
        )
        if not zip_path:
            return
        if not zip_path.lower().endswith('.zip'):
            zip_path += '.zip'

        try:
            with tempfile.TemporaryDirectory(prefix='koji_MapBundle_package_') as temp_dir:
                self._build_package(temp_dir, zip_path, layers, layouts)
            QMessageBox.information(
                self.iface.mainWindow(),
                '地図バンドル',
                '地図バンドルを書き出しました。\n{0}'.format(zip_path),
            )
        except Exception as exc:  # pragma: no cover - shown inside QGIS
            QMessageBox.critical(
                self.iface.mainWindow(),
                '地図バンドル',
                '地図バンドルの書き出しに失敗しました。\n{0}'.format(exc),
            )

    def import_package(self):
        zip_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            '地図バンドルを読み込み',
            '',
            '地図バンドル (*.zip);;All files (*.*)',
        )
        if not zip_path:
            return

        try:
            with tempfile.TemporaryDirectory(prefix='koji_MapBundle_import_') as temp_dir:
                package_dir = self._extract_package(zip_path, temp_dir)
                self._load_package_directory(package_dir, zip_path)
        except Exception as exc:  # pragma: no cover - shown inside QGIS
            QMessageBox.critical(
                self.iface.mainWindow(),
                '地図バンドル',
                '地図バンドルの読み込みに失敗しました。\n{0}'.format(exc),
            )

    def _build_package(self, temp_dir, zip_path, layers, layouts=None):
        data_dir = os.path.join(temp_dir, 'data')
        styles_dir = os.path.join(temp_dir, 'styles')
        symbols_dir = os.path.join(temp_dir, 'symbols')
        layouts_dir = os.path.join(temp_dir, 'layouts')
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(styles_dir, exist_ok=True)
        os.makedirs(symbols_dir, exist_ok=True)
        os.makedirs(layouts_dir, exist_ok=True)

        project = QgsProject.instance()
        manifest = {
            'package_name': self._safe_name(project.baseName() or 'koji_MapBundle_package'),
            'package_type': 'layer_package',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'layers': [],
            'layouts': [],
        }

        package_gpkg_name = 'koji_MapBundle_layers.gpkg'
        package_gpkg_path = os.path.join(data_dir, package_gpkg_name)
        used_names = set()
        vector_written = False
        for index, layer in enumerate(layers, start=1):
            layer_key = self._unique_name(
                self._safe_name(layer.name()) or 'layer_{0}'.format(index),
                used_names,
            )
            qml_path = os.path.join(styles_dir, layer_key + '.qml')

            layer_entry = {
                'name': layer.name(),
                'layername': layer_key,
                'style': 'styles/{0}.qml'.format(layer_key),
                'visible': self._layer_is_visible(layer),
                'group': self._layer_group_name(layer),
                'group_path': self._layer_group_path(layer),
            }
            if layer.type() == QgsMapLayer.VectorLayer:
                self._write_vector_layer(layer, package_gpkg_path, layer_key, not vector_written)
                vector_written = True
                layer_entry.update({
                    'type': 'vector',
                    'path': 'data/{0}'.format(package_gpkg_name),
                })
            elif layer.type() == QgsMapLayer.RasterLayer:
                layer_entry.update({
                    'type': 'raster',
                    'provider': layer.providerType(),
                    'source': layer.source(),
                })
            else:
                continue

            layer.saveNamedStyle(qml_path)
            self._copy_svg_assets(qml_path, symbols_dir)

            manifest['layers'].append(layer_entry)

        self._write_layout_templates(layouts_dir, layouts or [], manifest)

        manifest_path = os.path.join(temp_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as package_zip:
            for root, _, files in os.walk(temp_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    arcname = os.path.relpath(file_path, temp_dir).replace(os.sep, '/')
                    package_zip.write(file_path, arcname)

    def _extract_package(self, zip_path, temp_dir):
        base_name = self._safe_name(os.path.splitext(os.path.basename(zip_path))[0]) or 'package'
        package_dir = os.path.join(
            temp_dir,
            '{0}_{1}'.format(base_name, datetime.now().strftime('%Y%m%d_%H%M%S')),
        )
        os.makedirs(package_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as package_zip:
            self._safe_extract_zip(package_zip, package_dir)
        return package_dir

    def _load_package_directory(self, package_dir, zip_path=None):
        manifest_path = os.path.join(package_dir, 'manifest.json')
        if not os.path.exists(manifest_path):
            raise ValueError('選択したフォルダに manifest.json がありません。')

        with open(manifest_path, 'r', encoding='utf-8') as manifest_file:
            manifest = json.load(manifest_file)

        preview_dialog = MapSharingPackagePreviewDialog(manifest, self.iface.mainWindow())
        if preview_dialog.exec_() != QDialog.Accepted:
            return
        manifest = self._filter_manifest_by_preview_selection(manifest, preview_dialog)
        if not manifest.get('layers') and not manifest.get('layouts'):
            QMessageBox.warning(
                self.iface.mainWindow(),
                '地図バンドル',
                '読み込むレイヤまたはレイアウトを1つ以上選択してください。',
            )
            return

        if manifest.get('layouts'):
            layout_dialog = MapSharingLayoutImportDialog(
                manifest.get('layouts', []),
                self.iface.mainWindow(),
            )
            if layout_dialog.exec_() != QDialog.Accepted:
                return
            manifest['layouts'] = layout_dialog.selected_layouts()
            if not manifest.get('layers') and not manifest.get('layouts'):
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    '地図バンドル',
                    '読み込むレイヤまたはレイアウトを1つ以上選択してください。',
                )
                return

        project_package_dir = self._copy_package_to_project_storage(package_dir, manifest, zip_path)
        if project_package_dir is None:
            return

        destination_group = self._ask_import_group(manifest)
        if destination_group is None:
            return

        loaded_count = self._load_manifest_layers(
            project_package_dir,
            manifest,
            destination_group,
        )
        loaded_layout_count = self._load_layout_templates(project_package_dir, manifest)
        QMessageBox.information(
            self.iface.mainWindow(),
            '地図バンドル',
            '{0} レイヤ、{1} レイアウトを読み込みました。\n保存先: {2}'.format(
                loaded_count,
                loaded_layout_count,
                project_package_dir,
            ),
        )

    def _filter_manifest_by_preview_selection(self, manifest, preview_dialog):
        filtered_manifest = dict(manifest)
        layers = manifest.get('layers', [])
        layouts = manifest.get('layouts', [])
        selected_layer_indexes = set(preview_dialog.selected_layer_indexes())
        selected_layout_indexes = set(preview_dialog.selected_layout_indexes())

        filtered_manifest['layers'] = [
            layer
            for index, layer in enumerate(layers)
            if index in selected_layer_indexes
        ]
        filtered_manifest['layouts'] = [
            layout
            for index, layout in enumerate(layouts)
            if index in selected_layout_indexes
        ]
        return filtered_manifest

    def _copy_package_to_project_storage(self, package_dir, manifest, zip_path=None):
        storage_dir = self._project_package_storage_dir(manifest, zip_path)
        if storage_dir is None:
            return None

        if os.path.exists(storage_dir):
            shutil.rmtree(storage_dir)
        shutil.copytree(package_dir, storage_dir)
        if not self._rename_imported_geopackages(storage_dir, manifest):
            return None
        return storage_dir

    def _rename_imported_geopackages(self, storage_dir, manifest):
        gpkg_rel_paths = []
        for layer_info in manifest.get('layers', []):
            rel_path = layer_info.get('path')
            if rel_path and rel_path.lower().endswith('.gpkg') and rel_path not in gpkg_rel_paths:
                gpkg_rel_paths.append(rel_path)

        if not gpkg_rel_paths:
            return True

        gpkg_name, accepted = QInputDialog.getText(
            self.iface.mainWindow(),
            'GeoPackage名',
            '保存するGeoPackage名:',
            QLineEdit.Normal,
            'MapBundle',
        )
        if not accepted:
            return False

        gpkg_name = gpkg_name.strip()
        if gpkg_name.lower().endswith('.gpkg'):
            gpkg_name = gpkg_name[:-5]
        gpkg_name = (self._safe_name(gpkg_name) or 'MapBundle') + '.gpkg'

        rel_path_map = {}
        used_names = set()
        for index, rel_path in enumerate(gpkg_rel_paths, start=1):
            source_path = os.path.normpath(os.path.join(storage_dir, rel_path))
            self._assert_inside_directory(storage_dir, source_path)
            if not os.path.exists(source_path):
                raise ValueError('GeoPackageが見つかりません: {0}'.format(rel_path))

            target_name = gpkg_name
            if len(gpkg_rel_paths) > 1:
                base_name, extension = os.path.splitext(gpkg_name)
                target_name = '{0}_{1}{2}'.format(base_name, index, extension or '.gpkg')
            target_name = self._unique_name(os.path.splitext(target_name)[0], used_names) + '.gpkg'
            target_rel_path = 'data/{0}'.format(target_name)
            target_path = os.path.normpath(os.path.join(storage_dir, target_rel_path))
            self._assert_inside_directory(storage_dir, target_path)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            if os.path.abspath(source_path) != os.path.abspath(target_path):
                if os.path.exists(target_path):
                    os.remove(target_path)
                shutil.move(source_path, target_path)
            rel_path_map[rel_path] = target_rel_path

        for layer_info in manifest.get('layers', []):
            rel_path = layer_info.get('path')
            if rel_path in rel_path_map:
                layer_info['path'] = rel_path_map[rel_path]

        manifest_path = os.path.join(storage_dir, 'manifest.json')
        with open(manifest_path, 'w', encoding='utf-8') as manifest_file:
            json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
            manifest_file.write('\n')
        return True

    def _project_package_storage_dir(self, manifest, zip_path=None):
        root_dir = self._project_bundle_root()
        if root_dir is None:
            return None

        package_name = (
            manifest.get('package_name')
            or (os.path.splitext(os.path.basename(zip_path))[0] if zip_path else '')
            or 'package'
        )
        package_name = self._safe_name(package_name) or 'package'
        folder_name = '{0}_{1}'.format(package_name, datetime.now().strftime('%Y%m%d_%H%M%S'))
        return os.path.join(root_dir, folder_name)

    def _project_bundle_root(self):
        project = QgsProject.instance()
        project_dir = project.absolutePath()

        if not project_dir or not os.path.exists(project_dir):
            project_dir = QFileDialog.getExistingDirectory(
                self.iface.mainWindow(),
                'GeoPackageを保存するフォルダを選択',
                os.path.expanduser('~'),
            )
            if not project_dir:
                return None

        return project_dir

    def _load_layout_templates(self, package_dir, manifest):
        layouts = manifest.get('layouts', [])
        if not isinstance(layouts, list):
            return 0

        manager = QgsProject.instance().layoutManager()
        loaded_count = 0
        for layout_info in layouts:
            rel_path = layout_info.get('path')
            if not rel_path:
                continue

            template_path = os.path.normpath(os.path.join(package_dir, rel_path))
            self._assert_inside_directory(package_dir, template_path)
            if not os.path.exists(template_path):
                raise ValueError('レイアウトテンプレートが見つかりません: {0}'.format(rel_path))

            with open(template_path, 'r', encoding='utf-8') as template_file:
                template_text = template_file.read()

            document = QDomDocument()
            set_content_result = document.setContent(template_text)
            if isinstance(set_content_result, tuple):
                set_content_ok = bool(set_content_result[0])
            else:
                set_content_ok = bool(set_content_result)
            if not set_content_ok:
                raise ValueError('レイアウトテンプレートを読み込めません: {0}'.format(rel_path))

            layout = QgsPrintLayout(QgsProject.instance())
            layout.initializeDefaults()
            layout.loadFromTemplate(document, QgsReadWriteContext())
            layout.setName(self._unique_layout_name(
                layout_info.get('import_name') or layout_info.get('name') or '地図バンドルレイアウト'
            ))
            manager.addLayout(layout)
            loaded_count += 1

        return loaded_count

    def _write_layout_templates(self, layouts_dir, layouts, manifest):
        used_names = set()
        context = QgsReadWriteContext()
        for index, layout in enumerate(layouts, start=1):
            layout_key = self._unique_name(
                self._safe_name(layout.name()) or 'layout_{0}'.format(index),
                used_names,
            )
            qpt_path = os.path.join(layouts_dir, layout_key + '.qpt')
            layout.saveAsTemplate(qpt_path, context)
            manifest['layouts'].append({
                'name': layout.name(),
                'path': 'layouts/{0}.qpt'.format(layout_key),
            })

    def _load_manifest_layers(self, package_dir, manifest, destination_group=None, path_overrides=None):
        layers = manifest.get('layers', [])
        if not isinstance(layers, list):
            raise ValueError('manifest.json の layers が配列ではありません。')

        root = QgsProject.instance().layerTreeRoot()
        loaded_count = 0
        for layer_info in layers:
            rel_path = layer_info.get('path')
            layer_type = layer_info.get('type') or ('vector' if rel_path else 'raster')
            layer_name = layer_info.get('name') or layer_info.get('layername') or 'layer'

            if layer_type == 'vector':
                if not rel_path:
                    continue
                source_path = path_overrides.get(rel_path) if path_overrides else None
                if source_path is None:
                    source_path = os.path.normpath(os.path.join(package_dir, rel_path))
                    self._assert_inside_directory(package_dir, source_path)
                layer_name = layer_info.get('name') or layer_info.get('layername') or os.path.basename(source_path)
                gpkg_layer_name = layer_info.get('layername')
                source = source_path
                if gpkg_layer_name:
                    source = '{0}|layername={1}'.format(source_path, gpkg_layer_name)
                layer = QgsVectorLayer(source, layer_name, 'ogr')
            elif layer_type == 'raster':
                source = layer_info.get('source')
                provider = layer_info.get('provider') or 'gdal'
                if not source:
                    continue
                layer = QgsRasterLayer(source, layer_name, provider)
            else:
                continue

            if not layer.isValid():
                raise ValueError('レイヤを読み込めません: {0}'.format(layer_name))

            style_rel_path = layer_info.get('style')
            if style_rel_path:
                style_path = os.path.normpath(os.path.join(package_dir, style_rel_path))
                self._assert_inside_directory(package_dir, style_path)
                if os.path.exists(style_path):
                    style_result = layer.loadNamedStyle(style_path)
                    if isinstance(style_result, tuple) and len(style_result) > 1 and not style_result[1]:
                        raise ValueError('スタイルを読み込めません: {0}'.format(style_rel_path))
                    layer.triggerRepaint()

            QgsProject.instance().addMapLayer(layer, False)
            parent_group = destination_group or root
            group_path = layer_info.get('group_path')
            if not isinstance(group_path, list):
                group_name = layer_info.get('group')
                group_path = [group_name] if group_name else []
            target_group = self._find_or_create_group_path(parent_group, group_path)
            target_group.addLayer(layer)

            node = root.findLayer(layer.id())
            if node is not None:
                node.setItemVisibilityChecked(bool(layer_info.get('visible', True)))
            loaded_count += 1

        return loaded_count

    def _write_vector_layer(self, layer, gpkg_path, layer_name, create_file):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG'
        options.layerName = layer_name
        options.fileEncoding = 'UTF-8'
        if create_file:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            gpkg_path,
            QgsProject.instance().transformContext(),
            options,
        )
        error_code = result[0] if isinstance(result, tuple) else result
        if error_code != QgsVectorFileWriter.NoError:
            message = result[1] if isinstance(result, tuple) and len(result) > 1 else 'unknown error'
            raise RuntimeError('レイヤを書き出せません: {0} ({1})'.format(layer.name(), message))

    def _copy_svg_assets(self, qml_path, symbols_dir):
        if not os.path.exists(qml_path):
            return
        with open(qml_path, 'r', encoding='utf-8', errors='ignore') as qml_file:
            qml_text = qml_file.read()

        replacements = {}
        for match in re.findall(r'["\']([^"\']+\.svg)["\']', qml_text, flags=re.IGNORECASE):
            svg_path = match
            if not os.path.isabs(svg_path):
                svg_path = os.path.normpath(os.path.join(os.path.dirname(qml_path), svg_path))
            if os.path.exists(svg_path):
                asset_name = os.path.basename(svg_path)
                shutil.copy2(svg_path, os.path.join(symbols_dir, asset_name))
                replacements[match] = '../symbols/{0}'.format(asset_name)

        if replacements:
            for old_path, new_path in replacements.items():
                qml_text = qml_text.replace(old_path, new_path)
            with open(qml_path, 'w', encoding='utf-8') as qml_file:
                qml_file.write(qml_text)

    def _safe_extract_zip(self, package_zip, target_dir):
        for member in package_zip.infolist():
            target_path = os.path.normpath(os.path.join(target_dir, member.filename))
            self._assert_inside_directory(target_dir, target_path)
            package_zip.extract(member, target_dir)

    def _assert_inside_directory(self, base_dir, path):
        base_dir = os.path.abspath(base_dir)
        path = os.path.abspath(path)
        if os.path.commonpath([base_dir, path]) != base_dir:
            raise ValueError('地図バンドル外のパスは使用できません。')

    def _layer_is_visible(self, layer):
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        return True if node is None else node.isVisible()

    def _selected_layer_ids(self):
        selected_ids = set()
        try:
            layer_tree_view = self.iface.layerTreeView()
            selected_layers = layer_tree_view.selectedLayers()
        except Exception:
            selected_layers = []
            layer_tree_view = None

        selected_ids.update(layer.id() for layer in selected_layers if layer is not None)
        if layer_tree_view is not None and hasattr(layer_tree_view, 'selectedNodes'):
            for node in layer_tree_view.selectedNodes():
                self._collect_layer_ids_from_node(node, selected_ids)
        return list(selected_ids)

    def _selected_group_node(self):
        try:
            layer_tree_view = self.iface.layerTreeView()
        except Exception:
            return None

        if not hasattr(layer_tree_view, 'selectedNodes'):
            return None

        for node in layer_tree_view.selectedNodes():
            if self._is_group_node(node):
                return node
        return None

    def _collect_layer_ids_from_node(self, node, selected_ids):
        if hasattr(node, 'layerId'):
            layer_id = node.layerId()
            if layer_id:
                selected_ids.add(layer_id)

        if hasattr(node, 'children'):
            for child in node.children():
                self._collect_layer_ids_from_node(child, selected_ids)

    def _is_group_node(self, node):
        return hasattr(node, 'children') and not hasattr(node, 'layerId')

    def _ask_import_group(self, manifest):
        default_name = 'MapBundle'
        group_name, accepted = QInputDialog.getText(
            self.iface.mainWindow(),
            'インポート先フォルダ名',
            'レイヤパネルに作成するフォルダ名:',
            QLineEdit.Normal,
            default_name,
        )
        if not accepted:
            return None

        group_name = group_name.strip()
        if not group_name:
            QMessageBox.warning(
                self.iface.mainWindow(),
                '地図バンドル',
                'フォルダ名を入力してください。',
            )
            return None

        return QgsProject.instance().layerTreeRoot().addGroup(group_name)

    def _find_or_create_group(self, parent_group, group_name):
        if not group_name:
            return parent_group

        if hasattr(parent_group, 'findGroup'):
            group = parent_group.findGroup(group_name)
            if group is not None:
                return group

        for child in parent_group.children():
            if self._is_group_node(child) and child.name() == group_name:
                return child

        return parent_group.addGroup(group_name)

    def _find_or_create_group_path(self, parent_group, group_path):
        group = parent_group
        for group_name in group_path:
            if group_name:
                group = self._find_or_create_group(group, group_name)
        return group

    def _layer_group_name(self, layer):
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        parent = node.parent() if node is not None else None
        if parent is not None and hasattr(parent, 'name'):
            name = parent.name()
            return name or None
        return None

    def _layer_group_path(self, layer):
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        parent = node.parent() if node is not None else None
        root = QgsProject.instance().layerTreeRoot()
        path = []
        while parent is not None and parent is not root and hasattr(parent, 'name'):
            name = parent.name()
            if name:
                path.insert(0, name)
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return path

    def _safe_name(self, value):
        value = re.sub(r'[^\w\-]+', '_', value, flags=re.UNICODE).strip('_')
        return value[:80]

    def _unique_name(self, value, used_names):
        candidate = value
        suffix = 2
        while candidate in used_names:
            candidate = '{0}_{1}'.format(value, suffix)
            suffix += 1
        used_names.add(candidate)
        return candidate

    def _unique_layout_name(self, value):
        manager = QgsProject.instance().layoutManager()
        existing_names = {layout.name() for layout in manager.layouts()}
        candidate = value
        suffix = 2
        while candidate in existing_names:
            candidate = '{0}_{1}'.format(value, suffix)
            suffix += 1
        return candidate



