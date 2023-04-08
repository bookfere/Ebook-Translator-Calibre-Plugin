from calibre.utils.filenames import ascii_text
from calibre.utils.localization import get_lang, lang_as_iso639_1


try:
    from qt.core import pyqtSignal, pyqtSlot, QComboBox
except ImportError:
    from PyQt5.Qt import pyqtSignal, pyqtSlot, QComboBox


class TargetLang(QComboBox):
    refresh = pyqtSignal(dict)

    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.refresh.connect(self.set_codes)

    @pyqtSlot(dict)
    def set_codes(self, codes):
        default = self.itemText(0)
        current = self.currentText()
        self.clear()
        recommend, rest = [], []
        ui_lang = get_lang().lower()
        for lang in codes:
            code = codes.get(lang).replace('-', '_').lower()
            if code.startswith(lang_as_iso639_1(ui_lang)):
                recommend.append(lang)
            else:
                rest.append(lang)
            if code == ui_lang and current == default:
                current = lang
        langs = sorted(recommend, key=ascii_text)
        langs += sorted(rest, key=ascii_text)
        for lang in langs:
            self.addItem(lang)
        if current and current in codes:
            self.setCurrentText(current)
        else:
            self.setCurrentIndex(0)
