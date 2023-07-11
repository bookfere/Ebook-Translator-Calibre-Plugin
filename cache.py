import os
import sys
import os.path
from subprocess import Popen

from .lib.cache import default_cache_path, TranslationCache
from .lib.config import get_config
from .components import layout_info, AlertMessage

try:
    from qt.core import (
        Qt, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTableView, QAbstractTableModel, QAbstractItemView, pyqtSignal,
        QLineEdit, QFileDialog)
except ImportError:
    from PyQt5.Qt import (
        Qt, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
        QTableView, QAbstractTableModel, QAbstractItemView, pyqtSignal,
        QLineEdit, QFileDialog)

load_translations()


class CacheManager(QDialog):
    cache_count = pyqtSignal()

    def __init__(self, plugin, parent):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.gui = parent
        self.config = get_config()
        self.alert = AlertMessage(self)
        self.default_path = default_cache_path()

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.control_widget())
        self.layout.addWidget(self.table_widget())
        self.layout.addWidget(self.enable_widget())
        self.layout.addWidget(layout_info())

        self.cache_path.setText(TranslationCache.dir_path)
        self.cache_restore.setDisabled(
            TranslationCache.dir_path == self.default_path)

        self.cache_count.connect(self.recount)
        self.cache_path.mouseDoubleClickEvent = lambda event: self.move()
        self.cache_move.clicked.connect(self.move)
        self.cache_restore.clicked.connect(self.restore)
        self.cache_reveal.clicked.connect(self.reveal)
        self.clear_button.clicked.connect(self.clear)
        self.delete_button.clicked.connect(self.delete)

        self.cache_count.emit()

    def control_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.cache_path = QLineEdit()
        self.cache_path.setReadOnly(True)
        self.cache_path.setPlaceholderText(
            _('Choose a path to store cache files.'))
        self.cache_move = QPushButton(_('Move'))
        self.cache_restore = QPushButton(_('Restore'))
        self.cache_reveal = QPushButton(_('Reveal'))

        layout.addWidget(QLabel(_('Cache path')))
        layout.addWidget(self.cache_path, 1)
        layout.addWidget(self.cache_move)
        layout.addWidget(self.cache_restore)
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
        self.cache_list.setModel(CacheTableModel())
        self.selection = self.cache_list.selectionModel()

        return self.cache_list

    def restore(self):
        TranslationCache.move(self.default_path)
        self.cache_list.model().refresh()
        self.cache_path.setText(self.default_path)
        self.cache_restore.setDisabled(True)
        self.config.save(cache_path=None)

    def move(self):
        path = QFileDialog.getExistingDirectory()
        if not path or path == self.default_path:
            return
        action = self.alert.ask(
            _('Are you sure you want to change the cache path?'))
        if action != 'yes':
            return
        if not os.path.exists(path):
            self.alert.pop(_('The specified path does not exist.'))
            return
        if len([i for i in os.listdir(path) if not i.startswith('.')]) > 0:
            self.alert.pop(_('The specified path is not empty.'))
            return
        TranslationCache.move(path)
        self.cache_list.model().refresh()
        self.cache_path.setText(path)
        self.cache_restore.setDisabled(False)
        self.config.save(cache_path=path)

    def clear(self):
        if self.plugin.clear_caches():
            self.cache_list.model().clear()
            self.cache_count.emit()

    def delete(self):
        for row in reversed(self.selection.selectedRows()):
            cache_path = row.data(Qt.UserRole)
            print(cache_path)
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
    headers = ['Title', 'Engine', 'Size', 'Filename']

    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.refresh()

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
            # The path of the file always appends to the last item.
            return self.caches[index.row()][len(self.headers)]

    @update
    def refresh(self):
        self.caches = TranslationCache.get_list()

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
