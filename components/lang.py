from qt.core import pyqtSignal, pyqtSlot, QComboBox  # type: ignore
from calibre.utils.filenames import ascii_text  # type: ignore
from calibre.utils.localization import get_lang, lang_as_iso639_1  # type: ignore


load_translations()  # type: ignore


class SourceLang(QComboBox):
    refresh = pyqtSignal(dict, str, bool)

    def __init__(self, parent=None, book_lang=None):
        QComboBox.__init__(self, parent)
        self.book_lang = book_lang
        self.refresh.connect(self.set_codes)
        self.wheelEvent = lambda event: None

    @pyqtSlot(dict, str, bool)
    def set_codes(self, codes, preferred=None, auto_detect=True):
        # current = self.currentText()
        self.clear()
        self.book_lang = lang_as_iso639_1(self.book_lang)
        for lang in sorted(codes, key=ascii_text):
            code = codes.get(lang).lower()
            if self.book_lang is not None and code.startswith(self.book_lang):
                self.insertItem(0, lang)
            else:
                self.addItem(lang)
        if auto_detect:
            self.insertItem(0, _('Auto detect'))
        if preferred and preferred in codes:
            self.setCurrentText(preferred)
        # elif current and current in codes:
        #     self.setCurrentText(current)
        else:
            self.setCurrentIndex(0)


class TargetLang(QComboBox):
    refresh = pyqtSignal(dict, str)

    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.refresh.connect(self.set_codes)
        self.wheelEvent = lambda event: None

    @pyqtSlot(dict, str)
    def set_codes(self, codes, preferred=None):
        self.clear()
        recommend, rest = [], []
        ui_lang = get_lang().lower()
        for lang in codes:
            code = codes.get(lang).replace('-', '_').lower()
            if code.startswith(lang_as_iso639_1(ui_lang)):
                recommend.append(lang)
            else:
                rest.append(lang)
        langs = sorted(recommend, key=ascii_text)
        langs += sorted(rest, key=ascii_text)
        for lang in langs:
            self.addItem(lang)
        if preferred and preferred in codes:
            self.setCurrentText(preferred)
        else:
            self.setCurrentIndex(0)
