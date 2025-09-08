import os.path

from qt.core import QMenu, QSettings  # type: ignore
from calibre.utils.localization import _  # type: ignore
from calibre.gui2.actions import InterfaceAction  # type: ignore
from calibre.utils.config_base import plugin_dir  # type: ignore
from calibre.ebooks.conversion.config import (  # type: ignore
    get_input_format_for_book)
from . import EbookTranslator
from .lib.utils import uid
from .lib.ebook import Ebooks
from .lib.config import get_config, upgrade_config
from .lib.conversion import (
    ConversionWorker, extra_formats as predefined_extra_formats)
from .batch import BatchTranslation
from .setting import TranslationSetting
from .cache import CacheManager
from .about import AboutDialog
from .components import AlertMessage, ModeSelection
from .advanced import CreateTranslationProject, AdvancedTranslation


load_translations()  # type: ignore

upgrade_config()


class EbookTranslatorGui(InterfaceAction):
    name = EbookTranslator.name
    action_spec = (
        _('Translate Book'), None, _('Translate Ebook Content'), None)
    title = '%s - %s' % (EbookTranslator.title, EbookTranslator.__version__)
    ui_settings = QSettings(os.path.join(
        plugin_dir, EbookTranslator.identifier, 'settings.ini'),
        QSettings.Format.IniFormat)

    class Status:
        jobs: dict[object, tuple] = {}
        windows: dict[str, object] = {}

    def genesis(self):
        try:
            self.icon = get_icons('images/icon.png', self.name)  # type: ignore
        except Exception:
            self.icon = get_icons('images/icon.png')  # type: ignore

        menu = QMenu(self.gui)
        menu.addAction(
            _('Advanced Mode'), self.show_advanced_translation)
        menu.addAction(_('Batch Mode'), self.show_batch_translation)
        menu.addSeparator()
        menu.addAction(_('Cache'), self.show_cache)
        menu.addSeparator()
        menu.addAction(_('Setting'), self.show_setting)
        menu.addAction(_('About'), self.show_about)

        self.qaction.setMenu(menu)
        self.qaction.setIcon(self.icon)
        self.qaction.triggered.connect(self.select_preferred_mode)

        self.alert = AlertMessage(self.gui)

        if not getattr(self.gui, 'bookfere_ebook_translator', False):
            self.gui.bookfere_ebook_translator = self.Status()

    def advanced_translation_window(self, ebook):
        name = 'advanced_' + uid(ebook.get_input_path())
        if self.show_window(name):
            return
        worker = ConversionWorker(self.gui, self.icon)
        window = AdvancedTranslation(self, self.gui, worker, ebook)
        window.setMinimumWidth(1200)
        window.setMinimumHeight(680)
        window.setWindowTitle(
            '%s - %s' % (_('Advanced Mode'), self.title))
        window.show()
        self.add_window(name, window)

    def show_advanced_translation(self):
        ebooks = self.get_selected_ebooks()
        if len(ebooks) < 1:
            return self.alert.pop(
                _('Please choose a book.'), 'warning')
        window = CreateTranslationProject(self.gui, ebooks.first())
        window.start_translation.connect(self.advanced_translation_window)
        window.setModal(True)
        window.setWindowTitle(
            '%s - %s' % (_('Advanced Mode'), self.title))
        window.setWindowTitle(self.title)
        window.show()

    def show_batch_translation(self):
        if self.show_window('batch'):
            return
        ebooks = self.get_selected_ebooks()
        if len(ebooks) < 1:
            return self.alert.pop(
                _('Please choose at least one book.'), 'warning')
        worker = ConversionWorker(self.gui, self.icon)
        window = BatchTranslation(self.gui, worker, ebooks)
        window.setMinimumWidth(1000)
        window.setMinimumHeight(600)
        window.setWindowTitle(
            '%s - %s' % (_('Batch Mode'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('batch', window)

    def show_setting(self):
        if self.has_running_jobs():
            self.alert.pop(_(
                'Cannot change setting while book(s) are under translation.'),
                'warning')
            return
        if self.show_window('setting'):
            return
        window = TranslationSetting(self, self.gui, self.icon)
        window.setModal(True)
        window.setMinimumWidth(600)
        window.setMinimumHeight(520)
        window.setWindowTitle('%s - %s' % (_('Setting'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('setting', window)

    def show_cache(self):
        if self.has_running_jobs():
            self.alert.pop(_(
                'Cannot manage cache while book(s) are under translation.'),
                'warning')
            return
        if self.show_window('cache'):
            return
        window = CacheManager(self, self.gui)
        window.setModal(True)
        window.setMinimumWidth(800)
        window.setMinimumHeight(620)
        window.setWindowTitle('%s - %s' % (_('Cache Manager'), self.title))
        window.setWindowIcon(self.icon)
        window.show()
        self.add_window('cache', window)

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
            modes[preferred_mode]()

    def add_window(self, name, window):
        identifier = name.split('_')[0]

        window_size = 'window_size/%s' % identifier
        size = self.ui_settings.value(window_size)
        if size:
            window.resize(size)

        window_position = 'window_position/%s' % identifier
        position = self.ui_settings.value(window_position)
        if position:
            window.restoreGeometry(position)

        windows = self.gui.bookfere_ebook_translator.windows
        windows[name] = window

        def setup_window():
            self.ui_settings.setValue(window_size, window.size())
            self.ui_settings.setValue(window_position, window.saveGeometry())
            windows.pop(name)
        window.finished.connect(setup_window)

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

    def get_selected_ebooks(self):
        ebooks = Ebooks()
        db = self.gui.current_db
        api = db.new_api
        rows = self.gui.library_view.selectionModel().selectedRows()
        model = self.gui.library_view.model()
        for row in rows:
            row_id = row.row()
            book_id = model.id(row)
            book_metadata = api.get_proxy_metadata(book_id)
            fmt, fmts = None, []
            extra_formats = []
            try:
                fmt, fmts = get_input_format_for_book(db, book_id, 'epub')
            except Exception as e:
                for extra_format in predefined_extra_formats.keys():
                    if api.has_format(book_id, extra_format):
                        if fmt is None:
                            fmt = extra_format
                        fmts.append(extra_format)
                        extra_formats.append(extra_format)
                if fmt is None:
                    raise e
            ebooks.add(
                book_id,  # Book ID in db
                model.title(row_id),  # Title
                # Format and path
                dict(zip(
                    map(lambda fmt: fmt.lower(), fmts),
                    map(lambda fmt: api.format_abspath(book_id, fmt), fmts),
                )),
                fmt.lower(),  # Input format
                book_metadata.language,  # Source language
                extra_formats,
            )
        return ebooks
