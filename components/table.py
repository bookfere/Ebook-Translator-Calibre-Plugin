from ..lib.utils import group

from .alert import AlertMessage


try:
    from qt.core import (
        Qt, QTableWidget, QHeaderView, QMenu, QAbstractItemView, QCursor,
        QAbstractItemView, QTableWidgetItem, pyqtSignal,
        QTableWidgetSelectionRange)
except ImportError:
    from PyQt5.Qt import (
        Qt, QTableWidget, QHeaderView, QMenu, QAbstractItemView, QCursor,
        QAbstractItemView, QTableWidgetItem, pyqtSignal,
        QTableWidgetSelectionRange)

load_translations()


class AdvancedTranslationTable(QTableWidget):
    row = pyqtSignal(int)

    def __init__(self, parent, paragraphs):
        QTableWidget.__init__(self, parent)
        self.parent = parent
        self.paragraphs = paragraphs
        self.alert = AlertMessage(self)
        self.layout()

        self.row.connect(self.track_row_data)

    def layout(self):
        self.setRowCount(len(self.paragraphs))
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(
            [_('Original'), _('Engine'), _('Language'), _('Status')])

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        triggers = (getattr(
            QAbstractItemView.EditTrigger, 'NoEditTriggers', None)
            or QAbstractItemView.NoEditTriggers)
        self.setEditTriggers(triggers)
        self.setAlternatingRowColors(True)

        for row, paragraph in enumerate(self.paragraphs):
            original = QTableWidgetItem(paragraph.original)
            original.setData(Qt.UserRole, paragraph)
            engine_name = QTableWidgetItem(paragraph.engine_name)
            engine_name.setTextAlignment(Qt.AlignCenter)
            traget_lang = QTableWidgetItem(paragraph.target_lang)
            traget_lang.setTextAlignment(Qt.AlignCenter)
            status = QTableWidgetItem()
            status.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 0, original)
            self.setItem(row, 1, engine_name)
            self.setItem(row, 2, traget_lang)
            self.setItem(row, 3, status)
            self.track_row_data(row)

        header = self.horizontalHeader()
        stretch = (getattr(QHeaderView.ResizeMode, 'Stretch', None)
                   or QHeaderView.Stretch)
        header.setSectionResizeMode(0, stretch)

    def track_row_data(self, row):
        items = ['--', '--', _('Untranslated')]
        paragraph = self.paragraph(row)
        if paragraph.translation:
            items = [
                paragraph.engine_name, paragraph.target_lang, _('Translated')]
        for column, text in enumerate(items, 1):
            self.item(row, column).setText(text)

    def contextMenuEvent(self, event):
        if self.parent.on_working:
            return
        menu = QMenu()
        menu.addAction(
            _('Translate'), self.parent.translate_selected_paragraph)
        menu.addSeparator()
        menu.addAction(_('Delete'), self.delete_by_rows)
        menu.addSeparator()

        menu.addAction(
            _('Select the whole chapter'),
            lambda: self.select_by_page(self.current_paragraph().page))

        attributes = self.current_paragraph().get_attributes()
        for name, value in attributes.items():
            menu.addAction(
                _('Select similar paragraphs: {}="{}"').format(name, value),
                lambda: self.select_by_attribute(name, value))

        menu.setMinimumSize(menu.sizeHint())
        menu.setMaximumSize(menu.sizeHint())
        menu.exec_(QCursor.pos())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Backspace, Qt.Key_Backtab, Qt.Key_Delete):
            self.delete_by_rows()
        QTableWidget.keyPressEvent(self, event)

    def paragraph(self, row):
        item = self.item(row, 0)
        paragraph = item.data(Qt.UserRole)
        paragraph.row = row
        return paragraph

    def current_paragraph(self):
        return self.paragraph(self.currentRow())

    def get_selected_rows(self):
        rows = []
        for item_range in self.selectedRanges():
            rows.extend(list(range(
                item_range.topRow(), item_range.bottomRow() + 1)))
        return sorted(rows)

    def selected_count(self):
        return len(self.get_selected_rows())

    def get_seleted_items(self, ignore_done=False, select_all=False):
        items = []
        rows = range(self.rowCount()) if select_all else \
            self.get_selected_rows()
        for row in rows:
            paragraph = self.paragraph(row)
            if ignore_done and paragraph.translation:
                continue
            items.append(paragraph)
        return items

    def delete_by_rows(self, rows=[]):
        rows = rows or self.get_selected_rows()
        if self.rowCount() == len(rows):
            return self.alert.pop(_('Retain at least one row.'), 'warning')
        if len(rows) < 1:
            return
        self.setCurrentItem(
            self.item(rows[-1] + 1, 0) or self.item(rows[0] - 1, 0))
        paragraphs = []
        for row in reversed(rows):
            paragraphs.append(self.paragraph(row))
            self.removeRow(row)
        self.parent.cache.ignore_paragraphs(paragraphs)

    def select_by_attribute(self, name, value):
        rows = []
        paragraphs = self.get_seleted_items(False, True)
        for paragraph in paragraphs:
            attributes = paragraph.get_attributes()
            if attributes.get(name) == value:
                rows.append(paragraph.row)
        for bottom, top in group(rows):
            self.setRangeSelected(
                QTableWidgetSelectionRange(bottom, 0, top, 3), True)

    def select_by_page(self, page):
        rows = []
        paragraphs = self.get_seleted_items(False, True)
        for paragraph in paragraphs:
            if paragraph.page == page:
                rows.append(paragraph.row)
        for bottom, top in group(rows):
            self.setRangeSelected(
                QTableWidgetSelectionRange(bottom, 0, top, 3), True)
