from calibre.utils.filenames import ascii_text
from calibre.utils.localization import lang_as_iso639_1


try:
    from qt.core import pyqtSignal, pyqtSlot, QComboBox
except ImportError:
    from PyQt5.Qt import pyqtSignal, pyqtSlot, QComboBox

load_translations()


class SourceLang(QComboBox):
    refresh = pyqtSignal(dict)

    def __init__(self, parent=None, book_lang=None):
        QComboBox.__init__(self, parent)
        self.book_lang = book_lang
        self.refresh.connect(self.set_codes)

    @pyqtSlot(dict)
    def set_codes(self, codes):
        current = self.currentText()
        self.clear()
        self.book_lang = lang_as_iso639_1(self.book_lang)
        for lang in sorted(codes, key=ascii_text):
            code = codes.get(lang).lower()
            if self.book_lang is not None and code.startswith(self.book_lang):
                self.insertItem(0, lang)
            else:
                self.addItem(lang)
        self.insertItem(0, _('Auto detect'))
        if current and current in codes:
            self.setCurrentText(current)
        else:
            self.setCurrentIndex(0)
