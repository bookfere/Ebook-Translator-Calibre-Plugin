import os
import sys
import os.path
from subprocess import Popen

from .lib.cache import TranslationCache
from .lib.config import get_config
from .components import layout_info, AlertMessage

try:
    from qt.core import (
        Qt, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
        QLabel, QTableView, QAbstractTableModel, QAbstractItemView, pyqtSignal,
        QLineEdit)
except ImportError:
    from PyQt5.Qt import (
        Qt, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
        QLabel, QTableView, QAbstractTableModel, QAbstractItemView, pyqtSignal,
        QLineEdit)

load_translations()


class CacheManager(QDialog):
    cache_count = pyqtSignal()

    def __init__(self, plugin, parent):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.gui = parent
        self.config = get_config()

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.control_widget())
        self.layout.addWidget(self.table_widget())
        self.layout.addWidget(self.enable_widget())
        self.layout.addWidget(layout_info())

        self.alert = AlertMessage(self)

        self.cache_enabled.setChecked(self.config.get('cache_enabled'))
        self.cache_enabled.toggled.connect(
            lambda checked: self.config.save(cache_enabled=checked))

        self.cache_count.connect(self.recount)
        self.cache_reveal.clicked.connect(self.reveal)
        self.clear_button.clicked.connect(self.clear)
        self.delete_button.clicked.connect(self.delete)

        self.cache_count.emit()

    def control_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.cache_enabled = QCheckBox(_('Enable'))
        self.cache_path = QLineEdit()
        self.cache_choose = QPushButton(_('Choose'))
        self.cache_reveal = QPushButton(_('Reveal'))

        layout.addWidget(self.cache_enabled)
        layout.addWidget(self.cache_path)
        layout.addWidget(self.cache_choose)
        layout.addWidget(self.cache_reveal)

        return widget

    def enable_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.cache_size = QLabel()
        self.clear_button = QPushButton(_('Clear'))
        self.delete_button = QPushButton(_('Delete'))

        layout.addWidget(self.cache_size)
        layout.addStretch(1)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.delete_button)

        return widget

    def table_widget(self):
        self.cache_list = CacheTableView()
        self.cache_list.setModel(
            CacheTableModel(TranslationCache.get_list()))
        self.selection = self.cache_list.selectionModel()

        return self.cache_list

    def clear(self):
        if self.plugin.clear_caches():
            self.cache_list.model().clear()
            self.cache_count.emit()

    def delete(self):
        for row in reversed(self.selection.selectedRows()):
            cache_path = row.data(Qt.UserRole)
            os.path.exists(cache_path) and os.remove(cache_path)
            self.cache_list.model().delete(row.row())

    def reveal(self):
        cache_path = TranslationCache.cache_path
        if not os.path.exists(cache_path):
            return self.alert.pop(_('No cache exists.'), 'warning')
        cmd = 'open'
        if sys.platform.startswith('win32'):
            cmd = 'explorer'
        if sys.platform.startswith('linux'):
            cmd = 'xdg-open'
        Popen([cmd, cache_path])

    def recount(self):
        return self.cache_size.setText(
            _('Total: {}').format('%sMB' % TranslationCache.count()))


class CacheTableView(QTableView):
    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().sortIndicatorChanged.connect(self.sortByColumn)


class CacheTableModel(QAbstractTableModel):
    headers = ['Title', 'Size', 'Filename']

    def __init__(self, caches=[]):
        QAbstractTableModel.__init__(self)
        self.caches = caches

    def update(func):
        def wrapper(self, *args):
            self.layoutAboutToBeChanged.emit()
            func(self, *args)
            self.layoutChanged.emit()
        return wrapper

    def headerData(self, section, orientation, role):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.headers[section]
        else:
            return section

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return self.caches[index.row()][index.column()]
        if role == Qt.UserRole:
            return self.caches[index.row()][3]

    @update
    def delete(self, row):
        del self.caches[row]

    @update
    def clear(self):
        del self.caches[:]

    @update
    def sort(self, column, order):
        self.caches = sorted(self.caches, key=lambda item: item[column])
        if order == Qt.DescendingOrder:
            self.caches.reverse()

    def rowCount(self, parent):
        return len(self.caches)

    def columnCount(self, parent):
        return len(self.headers)
