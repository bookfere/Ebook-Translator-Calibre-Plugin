from qt.core import QComboBox  # type: ignore
from calibre.ebooks.conversion.plumber import supported_input_formats  # type: ignore
from calibre.ebooks.conversion.config import get_output_formats  # type: ignore

from ..lib.config import get_config


load_translations()  # type: ignore


class InputFormat(QComboBox):
    def __init__(self, formats=None, parent=None):
        QComboBox.__init__(self, parent)
        self.wheelEvent = lambda event: None
        config = get_config()

        if formats is None:
            formats = sorted(list(supported_input_formats()))
            formats.insert(0, _('Ebook Specific'))

        for format in formats:
            self.addItem(format)
            self.setStyleSheet('text-transform:uppercase;')
        input_format = config.get('input_format')
        if input_format:
            self.setCurrentText(input_format)


class OutputFormat(QComboBox):
    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.wheelEvent = lambda event: None
        self.locked_format = None

        config = get_config()
        for format in get_output_formats(''):
            self.addItem(format.lower())
            self.setStyleSheet('text-transform:uppercase;')
        self.setCurrentText(config.get('output_format', 'epub'))

    def lock_format(self, format):
        if self.findText(format) == -1:
            self.locked_format = format
            self.addItem(format.lower())
        self.setCurrentText(format)
        self.setDisabled(True)

    def unlock_format(self):
        if self.findText(self.locked_format) != -1:
            self.removeItem(self.locked_format)
        self.setDisabled(False)
