from ..lib.utils import group
from ..lib.translation import get_engine_class

from .alert import AlertMessage


try:
    from qt.core import (
        Qt, QTableWidget, QHeaderView, QMenu, QAbstractItemView, QCursor,
        QBrush, QTableWidgetItem, pyqtSignal, QTableWidgetSelectionRange,
        QColor, QPalette, QT_VERSION_STR)
except ImportError:
    from PyQt5.Qt import (
        Qt, QTableWidget, QHeaderView, QMenu, QAbstractItemView, QCursor,
        QBrush, QTableWidgetItem, pyqtSignal, QTableWidgetSelectionRange,
        QColor, QPalette, QT_VERSION_STR)

load_translations()


class AdvancedTranslationTable(QTableWidget):
    row = pyqtSignal(int)

    def __init__(self, parent, paragraphs):
        QTableWidget.__init__(self, parent)
        self.parent = parent
        self.paragraphs = paragraphs

        self.non_aligned_count = 0
        # self.setFocusPolicy(Qt.NoFocus)
        self.alert = AlertMessage(self)
        self.layout()

        self.row.connect(self.track_row_data)

    def layout(self):
        self.setRowCount(len(self.paragraphs))
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(
            [_('Original'), _('Engine'), _('Language'), _('Status')])
        self.verticalHeader().setMinimumWidth(28)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        triggers = (getattr(
            QAbstractItemView.EditTrigger, 'NoEditTriggers', None)
            or QAbstractItemView.NoEditTriggers)
        self.setEditTriggers(triggers)
        self.setAlternatingRowColors(True)

        # self.setVerticalHeaderLabels(
        #     map(str, range(1, len(self.paragraphs) + 1)))
        # self.verticalHeader().setStyleSheet(
        #     "QHeaderView::section{background-color:red}")

        for row, paragraph in enumerate(self.paragraphs):
            paragraph.row = row

            vheader = QTableWidgetItem(str(row))
            vheader.setTextAlignment(Qt.AlignCenter)
            self.setVerticalHeaderItem(row, vheader)

            original = QTableWidgetItem(paragraph.original.replace('\n', ' '))
            original.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            original.setData(Qt.UserRole, paragraph)
            engine_name = QTableWidgetItem(paragraph.engine_name)
            engine_name.setToolTip(paragraph.engine_name)
            engine_name.setTextAlignment(Qt.AlignCenter)
            traget_lang = QTableWidgetItem(paragraph.target_lang)
            traget_lang.setToolTip(paragraph.target_lang)
            traget_lang.setTextAlignment(Qt.AlignCenter)
            status = QTableWidgetItem()
            status.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 0, original)
            self.setItem(row, 1, engine_name)
            self.setItem(row, 2, traget_lang)
            self.setItem(row, 3, status)
            self.track_row_data(row)

        header = self.horizontalHeader()
        stretch = (
            getattr(QHeaderView.ResizeMode, 'Stretch', None)
            or QHeaderView.Stretch)
        header.setSectionResizeMode(0, stretch)

    def track_row_data(self, row):
        items = ['--', '--', _('Untranslated')]
        paragraph = self.paragraph(row)
        if paragraph.translation:
            before_aligned = paragraph.aligned
            self.parent.merge_enabled and self.check_line_alignment(paragraph)
            # If the alignment of before and after is the same, do nothing.
            if before_aligned and not paragraph.aligned:
                self.non_aligned_count += 1
            elif not before_aligned and paragraph.aligned:
                self.non_aligned_count -= 1
            items = [
                paragraph.engine_name, paragraph.target_lang, _('Translated')]
        else:
            self.check_translation_error(paragraph)
        for column, text in enumerate(items, 1):
            self.item(row, column).setText(text)

    def _is_light_theme(self):
        return self.palette().color(QPalette.Window).lightness() > 127

    def _normal_row_background_color(self):
        vh_background = vh_foreground = background = QBrush(Qt.NoBrush)
        if QT_VERSION_STR < '6.0.0':
            vh_background = QBrush(QColor(235, 235, 235, 255))
            vh_foreground = QBrush(Qt.black)
        return (vh_background, vh_foreground, background)

    def check_translation_error(self, paragraph):
        if paragraph.error is not None:
            vh_bg = QBrush(
                QColor(255, 100, 100) if self._is_light_theme() else
                QColor(100, 0, 0))
            vh_fg = QBrush(
                Qt.black if self._is_light_theme() else Qt.white)
            bg = QBrush(QColor(255, 0, 0, 100))
            tip = paragraph.error
        else:
            (vh_bg, vh_fg, bg), tip = self._normal_row_background_color(), ''
        self.set_row_background_color(paragraph.row, vh_bg, vh_fg, bg, tip)

    def check_line_alignment(self, paragraph):
        """The header item exhibits a peculiar behavior where setting the
        background color with an alpha value visually has no effect. Emulating
        a native background for PyQt versions lower than 6.0.0, as using
        Qt.NoBrush results in a fully black background.
        """
        engine = get_engine_class(paragraph.engine_name)
        if engine is None or paragraph.is_alignment(engine.separator):
            (vh_bg, vh_fg, bg), tip = self._normal_row_background_color(), ''
            paragraph.aligned = True
        else:
            vh_bg = QBrush(
                QColor(255, 255, 100) if self._is_light_theme() else
                QColor(100, 100, 0))
            vh_fg = QBrush(
                Qt.black if self._is_light_theme() else Qt.white)
            bg = QBrush(QColor(255, 255, 0, 100))
            tip = _(
                'The number of lines differs between the original text and '
                'the translated text.')
            paragraph.aligned = False
        self.set_row_background_color(paragraph.row, vh_bg, vh_fg, bg, tip)

    def set_row_background_color(
            self, row, vh_background, vh_foreground, background, tip):
        item = self.verticalHeaderItem(row)
        item.setBackground(vh_background)
        item.setForeground(vh_foreground)
        item.setToolTip(tip)
        for column in range(self.columnCount()):
            item = self.item(row, column)
            item.setBackground(background)
        item.setToolTip(tip)

    def contextMenuEvent(self, event):
        if self.parent.trans_worker.on_working:
            return
        menu = QMenu()
        menu.addAction(
            _('Translate'), self.parent.translate_selected_paragraph)
        menu.addSeparator()
        menu.addAction(_('Delete'), self.delete_by_rows)
        menu.addSeparator()

        if not self.parent.merge_enabled:
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
        return item.data(Qt.UserRole)

    def current_paragraph(self):
        # return self.paragraph(self.currentRow())
        items = self.get_selected_items()
        return items[0] if len(items) > 0 else None

    def non_aligned_paragraphs(self):
        return [p for p in self.paragraphs if not p.aligned]

    def aligned_paragraphs(self):
        return [p for p in self.paragraphs if p.aligned]

    def untranslated_paragraphs(self):
        return [p for p in self.paragraphs if not p.translation]

    def translated_paragraphs(self):
        return [p for p in self.paragraphs if p.translation]

    def get_selected_rows(self):
        rows = []
        for item_range in self.selectedRanges():
            rows.extend(list(range(
                item_range.topRow(), item_range.bottomRow() + 1)))
        return sorted(rows)

    def selected_count(self):
        return len(self.get_selected_rows())

    def get_selected_items(self, ignore_done=False, select_all=False):
        items = []
        rows = range(self.rowCount()) if select_all else \
            self.get_selected_rows()
        for row in rows:
            paragraph = self.paragraph(row)
            if self.isRowHidden(row):
                continue
            if ignore_done and paragraph.translation:
                continue
            items.append(paragraph)
        return items

    def hide_by_paragraphs(self, paragraphs):
        for paragraph in paragraphs:
            self.hideRow(paragraph.row)

    def show_all_rows(self):
        for row in range(self.rowCount()):
            self.showRow(row)

    def show_by_text(self, text):
        if not text:
            return
        paragraphs = []
        for row in range(self.rowCount()):
            if self.isRowHidden(row):
                continue
            paragraph = self.paragraph(row)
            if text.lower() not in paragraph.original.lower():
                paragraphs.append(paragraph)
        self.hide_by_paragraphs(paragraphs)

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
        paragraphs = self.get_selected_items(False, True)
        for paragraph in paragraphs:
            attributes = paragraph.get_attributes()
            if attributes.get(name) == value:
                rows.append(paragraph.row)
        for bottom, top in group(rows):
            self.setRangeSelected(
                QTableWidgetSelectionRange(bottom, 0, top, 3), True)

    def select_by_page(self, page):
        rows = []
        paragraphs = self.get_selected_items(False, True)
        for paragraph in paragraphs:
            if paragraph.page == page:
                rows.append(paragraph.row)
        for bottom, top in group(rows):
            self.setRangeSelected(
                QTableWidgetSelectionRange(bottom, 0, top, 3), True)
