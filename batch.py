import os
import os.path

from .lib.config import get_config
from .lib.translation import get_engine_class
from .components import (
    layout_info, AlertMessage, SourceLang, TargetLang, InputFormat,
    OutputFormat)


try:
    from qt.core import (
        QDialog, QWidget, QPushButton, QHeaderView, QVBoxLayout, QTableWidget,
        QTableWidgetItem)
except ImportError:
    from PyQt5.Qt import (
        QDialog, QWidget, QPushButton, QHeaderView, QVBoxLayout, QTableWidget,
        QTableWidgetItem)

load_translations()


class BatchTranslation(QDialog):
    def __init__(self, parent, worker, ebooks):
        QDialog.__init__(self, parent)

        self.gui = parent
        self.worker = worker
        self.ebooks = ebooks
        self.alert = AlertMessage(self)

        self.config = get_config()
        self.jobs = {}
        self.source_langs = []
        self.target_langs = []

        self.main_layout()

    def main_layout(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.layout_translate())
        layout.addWidget(layout_info())

    def layout_translate(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        table = QTableWidget()
        table.setStyleSheet('QComboBox{border:0;}')
        table.setRowCount(len(self.ebooks))
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            _('Title'), _('Input Format'), _('Output Format'),
            _('Source Language'), _('Target Language')])

        header = table.horizontalHeader()
        stretch = getattr(QHeaderView.ResizeMode, 'Stretch', None) or \
            QHeaderView.Stretch
        header.setSectionResizeMode(0, stretch)

        translation_engine = get_engine_class()

        for row, ebook in enumerate(self.ebooks):
            ebook_title = QTableWidgetItem(ebook.title)
            ebook_title.setSizeHint(table.sizeHint())
            table.setItem(row, 0, ebook_title)

            input_fmt = InputFormat(ebook.files.keys())
            table.setCellWidget(row, 1, input_fmt)

            output_format = OutputFormat()
            table.setCellWidget(row, 2, output_format)

            exist_format = output_format.findText(ebook.input_format)
            if ebook.is_extra_format() and exist_format:
                output_format.addItem(ebook.input_format)

            def change_input_format(format, row=row):
                ebook = self.ebooks[row]
                ebook.set_input_format(format)
                if ebook.is_extra_format():
                    output_format.lock_format(format)
                else:
                    output_format.unlock_format()
            change_input_format(input_fmt.currentText(), row)
            input_fmt.currentTextChanged.connect(change_input_format)

            def change_output_format(format, row=row):
                self.ebooks[row].set_output_format(format)
            change_output_format(output_format.currentText(), row)
            output_format.currentTextChanged.connect(change_output_format)

            source_lang = SourceLang(book_lang=ebook.source_lang)
            table.setCellWidget(row, 3, source_lang)
            self.source_langs.append(source_lang)

            def change_source_lang(lang, row=row):
                self.ebooks[row].set_source_lang(lang)
            change_source_lang(source_lang.currentText(), row)
            source_lang.currentTextChanged.connect(change_source_lang)

            source_lang.refresh.emit(
                translation_engine.lang_codes.get('source'),
                translation_engine.config.get('source_lang'),
                not translation_engine.is_custom())

            target_lang = TargetLang()
            table.setCellWidget(row, 4, target_lang)
            self.target_langs.append(target_lang)

            def change_target_lang(lang, row=row):
                ebook = self.ebooks[row]
                ebook.set_target_lang(lang)
                ebook.set_lang_code(
                    translation_engine.get_iso639_target_code(lang))
            change_target_lang(target_lang.currentText(), row)
            target_lang.currentTextChanged.connect(change_target_lang)

            target_lang.refresh.emit(
                translation_engine.lang_codes.get('target'),
                translation_engine.config.get('target_lang'))

        layout.addWidget(table)

        start_button = QPushButton(_('Translate'))
        start_button.setStyleSheet(
            'padding:0;height:48;font-size:20px;color:royalblue;'
            'text-transform:uppercase;')
        start_button.clicked.connect(
            lambda: self.translate_ebooks(self.ebooks))
        layout.addWidget(start_button)

        # Change the book title
        table.itemChanged.connect(
            lambda item: self.alter_ebooks_data(
                item.row(), item.text().strip() or _('Unknown')))

        return widget

    def translate_ebooks(self, ebooks):
        to_library = self.config.get('to_library')
        output_path = self.config.get('output_path')
        if not to_library and not os.path.exists(output_path):
            return self.alert.pop(
                _('The specified path does not exist.'), 'warning')
        ebooks = ebooks if isinstance(ebooks, list) else [ebooks]
        for ebook in self.ebooks:
            self.worker.translate_ebook(ebook, is_batch=True)
        self.ebooks.clear()
        self.done(0)
