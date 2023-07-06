import os
import os.path

try:
    from qt.core import (
        Qt, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel,
        QTableView, QAbstractTableModel, QAbstractItemView)
except ImportError:
    from PyQt5.Qt import (
        Qt, QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel,
        QTableView, QAbstractTableModel, QAbstractItemView)

load_translations()


class CacheManager(QWidget):
    def __init__(self, data, parent=None):
        QWidget.__init__(self, parent)
        self.data = data

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.control_widget())
        self.layout.addWidget(self.table_widget())

    def control_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.cache_enabled = QCheckBox(_('Enable'))
        self.cache_size = QLabel()
        self.cache_reveal = QPushButton(_('Reveal'))
        self.clear_button = QPushButton(_('Clear'))
        self.delete_button = QPushButton(_('Delete'))

        layout.addWidget(self.cache_enabled)
        layout.addStretch(1)
        layout.addWidget(self.cache_size)
        layout.addWidget(self.cache_reveal)
        layout.addWidget(self.clear_button)
        layout.addWidget(self.delete_button)

        return widget

    def table_widget(self):
        self.cache_list = CacheTableView()
        self.cache_list.setModel(CacheTableModel(self.data))
        self.selection = self.cache_list.selectionModel()

        return self.cache_list

    def clear(self):
        self.cache_list.model().clear()

    def delete(self):
        for row in reversed(self.selection.selectedRows()):
            cache_path = row.data(Qt.UserRole)
            os.path.exists(cache_path) and os.remove(cache_path)
            self.cache_list.model().delete(row.row())


class CacheTableView(QTableView):
    def __init__(self, parent=None):
        QTableView.__init__(self, parent)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().sortIndicatorChanged.connect(self.sortByColumn)


class CacheTableModel(QAbstractTableModel):
    headers = ['Title', 'Size (MB)', 'Filename']

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
        self.caches = sorted(self.caches, key=lambda k: k[column])
        if order == Qt.DescendingOrder:
            self.caches.reverse()

    def rowCount(self, parent):
        return len(self.caches)

    def columnCount(self, parent):
        return len(self.headers)
