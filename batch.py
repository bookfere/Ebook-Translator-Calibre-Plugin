import os
import os.path

from qt.core import (  # type: ignore
    QDialog, QWidget, QPushButton, QHeaderView, QVBoxLayout, QTableWidget,
    QTableWidgetItem, Qt, QComboBox, QHBoxLayout, QApplication)

from calibre.utils.localization import _  # type: ignore

from .lib.config import get_config
from .lib.translation import get_engine_class
from .lib.conversion import extra_formats, ConversionWorker
from .lib.encodings import encoding_list
from .lib.ebook import Ebooks, Ebook
from .engines.custom import CustomTranslate
from .components import (
    Footer, AlertMessage, SourceLang, TargetLang, InputFormat, OutputFormat)


load_translations()  # type: ignore


class BatchTranslation(QDialog):
    def __init__(self, parent, worker: ConversionWorker, ebooks: Ebooks):
        QDialog.__init__(self, parent)

        self.worker: ConversionWorker = worker
        self.ebooks: Ebooks = ebooks
        self.alert = AlertMessage(self)

        self.config = get_config()
        self.source_langs: list[str] = []
        self.target_langs: list[str] = []

        self.main_layout()

    def main_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.layout_translate())
        layout.addWidget(Footer())

    def _cell_widget(self, _widget):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        # _widget.setFixedSize(_widget.sizeHint())
        # _widget.setFixedHeight(_widget.sizeHint().height())
        layout.addWidget(_widget, 1)
        # layout.setAlignment(_widget, Qt.AlignCenter)
        return widget

    def layout_translate(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget()
        table.setAlternatingRowColors(True)
        table.setFocusPolicy(Qt.NoFocus)
        # table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setRowCount(len(self.ebooks))

        headers = (
            _('Title'), _('Encoding'), _('Input Format'), _('Output Format'),
            _('Source Language'), _('Target Language'),
            _('Target Directionality'))
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setMaximumSectionSize(36)

        translation_engine = get_engine_class()
        for row, ebook in enumerate(self.ebooks):
            ebook: Ebook
            ebook_title = QTableWidgetItem(ebook.title)
            table.setItem(row, 0, ebook_title)

            input_fmt = InputFormat(ebook.files.keys())
            table.setCellWidget(row, 2, self._cell_widget(input_fmt))

            output_format = OutputFormat()
            table.setCellWidget(row, 3, self._cell_widget(output_format))

            existed_format = output_format.findText(ebook.input_format)
            if ebook.is_extra_format() and existed_format:
                output_format.addItem(ebook.input_format)

            def change_input_format(format, row=row):
                ebook = self.ebooks[row]
                ebook.set_input_format(format)
                if ebook.is_extra_format():
                    output_format.lock_format(format)
                else:
                    output_format.unlock_format()
                input_fmt.setToolTip(format)
            change_input_format(input_fmt.currentText(), row)
            input_fmt.currentTextChanged.connect(change_input_format)

            def change_output_format(format, row=row):
                self.ebooks[row].set_output_format(format)
                output_format.setToolTip(format)
            change_output_format(output_format.currentText(), row)
            output_format.currentTextChanged.connect(change_output_format)

            source_lang = SourceLang(book_lang=ebook.source_lang)
            table.setCellWidget(row, 4, self._cell_widget(source_lang))
            self.source_langs.append(source_lang)

            def change_source_lang(lang, row=row):
                self.ebooks[row].set_source_lang(lang)
                source_lang.setToolTip(lang)
            change_source_lang(source_lang.currentText(), row)
            source_lang.currentTextChanged.connect(change_source_lang)

            source_lang.refresh.emit(
                translation_engine.lang_codes.get('source'),
                translation_engine.config.get('source_lang'),
                not issubclass(translation_engine, CustomTranslate))

            target_lang = TargetLang()
            table.setCellWidget(row, 5, self._cell_widget(target_lang))
            self.target_langs.append(target_lang)

            target_lang.refresh.emit(
                translation_engine.lang_codes.get('target'),
                translation_engine.config.get('target_lang'))

            if ebook.input_format in extra_formats.keys():
                input_encoding = QComboBox()
                input_encoding.wheelEvent = lambda event: None
                table.setCellWidget(row, 1, self._cell_widget(input_encoding))
                input_encoding.addItems(encoding_list)
                input_encoding.currentTextChanged.connect(
                    lambda encoding, row=row: self.ebooks[row]
                    .set_encoding(encoding))
                input_encoding.currentTextChanged.connect(
                    lambda encoding: input_encoding.setToolTip(encoding))
                # Target directionality
                target_direction = QTableWidgetItem(_('Default'))
                target_direction.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 6, target_direction)
            else:
                input_encoding = QTableWidgetItem(_('Default'))
                input_encoding.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 1, input_encoding)
                # Target directionality
                direction_list = QComboBox()
                direction_list.wheelEvent = lambda event: None
                direction_list.addItem(_('Auto'), 'auto')
                direction_list.addItem(_('Left to Right'), 'ltr')
                direction_list.addItem(_('Right to Left'), 'rtl')
                direction_list.currentIndexChanged.connect(
                    lambda index, row=row: self.ebooks[row]
                    .set_target_direction(direction_list.itemData(index)))
                direction_list.currentTextChanged.connect(
                    lambda direction: direction_list.setToolTip(direction))

                engine_target_lange_codes = \
                    translation_engine.lang_codes.get('target')
                if engine_target_lange_codes is not None and \
                        ebook.target_lang in engine_target_lange_codes:
                    target_lang_code = engine_target_lange_codes[
                        ebook.target_lang]
                    direction = translation_engine.get_lang_directionality(
                        target_lang_code)
                    index = direction_list.findData(direction)
                    direction_list.setCurrentIndex(index)

                table.setCellWidget(row, 6, self._cell_widget(direction_list))

            def change_target_lang(lang, row=row):
                ebook = self.ebooks[row]
                ebook.set_target_lang(lang)
                ebook.set_lang_code(
                    translation_engine.get_iso639_target_code(lang))
                target_lang.setToolTip(lang)
            change_target_lang(target_lang.currentText(), row)
            target_lang.currentTextChanged.connect(change_target_lang)

            table.resizeRowsToContents()
            table.resizeColumnsToContents()

        layout.addWidget(table)

        start_button = QPushButton(_('Translate'))

        btn_text_color = 'royalblue'
        if QApplication.instance().is_dark_theme:
            btn_text_color = 'white'
        start_button.setStyleSheet(
            f'padding:0;height:48;font-size:20px;color:{btn_text_color};'
            'text-transform:uppercase;')
        start_button.clicked.connect(self.translate_ebooks)
        layout.addWidget(start_button)

        # Change the book title
        table.itemChanged.connect(
            lambda item: self.alter_ebooks_data(
                item.row(), item.text().strip() or _('Unknown')))

        return widget

    def translate_ebooks(self):
        output_path = self.config.get('output_path')
        if not self.config.get('to_library', False) and (
                output_path is None or not os.path.exists(output_path)):
            self.alert.pop(
                _('The specified path does not exist.'), 'warning')
            return
        for ebook in self.ebooks:
            self.worker.translate_ebook(ebook, is_batch=True)
        self.ebooks.clear()
        self.done(0)
