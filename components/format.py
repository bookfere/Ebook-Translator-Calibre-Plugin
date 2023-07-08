from calibre.ebooks.conversion.plumber import supported_input_formats

from ..lib.config import get_config


try:
    from qt.core import QComboBox
except ImportError:
    from PyQt5.Qt import QComboBox

try:
    from calibre.ebooks.conversion.config import get_output_formats
except ImportError:
    from calibre.gui2.convert.single import get_output_formats

load_translations()


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
        input_format and self.setCurrentText(input_format)


class OutputFormat(QComboBox):
    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.wheelEvent = lambda event: None
        config = get_config()

        for format in get_output_formats(''):
            self.addItem(format.lower())
            self.setStyleSheet('text-transform:uppercase;')
        self.setCurrentText(config.get('output_format', 'epub'))
