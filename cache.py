import os
import os.path

from qt.core import (  # type: ignore
    Qt, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableView, QAbstractTableModel, QAbstractItemView, pyqtSignal,
    QLineEdit, QFileDialog, QModelIndex, QMenu, QCursor)

from calibre.utils.localization import _  # type: ignore

from .lib.utils import open_path
from .lib.cache import default_cache_path, TranslationCache
from .lib.config import get_config
from .components import Footer, AlertMessage


load_translations()  # type: ignore


class CacheManager(QDialog):
    cache_count = pyqtSignal()

    def __init__(self, plugin, parent):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.gui = parent
        self.config = get_config()
        self.alert = AlertMessage(self)
        self.footer = Footer()
        self.default_path = default_cache_path()

        self.cache_size = QLabel()
        self.footer.layout().insertWidget(0, self.cache_size)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.control_widget())
        self.layout.addWidget(self.table_widget())
        self.layout.addWidget(self.enable_widget())
        self.layout.addWidget(self.footer)

        self.cache_list.selected_rows.connect(
            lambda rows: self.delete_button.setDisabled(len(rows) < 1))

        def clear_button_status():
            self.clear_button.setDisabled(
                self.cache_list.model().rowCount() < 1)
        clear_button_status()
        self.cache_list.model().layoutChanged.connect(clear_button_status)

        self.cache_path.setText(TranslationCache.dir_path)
        self.cache_reset.setDisabled(
            TranslationCache.dir_path == self.default_path)

        self.cache_count.connect(self.recount)
        self.cache_path.mouseDoubleClickEvent = lambda event: self.move()
        self.cache_move.clicked.connect(self.move)
        self.cache_reset.clicked.connect(self.reset)
        self.cache_reveal.clicked.connect(self.reveal)
        self.clear_button.clicked.connect(self.clear)
        self.delete_button.clicked.connect(self.cache_list.delete_cache)

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
        self.cache_reset = QPushButton(_('Reset'))
        self.cache_reveal = QPushButton(_('Reveal'))

        layout.addWidget(QLabel(_('Cache Path')))
        layout.addWidget(self.cache_path, 1)
        layout.addWidget(self.cache_move)
        layout.addWidget(self.cache_reset)
        layout.addWidget(self.cache_reveal)

        return widget

    def enable_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.clear_button = QPushButton(_('Clear All'))
        self.clear_button.setDisabled(True)
        self.delete_button = QPushButton(_('Delete'))
        self.delete_button.setDisabled(True)

        layout.addWidget(self.clear_button)
        layout.addStretch(1)
        layout.addWidget(self.delete_button)

        return widget

    def table_widget(self):
        self.cache_list = CacheTableView(self.alert, self)
        self.cache_list.setModel(CacheTableModel())

        return self.cache_list

    def reset(self):
        action = self.alert.ask(_(
            'All cache(s) will be moved to the default path. '
            'Are you sure to proceed?'))
        if action != 'yes':
            return
        TranslationCache.move(self.default_path)
        self.cache_list.model().refresh()
        self.cache_path.setText(self.default_path)
        self.cache_reset.setDisabled(True)
        self.config.save(cache_path=None)

    def move(self):
        path = QFileDialog.getExistingDirectory()
        if not path or path == self.default_path:
            return
        action = self.alert.ask(_(
            'All cache(s) will be moved to the new path. '
            'Are you sure to proceed?'))
        if action != 'yes':
            return
        if not os.path.exists(path):
            self.alert.pop(_('The specified path does not exist.'))
            return
        if len([i for i in os.listdir(path) if not i.startswith('.')]) > 0:
            self.alert.pop(_('Please choose an empty folder.'))
            return
        TranslationCache.move(path)
        self.cache_list.model().refresh()
        self.cache_path.setText(path)
        self.cache_reset.setDisabled(False)
        self.config.save(cache_path=path)

    def clear(self):
        action = self.alert.ask(
            _('Are you sure you want to clear all caches?'))
        if action != 'yes':
            return
        TranslationCache.clean()
        self.cache_list.model().clear()
        self.cache_count.emit()

    def reveal(self):
        cache_path = TranslationCache.cache_path
        if not os.path.exists(cache_path):
            return self.alert.pop(_('No cache exists.'), 'warning')
        open_path(cache_path)

    def recount(self):
        return self.cache_size.setText(
            _('Total: {}').format('%sMB' % TranslationCache.count()))


class CacheTableView(QTableView):
    selected_rows = pyqtSignal(list)

    def __init__(self, alert, parent=None):
        QTableView.__init__(self, parent)

        self.alert = alert
        self.parent = parent

        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().sortIndicatorChanged.connect(self.sortByColumn)

    def selectionChanged(self, selected, deselected):
        QTableView.selectionChanged(self, selected, deselected)
        self.selected_rows.emit(self.selectionModel().selectedRows())

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.addAction(_('Delete'), self.delete_cache)
        menu.setMinimumSize(menu.sizeHint())
        menu.setMaximumSize(menu.sizeHint())
        menu.exec_(QCursor.pos())

    def delete_cache(self):
        action = self.alert.ask(
            _('Are you sure you want to delete the selected cache(s)?'))
        if action != 'yes':
            return
        # Collect all selected rows with their data first
        selected_items = [(row.row(), row.data(Qt.UserRole)) for row in self.selectionModel().selectedRows()]
        # Sort by row number descending to delete from bottom to top
        selected_items.sort(key=lambda x: x[0], reverse=True)

        # Delete in reverse order to avoid index shifting issues
        for row_num, filename in selected_items:
            TranslationCache.remove(filename)
            self.model().delete(row_num)
        self.clearSelection()
        if self.parent is not None:
            self.parent.cache_count.emit()


def update_cache(func):
    def wrapper(self, *args):
        self.layoutAboutToBeChanged.emit()
        func(self, *args)
        self.layoutChanged.emit()
    return wrapper


class CacheTableModel(QAbstractTableModel):
    headers = [
        _('Title'), _('Engine'), _('Language'), _('Merge Length'),
        _('Size (MB)'), _('Last Modification Time'), _('Filename'),
    ]

    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.refresh()

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
            return self.caches[index.row()][-1]

    @update_cache
    def refresh(self):
        self.caches = TranslationCache.get_list()

    @update_cache
    def delete(self, row):
        del self.caches[row]

    @update_cache
    def clear(self):
        del self.caches[:]

    @update_cache
    def sort(self, column, order):
        self.caches = sorted(self.caches, key=lambda item: item[column])
        if order == Qt.DescendingOrder:
            self.caches.reverse()

    def rowCount(self, parent=QModelIndex()):
        return len(self.caches)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)
