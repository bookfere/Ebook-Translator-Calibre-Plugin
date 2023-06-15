from calibre.constants import DEBUG
from calibre.gui2.actions import InterfaceAction

from . import EbookTranslator
from .utils import uid
from .config import get_config, upgrade_config
from .ebook import Ebooks
from .batch import BatchTranslation
from .cache import TranslationCache
from .setting import TranslationSetting
from .about import AboutDialog
from .worker import ConvertionWorker
from .components import AlertMessage, ModeSelection
from .advanced import CreateTranslationProject, AdvancedTranslation


try:
    from calibre.ebooks.conversion.config import get_input_format_for_book
except ImportError:
    from calibre.gui2.convert.single import get_input_format_for_book

try:
    get_input_format_for_book
    from qt.core import QMenu
except ImportError:
    from PyQt5.Qt import QMenu

load_translations()


class EbookTranslatorGui(InterfaceAction):
    name = EbookTranslator.name
    action_spec = (
        _('Translate Book'), None, _('Translate Ebook Content'), None)
    title = '%s - %s' % (EbookTranslator.title, EbookTranslator.__version__)

    class Status:
        jobs = {}
        windows = {}

    def genesis(self):
        try:
            self.icon = get_icons('images/icon.png', self.name)
        except Exception:
            self.icon = get_icons('images/icon.png')

        menu = QMenu(self.gui)
        menu.addAction(
            _('Advanced Mode'), self.show_advanced_translation)
        menu.addAction(_('Batch Mode'), self.show_batch_translation)
        menu.addAction(_('Setting'), self.show_setting)
        menu.addAction(_('About'), self.show_about)
        if DEBUG:
            menu.addSeparator()
            menu.addAction(_('Clear all caches'), self.clear_caches)

        self.qaction.setMenu(menu)
        self.qaction.setIcon(self.icon)
        self.qaction.triggered.connect(self.select_preferred_mode)

        self.alert = AlertMessage(self.gui)

        if not getattr(self.gui, 'bookfere_ebook_translator', None):
            self.gui.bookfere_ebook_translator = self.Status()

        upgrade_config()

    def show_advanced_translation(self):
        ebooks = self.get_selected_ebooks()
        if len(ebooks) < 1:
            return self.alert.pop(
                _('Please choose one single book.'), 'warning')
        ebook = ebooks.first()

        def advanced_translation_window():
            name = 'advanced_' + uid(ebook.get_input_path())
            if self.show_window(name):
                return
            worker = ConvertionWorker(self.gui, self.icon)
            window = AdvancedTranslation(
                self.gui, self.qaction.icon(), worker, ebook)
            window.setMinimumWidth(1200)
            window.setMinimumHeight(700)
            window.setWindowTitle(
                '%s - %s' % (_('Advanced Mode'), self.title))
            window.show()
            self.add_window(name, window)

        window = CreateTranslationProject(self.gui, ebook)
        window.start_translation.connect(advanced_translation_window)
        window.setModal(True)
        window.setWindowTitle(self.title)
        window.show()

    def show_batch_translation(self):
        if self.show_window('batch'):
            return
        ebooks = self.get_selected_ebooks()
        if len(ebooks) < 1:
            return self.alert.pop(
                _('Please choose at least one book.'), 'warning')
        worker = ConvertionWorker(self.gui, self.icon)
        window = BatchTranslation(self.gui, worker, ebooks)
        # window.setModal(True)
        window.setMinimumWidth(600)
        window.setMinimumHeight(520)
        window.setWindowTitle(
            '%s - %s' % (_('Batch Mode'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('batch', window)

    def show_setting(self):
        if self.show_window('setting'):
            return
        window = TranslationSetting(self, self.gui, self.icon)
        window.setMinimumWidth(600)
        window.setMinimumHeight(520)
        window.setWindowTitle('%s - %s' % (_('Setting'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('setting', window)

    def show_about(self):
        if self.show_window('about'):
            return
        window = AboutDialog(self, self.gui, self.icon)
        window.setMinimumWidth(600)
        window.setMinimumHeight(520)
        window.setWindowTitle('%s - %s' % (_('About'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('about', window)

    def select_preferred_mode(self):
        modes = {
            'advanced': self.show_advanced_translation,
            'batch': self.show_batch_translation,
        }
        preferred_mode = get_config().get('preferred_mode')
        if not preferred_mode:
            window = ModeSelection(self.gui)
            window.choose_action.connect(self.select_preferred_mode)
            window.setModal(True)
            window.setMaximumWidth(500)
            window.setMaximumHeight(200)
            window.setWindowTitle(
                '%s - %s' % (_('Choose Translation Mode'), self.title))
            window.show()
        else:
            modes.get(preferred_mode)()

    def add_window(self, name, window):
        windows = self.gui.bookfere_ebook_translator.windows
        windows[name] = window
        window.finished.connect(lambda: windows.pop(name))

    def get_window(self, name):
        return self.gui.bookfere_ebook_translator.windows.get(name)

    def show_window(self, name):
        window = self.get_window(name)
        if not window:
            return False
        window.raise_()
        return True

    def has_running_jobs(self):
        jobs = self.gui.bookfere_ebook_translator.jobs
        if len(jobs) > 0:
            return True
        windows = self.gui.bookfere_ebook_translator.windows
        for name in windows:
            if name.startswith('advanced_'):
                return True
        return False

    def clear_caches(self):
        if self.has_running_jobs():
            return self.alert.pop(
                _('Cannot clear cache while there are running jobs.'),
                'warning')
        action = self.alert.ask(_('Are you sure you want clear all caches?'))
        action == 'yes' and TranslationCache.clean()

    def get_selected_ebooks(self):
        ebooks = Ebooks()
        api = self.gui.current_db.new_api
        rows = self.gui.library_view.selectionModel().selectedRows()
        model = self.gui.library_view.model()
        for row in rows:
            row_id = row.row()
            book_id = model.id(row)
            book_metadata = api.get_proxy_metadata(book_id)
            fmt, fmts = get_input_format_for_book(
                self.gui.current_db, book_id, 'epub')
            ebooks.add(
                book_id,  # book ID in db
                model.title(row_id),  # Title
                dict(zip(
                    map(lambda fmt: fmt.lower(), fmts),  # Format 1
                    map(lambda fmt: api.format_abspath(book_id, fmt),
                        fmts),  # Format 2
                )),
                fmt.lower(),  # Input format
                book_metadata.language,  # Source language
            )
        return ebooks
