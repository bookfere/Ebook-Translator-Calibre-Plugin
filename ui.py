import os

from calibre.constants import DEBUG
from calibre.gui2.actions import InterfaceAction
from calibre.ebooks.conversion.config import get_input_format_for_book
from calibre_plugins.ebook_translator import EbookTranslator
from calibre_plugins.ebook_translator.main import MainWindowFrame
# from calibre_plugins.ebook_translator.monitor import MonitorPanel
from calibre_plugins.ebook_translator.components.alert import pop_alert


try:
    from qt.core import QMenu
except ImportError:
    from PyQt5.Qt import QMenu

load_translations()


class EbookTranslatorGui(InterfaceAction):
    name = EbookTranslator.name
    action_spec = (
        _('Translate Book'), None, _('Translate Ebook Content'), None)

    def genesis(self):
        try:
            icon = get_icons('images/icon.png', name)
        except Exception:
            icon = get_icons('images/icon.png')

        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.show_dialog)

        # menu = QMenu(self.gui)
        # test = menu.addAction(_('Translation Monitor'))
        # test.triggered.connect(self.show_monitor)
        # self.qaction.setMenu(menu)

    def show_dialog(self):
        DEBUG and os.environ.update(CALIBRE_DEBUG='1')
        ebooks = self.get_selected_ebooks()

        if len(ebooks) < 1:
            return pop_alert(
                self.gui, _('Please choose at least one book.'), 'warning')

        window = MainWindowFrame(self, self.qaction.icon(), ebooks)
        window.setModal(True)
        window.setMinimumWidth(600)
        window.setMinimumHeight(520)
        window.setWindowTitle(
            '%s - %s' % (EbookTranslator.title, EbookTranslator.__version__))
        window.setWindowIcon(self.qaction.icon())
        window.show()

    # def show_monitor(self):
    #     MonitorPanel(self.gui).show()

    def get_selected_ebooks(self):
        """
        {
            0: [
                'book_id': 123,  # book ID in db
                'test',  # Title
                {
                    'mobi': '/path/to/ebook.mobi',  # Format 1
                    'txt': '/path/to/ebook.txt',  # Format 2
                },
                'txt',  # Input format
                'epub',  # Output format
                'en-US',  # Source language
                'zh-CN',  # Target Language
            ]
        }
        """
        ebooks = {}
        api = self.gui.current_db.new_api
        rows = self.gui.library_view.selectionModel().selectedRows()
        model = self.gui.library_view.model()
        for index, row in enumerate(rows):
            row_number = row.row()
            book_id = model.id(row)
            book_metadata = api.get_proxy_metadata(book_id)
            fmt, fmts = get_input_format_for_book(
                self.gui.current_db, book_id, 'epub')
            ebooks[index] = [
                book_id,
                model.title(row_number),
                dict(zip(
                    map(lambda fmt: fmt.lower(), fmts),
                    map(lambda fmt: api.format_abspath(book_id, fmt), fmts),
                )),
                fmt.lower(),
                None,
                book_metadata.language,
                None,
            ]
        return ebooks
