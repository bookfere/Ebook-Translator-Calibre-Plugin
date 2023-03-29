import os
import shutil
import zipfile
import os.path

from calibre.gui2 import Dispatcher
from calibre.gui_launch import ebook_viewer
from calibre.ebooks.markdown import markdown
from calibre.ptempfile import PersistentTemporaryFile
from calibre.ebooks.conversion.config import get_output_formats
from calibre.utils.localization import get_lang, lang_as_iso639_1

from calibre_plugins.ebook_translator import EbookTranslator
from calibre_plugins.ebook_translator.config import (
    init_config, save_config, get_config, set_config)
from calibre_plugins.ebook_translator.utils import (
    is_proxy_availiable, get_language_codes)
from calibre_plugins.ebook_translator.translator import TranslatorBuilder
from calibre_plugins.ebook_translator.cache import TranslationCache


try:
    from qt.core import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QMessageBox, QPushButton,
        QTabWidget, QComboBox, QHeaderView, QHBoxLayout, QVBoxLayout,
        QGroupBox, QTableWidget, QTableWidgetItem, QRegularExpression,
        QFileDialog, QIntValidator, QModelIndex, QRadioButton, QSizePolicy,
        QCheckBox, QFrame, QValidator, QTextBrowser, QTextDocument,
        QRegularExpressionValidator)
except ImportError:
    from PyQt5.Qt import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QMessageBox, QTabWidget,
        QComboBox, QPushButton, QHeaderView, QHBoxLayout, QVBoxLayout,
        QGroupBox, QTableWidget, QTableWidgetItem, QRegularExpression,
        QFileDialog, QIntValidator, QModelIndex, QRadioButton, QSizePolicy,
        QCheckBox, QFrame, QValidator, QTextBrowser, QTextDocument,
        QRegularExpressionValidator)

load_translations()


class MainWindowFrame(QDialog):
    def __init__(self, plugin, icon, ebooks):
        self.gui = plugin.gui
        QDialog.__init__(self, self.gui)
        self.db = self.gui.current_db
        self.api = self.db.new_api
        self.plugin = plugin
        self.icon = icon
        self.ebooks = ebooks
        self.jobs = {}
        self.lang_codes = get_language_codes()
        self.config = {
            'to_library': get_config('to_library', True),
            'output_path': get_config('output_path', None),
            'translate_engine': get_config('translate_engine', 'Google'),
            'api_key': get_config('api_key', {}),
            'proxy_enabled': get_config('proxy_enabled', False),
            'proxy_setting': get_config('proxy_setting', []),
            'request_attempt': get_config('request_attempt', 3),
            'request_interval': get_config('request_interval', 5),
            'cache_enabled': get_config('cache_enabled', True),
            'log_translation': get_config('log_translation', True),
        }
        init_config(self.config.items())

        if not getattr(self.gui, 'bookfere_translate_ebook_jobs', None):
            self.gui.bookfere_translate_ebook_jobs = []

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.layout_translate(), _('Translate'))

        config_widget = QWidget()
        self.config_layout = QVBoxLayout(config_widget)
        self.tabs.addTab(self.layout_config(), _('Setting'))

        self.tabs.addTab(self.layout_about(), _('About'))
        self.tabs.setStyleSheet('QTabBar::tab {width:100px;}')
        layout.addWidget(self.tabs)
        self.tabs.tabBarClicked.connect(self.tabs_bar_clicked_action)

        info = QWidget()
        info.setStyleSheet('color:grey')
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        app_author = EbookTranslator.author
        site = QLabel('♥ by <a href="https://{0}">{0}</a>'.format(app_author))
        site.setOpenExternalLinks(True)
        info_layout.addWidget(site)
        info_layout.addStretch(1)
        link = QLabel((
            '<a href="https://github.com/bookfere/'
            'Ebook-Translator-Calibre-Plugin">GitHub</a>'
            ' ｜ <a href="https://{0}/post/1057.html">{1}</a>'
            ' ｜ <a href="https://{0}/donate">{2}</a>'
        ).format(app_author, _('Feedback'), _('Donate')))
        link.setOpenExternalLinks(True)
        info_layout.addWidget(link)
        layout.addWidget(info)

    def tabs_bar_clicked_action(self, index):
        if index == 1:
            self.recount_translation_cache()

    def layout_translate(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        table = QTableWidget()
        table.setStyleSheet('QComboBox{border:0;}')
        table.setRowCount(len(self.ebooks))
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            _('Title'), _('Input Format'), _('Output Format'),
            _('Source Language'), _('Target Language')
        ])

        header = table.horizontalHeader()
        try:
            stretch = QHeaderView.ResizeMode.Stretch
        except Exception:
            stretch = QHeaderView.Stretch
        header.setSectionResizeMode(0, stretch)

        for index, (
            book_id, title, fmts, ifmt, ofmt, slang, tlang
        ) in self.ebooks.items():
            ebook_title = QTableWidgetItem(title)
            ebook_title.setSizeHint(table.sizeHint())
            table.setItem(index, 0, ebook_title)

            input_fmt = QComboBox()
            for fmt in sorted(fmts.keys()):
                input_fmt.addItem(fmt)
                input_fmt.setStyleSheet('text-transform:uppercase;')
            table.setCellWidget(index, 1, input_fmt)
            self.alter_ebooks_data(index, 3, input_fmt.currentText())
            input_fmt.currentTextChanged.connect(
                lambda fmt, row=index: self.alter_ebooks_data(
                    row, 3, fmt.lower()))

            output_fmt = QComboBox()
            for fmt in get_output_formats('epub'):
                output_fmt.addItem(fmt)
                output_fmt.setStyleSheet('text-transform:uppercase;')
            table.setCellWidget(index, 2, output_fmt)
            self.alter_ebooks_data(index, 4, output_fmt.currentText())
            output_fmt.currentTextChanged.connect(
                lambda fmt, row=index: self.alter_ebooks_data(
                    row, 4, fmt.lower()))

            source_lang = QComboBox()
            book_lang = lang_as_iso639_1(slang)
            for lang, code in self.lang_codes.items():
                if book_lang is not None and not code.startswith(book_lang):
                    source_lang.addItem(lang)
            # recommend language selection
            source_lang.model().sort(0, Qt.AscendingOrder)
            for lang, code in self.lang_codes.items():
                if book_lang is not None and code.startswith(book_lang):
                    source_lang.insertItem(0, lang)
            source_lang.insertItem(0, _('Auto detect'))
            source_lang.setCurrentIndex(0)
            table.setCellWidget(index, 3, source_lang)
            self.alter_ebooks_data(index, 5, source_lang.currentText())
            source_lang.currentTextChanged.connect(
                lambda lang, row=index: self.alter_ebooks_data(row, 5, lang))

            target_lang = QComboBox()
            current_lang = None
            codes = self.lang_codes
            for lang, code in [(k, codes[k]) for k in codes]:
                target_lang.addItem(lang)
                if code.replace('-', '_').lower() == get_lang().lower():
                    current_lang = lang
            target_lang.model().sort(0, Qt.AscendingOrder)
            target_lang.setCurrentText(current_lang)
            table.setCellWidget(index, 4, target_lang)
            self.alter_ebooks_data(index, 6, target_lang.currentText())
            target_lang.currentTextChanged.connect(
                lambda lang, row=index: self.alter_ebooks_data(row, 6, lang))

        layout.addWidget(table)

        start_button = QPushButton(_('Translate'))
        start_button.setStyleSheet(
            'padding:0;height:48;font-size:20px;color:royalblue;'
            'text-transform:uppercase;')
        start_button.clicked.connect(self.translate_ebooks)
        layout.addWidget(start_button)

        # Change the book title
        table.itemChanged.connect(
            lambda item: self.alter_ebooks_data(item.row(), 1, item.text()))

        return widget

    def alter_ebooks_data(self, row, index, data):
        self.ebooks[row][index] = data

    def translate_ebooks(self):
        to_library = get_config('to_library')
        output_path = get_config('output_path')
        if not to_library and not os.path.exists(output_path):
            return self.pop_alert(
                _('The specified path does not exist.'), 'warning')
        for book_id, title, fmts, ifmt, ofmt, slang, tlang in \
                self.ebooks.values():
            self.translate_ebook(
                book_id, title, fmts, ifmt, ofmt, slang, tlang)
        self.ebooks.clear()
        self.done(0)

    def translate_ebook(self, book_id, title, fmts, ifmt, ofmt, slang, tlang):
        input_path = fmts[ifmt]
        output_path = PersistentTemporaryFile(suffix='.' + ofmt).name

        job = self.gui.job_manager.run_job(
            Dispatcher(self.translate_done),
            'arbitrary_n',
            args=(
                'calibre_plugins.ebook_translator.convertion',
                'convert_book',
                (input_path, output_path, slang, tlang),
            ),
            description=(_('[{} > {}] Translating "{}"')
                         .format(slang, tlang, title)))

        job.same_format = ifmt == ofmt
        self.jobs[job] = book_id, title, ofmt, output_path
        self.gui.bookfere_translate_ebook_jobs.append(job)

    def translate_done(self, job):
        self.gui.bookfere_translate_ebook_jobs.remove(job)

        if job.failed:
            return self.gui.job_exception(
                job, dialog_title=_('Failed to translate'))

        book_id, title, ofmt, temp_file = self.jobs.pop(job)

        if not get_config('to_library'):
            output_path = os.path.join(
                get_config('output_path'), '%s.%s' % (title, ofmt))
            shutil.move(temp_file, output_path)
        else:
            if job.same_format:
                self.db.save_original_format(
                    book_id, ofmt, notify=False)

            with open(temp_file, 'rb') as data:
                self.db.add_format(
                    book_id, ofmt, data, index_is_id=True)
            output_path = self.api.format_abspath(book_id, ofmt)
            os.remove(temp_file)

            self.gui.tags_view.recount()
            if self.gui.current_view() is self.gui.library_view:
                lv = self.gui.library_view
                lv.model().refresh_ids((book_id,))
                current = lv.currentIndex()
                if current.isValid():
                    lv.model().current_changed(current, QModelIndex())

        self.gui.status_bar.show_message(
            job.description + ' ' + _('completed'), 5000)

        self.gui.proceed_question(
            lambda payload: payload(
                'ebook-viewer',
                kwargs={'args': ['ebook-viewer', output_path]}),
            self.gui.job_manager.launch_gui_app,
            job.log_path,
            _('Ebook Translation Log'),
            _('Translation Completed'),
            _('The translation of "{}" was completed. '
              'Do you want to open the book?').format(title),
            log_is_file=True,
            icon=self.icon,
        )

    def layout_config(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        radio_group = QGroupBox(_('Output Path'))
        radio_layout = QHBoxLayout()
        self.library_radio = QRadioButton(_('Library'))
        self.path_radio = QRadioButton(_('Path'))
        radio_layout.addWidget(self.library_radio)
        radio_layout.addWidget(self.path_radio)
        self.output_path_entry = QLineEdit()
        self.output_path_entry.setText(self.config.get('output_path'))
        radio_layout.addWidget(self.output_path_entry)
        self.output_path_button = QPushButton(_('Choose ...'))
        self.output_path_button.clicked.connect(self.choose_output_path)
        radio_layout.addWidget(self.output_path_button)
        radio_group.setLayout(radio_layout)
        layout.addWidget(radio_group)

        if self.config.get('to_library'):
            self.library_radio.setChecked(True)
        else:
            self.path_radio.setChecked(True)
        self.choose_output_type(self.library_radio.isChecked())
        self.library_radio.toggled.connect(self.choose_output_type)

        # Translate engine setting

        engine_group = QGroupBox(_('Translate Engine'))
        engine_layout = QVBoxLayout()
        self.translate_engine = QComboBox()
        for engine in sorted(TranslatorBuilder.engines):
            self.translate_engine.addItem(engine)
        engine = self.config.get('translate_engine')
        if engine is not None:
            self.translate_engine.setCurrentText(engine)
        self.translate_engine.currentTextChanged.connect(
            self.choose_translate_engine)
        engine_layout.addWidget(self.translate_engine)
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText(_('API Key'))
        self.choose_translate_engine(self.translate_engine.currentText())
        engine_layout.addWidget(self.api_key)
        engine_group.setLayout(engine_layout)
        layout.addWidget(engine_group)

        # Network Proxy

        proxy_group = QGroupBox(_('Network Proxy'))
        proxy_layout = QHBoxLayout()

        self.proxy_enabled = QCheckBox(_('Enable'))
        self.proxy_enabled.setChecked(self.config.get('proxy_enabled'))
        proxy_layout.addWidget(self.proxy_enabled)

        self.proxy_host = QLineEdit()
        regex = r'^[a-zA-Z\d]([a-zA-Z\d]+(\.|-*)){2,}[a-zA-Z\d]\.[a-zA-Z\d]+$'
        re = QRegularExpression(regex)
        self.host_validator = QRegularExpressionValidator(re)
        self.proxy_host.setPlaceholderText(_('Host'))
        self.proxy_host.setValidator(self.host_validator)
        proxy_layout.addWidget(self.proxy_host, 4)
        self.proxy_port = QLineEdit()
        self.proxy_port.setPlaceholderText(_('Port'))
        port_validator = QIntValidator()
        port_validator.setRange(0, 65536)
        self.proxy_port.setValidator(port_validator)
        proxy_layout.addWidget(self.proxy_port, 1)

        self.proxy_port.textChanged.connect(
            lambda num: self.proxy_port.setText(
                num if not num or int(num) < port_validator.top()
                else str(port_validator.top())))

        proxy_test = QPushButton(_('Test'))
        proxy_test.clicked.connect(self.test_proxy_connection)
        proxy_layout.addWidget(proxy_test)

        proxy_setting = self.config.get('proxy_setting')
        if len(proxy_setting) == 2:
            self.proxy_host.setText(proxy_setting[0])
            self.proxy_port.setText(str(proxy_setting[1]))
        proxy_group.setLayout(proxy_layout)
        layout.addWidget(proxy_group)

        # Miscellaneous setting

        misc_widget = QWidget()
        misc_layout = QHBoxLayout()
        misc_layout.setContentsMargins(0, 0, 0, 0)

        # Cache
        cache_group = QGroupBox(_('Cache'))
        self.cache_button = QPushButton(_('Clear'))
        self.cache_count = QLabel()
        self.recount_translation_cache()
        self.cache_enabled = QCheckBox(_('Enable'))
        cache_layout = QVBoxLayout()
        cache_layout.addWidget(self.cache_enabled)
        cache_layout.addWidget(self.get_divider())
        cache_layout.addWidget(self.cache_count)
        cache_layout.addWidget(self.cache_button)
        cache_layout.addStretch(1)
        cache_group.setLayout(cache_layout)
        misc_layout.addWidget(cache_group, 1)

        self.cache_enabled.setChecked(self.config.get('cache_enabled'))
        self.cache_button.clicked.connect(self.clear_translation_cache)

        # Request
        request_group = QGroupBox(_('Request'))
        request_validator = QIntValidator()
        request_validator.setBottom(0)
        self.attempt_limit = QLineEdit()
        self.attempt_limit.setValidator(request_validator)
        self.attempt_limit.setText(str(self.config.get('request_attempt')))
        self.interval_max = QLineEdit()
        self.interval_max.setValidator(request_validator)
        self.interval_max.setText(str(self.config.get('request_interval')))
        request_layout = QVBoxLayout()
        request_layout.addWidget(QLabel(_('Attempt times (Default 3):')))
        request_layout.addWidget(self.attempt_limit)
        request_layout.addWidget(QLabel(_('Max interval (Default 5s):')))
        request_layout.addWidget(self.interval_max)
        request_layout.addStretch(1)
        request_group.setLayout(request_layout)
        misc_layout.addWidget(request_group, 1)

        # Log
        log_group = QGroupBox(_('Log'))
        self.log_translation = QCheckBox(_('Show translation'))
        log_layout = QVBoxLayout()
        log_layout.addWidget(self.log_translation)
        log_layout.addStretch(1)
        log_group.setLayout(log_layout)
        misc_layout.addWidget(log_group, 1)

        self.log_translation.setChecked(self.config.get('log_translation'))

        misc_widget.setLayout(misc_layout)
        layout.addWidget(misc_widget, 0)

        layout.addStretch(1)

        save_button = QPushButton(_('Save'))
        save_button.setObjectName('save_button')
        save_button.clicked.connect(self.save_config)
        layout.addWidget(save_button)

        return widget

    def choose_output_type(self, checked):
        self.output_path_button.setDisabled(checked)
        self.output_path_entry.setDisabled(checked)

    def clear_translation_cache(self):
        if len(self.gui.bookfere_translate_ebook_jobs) > 0:
            return self.pop_alert(
                _('Can not clear cache while job(s) running.'), 'warning')
        TranslationCache.clean()
        self.recount_translation_cache()

    def recount_translation_cache(self):
        return self.cache_count.setText(
            _('Total: {}').format(TranslationCache.count()))

    def is_valid_proxy_host(self, host):
        state = self.host_validator.validate(host, 0)[0]
        if isinstance(state, int):
            return state == 2
        return state.value == 2

    def test_proxy_connection(self):
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if not host or not self.is_valid_proxy_host(host) or not port:
            return self.pop_alert(
                _('Proxy host or port is incorrect.'), level='warning')
        if is_proxy_availiable(host, port):
            return self.pop_alert(_('The proxy is available.'))
        return self.pop_alert(_('The proxy is not available.'), 'error')

    def choose_translate_engine(self, engine):
        self.api_key.setVisible(engine != 'Google')
        engine_info = self.config.get('api_key')
        current_engine = self.translate_engine.currentText()
        self.api_key.clear()
        if current_engine in engine_info:
            self.api_key.setText(engine_info[current_engine])

    def choose_output_path(self):
        path = QFileDialog.getExistingDirectory()
        self.output_path_entry.setText(path)

    def save_config(self):
        to_library = self.library_radio.isChecked()
        self.config.update(to_library=to_library)

        output_path = self.output_path_entry.text()
        if not to_library and not os.path.exists(output_path):
            return self.pop_alert(
                _('The specified path does not exist.'), 'warning')
        self.config.update(output_path=output_path.strip())

        current_engine = self.translate_engine.currentText()
        self.config.update(translate_engine=current_engine)

        engine_info = self.config.get('api_key')
        api_key = self.api_key.text()
        if self.api_key.isVisible() and not api_key:
            return self.pop_alert(
                _('An API key is required.'), 'warning')
        engine_info.update({current_engine: api_key or None})

        proxy_enabled = self.proxy_enabled.isChecked()
        self.config.update(proxy_enabled=proxy_enabled)

        proxy_setting = []
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if proxy_enabled and (
                not host or not self.is_valid_proxy_host(host) or not port):
            return self.pop_alert(
                _('Proxy host or port is incorrect.'), level='warning')
        self.config.update(proxy_setting=[])
        if host:
            proxy_setting.append(host)
        if port:
            proxy_setting.append(int(port))
        self.config.update(proxy_setting=proxy_setting)

        request_fields = (
            ('request_attempt', self.attempt_limit),
            ('request_interval', self.interval_max),
        )
        for name, value in request_fields:
            if value.text():
                self.config.update({name: int(value.text())})
            else:
                value.setText('0')
                self.config.update({name: 0})

        self.config.update(cache_enabled=self.cache_enabled.isChecked())
        self.config.update(log_translation=self.log_translation.isChecked())

        save_config(self.config.items())
        self.pop_alert(_('The setting was saved.'))

    def layout_about(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.addStretch(1)
        logo = QLabel()
        logo.setPixmap(self.icon.pixmap(80, 80))
        logo.setAlignment(Qt.AlignCenter)
        brand_layout.addWidget(logo)
        name = QLabel(EbookTranslator.title.upper())
        name.setStyleSheet('font-size:20px;font-weight:300;')
        name.setAlignment(Qt.AlignCenter)
        name.setTextFormat(Qt.RichText)
        brand_layout.addWidget(name)
        version = QLabel(EbookTranslator.get_version())
        version.setStyleSheet('font-size:14px;')
        version.setAlignment(Qt.AlignCenter)
        version.setTextFormat(Qt.RichText)
        brand_layout.addWidget(version)
        brand_layout.addStretch(1)
        layout.addWidget(brand, 1)

        description = QTextBrowser()
        document = QTextDocument()
        document.setDocumentMargin(30)
        document.setDefaultStyleSheet(
            'h1,h2{font-size:large;}'
            'p,ul{margin:20px 0;}'
            'ul{-qt-list-indent:0;margin-left:10px;}'
            'li{margin:6px 0;}')
        html = markdown(self.get_readme())
        document.setHtml(html)
        description.setDocument(document)
        description.setOpenExternalLinks(True)
        layout.addWidget(description, 1)

        return widget

    def get_readme(self):
        default = 'README.md'
        foreign = default.replace('.', '.%s.' % get_lang().replace('_', '-'))
        resource = self.get_resource(foreign) or self.get_resource(default)
        return resource.decode()

    def get_resource(self, filename):
        """Replace the built-in get_resources function because it cannot
        prevent reporting to STDERR in the old version..
        """
        with zipfile.ZipFile(self.plugin.plugin_path) as zf:
            try:
                return zf.read(filename)
            except Exception:
                return None

    def pop_alert(self, text, level='info'):
        icons = {
            'info': QMessageBox.Information,
            'warning': QMessageBox.Warning,
            'ask': QMessageBox.Question,
            'error': QMessageBox.Critical,
        }
        alert = QMessageBox(self)
        alert.setIcon(icons[level])
        alert.setText(text)
        alert.exec_()

    def get_divider(self):
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        return divider
