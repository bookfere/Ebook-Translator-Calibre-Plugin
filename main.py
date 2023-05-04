import re
import os
import zipfile
import os.path
from types import MethodType

from calibre.constants import DEBUG
from calibre.gui2 import Dispatcher
from calibre.ebooks.markdown import markdown
from calibre.utils.localization import get_lang
from calibre.ptempfile import PersistentTemporaryFile
from calibre.ebooks.metadata.meta import get_metadata
from calibre.ebooks.conversion.config import get_output_formats

from calibre_plugins.ebook_translator import EbookTranslator
from calibre_plugins.ebook_translator.config import (
    init_config, save_config, get_config)
from calibre_plugins.ebook_translator.utils import (
    is_proxy_availiable, sorted_mixed_keys)
from calibre_plugins.ebook_translator.engines import builtin_engines
from calibre_plugins.ebook_translator.translator import get_engine_class
from calibre_plugins.ebook_translator.cache import TranslationCache
from calibre_plugins.ebook_translator.components import get_divider
from calibre_plugins.ebook_translator.components.alert import (
    pop_alert, ask_action)
from calibre_plugins.ebook_translator.components.lang import (
    SourceLang, TargetLang)
from calibre_plugins.ebook_translator.components.engine import (
    EngineTester, ManageCustomEngine)


try:
    from qt.core import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QPushButton, QPlainTextEdit,
        QTabWidget, QComboBox, QHeaderView, QHBoxLayout, QVBoxLayout,
        QGroupBox, QTableWidget, QTableWidgetItem, QRegularExpression, QColor,
        QFileDialog, QIntValidator, QScrollArea, QRadioButton, QGridLayout,
        QCheckBox, QTextBrowser, QTextDocument, QButtonGroup, QColorDialog,
        QSpinBox, QPalette, QRegularExpressionValidator, QApplication)
except ImportError:
    from PyQt5.Qt import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QTabWidget, QPlainTextEdit,
        QComboBox, QPushButton, QHeaderView, QHBoxLayout, QVBoxLayout,
        QGroupBox, QTableWidget, QTableWidgetItem, QRegularExpression, QColor,
        QFileDialog, QIntValidator, QScrollArea, QRadioButton, QGridLayout,
        QCheckBox, QTextBrowser, QTextDocument, QButtonGroup, QColorDialog,
        QSpinBox, QPalette, QRegularExpressionValidator, QApplication)

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
        self.config = init_config()

        if not getattr(self.gui, 'bookfere_translate_ebook_jobs', None):
            self.gui.bookfere_translate_ebook_jobs = []

        self.current_engine = get_engine_class(
            self.config.get('translate_engine'))
        self.preferred_language = self.config.get('preferred_language')
        self.source_langs = []
        self.target_langs = []

        self.pop_alert = MethodType(pop_alert, self)
        self.ask_action = MethodType(ask_action, self)

        self.main_layout()

    def main_layout(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.layout_translate(), _('Translate'))
        self.tabs.addTab(self.layout_content(), _('Content'))
        self.tabs.addTab(self.layout_setting(), _('Setting'))
        self.tabs.addTab(self.layout_about(), _('About'))
        self.tabs.setStyleSheet('QTabBar::tab {min-width:120px;}')
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
        github = 'https://github.com/bookfere/Ebook-Translator-Calibre-Plugin'
        if 'zh' in get_lang():
            feedback = 'https://{}/post/1057.html'.format(app_author)
            donate = 'https://{}/donate'.format(app_author)
        else:
            feedback = '{}/issues'.format(github)
            donate = 'https://www.paypal.com/paypalme/bookfere'
        link = QLabel((
            '<a href="{0}">GitHub</a> ｜ <a href="{1}">{3}</a>'
            ' ｜ <a href="{2}">{4}</a>')
            .format(github, feedback, donate, _('Feedback'), _('Donate')))
        link.setOpenExternalLinks(True)
        info_layout.addWidget(link)
        layout.addWidget(info)

    def tabs_bar_clicked_action(self, index):
        index == 1 and self.recount_translation_cache()

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
        stretch = getattr(QHeaderView.ResizeMode, 'Stretch', None) or \
            QHeaderView.Stretch
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
            input_fmt.wheelEvent = lambda event: None
            input_fmt.currentTextChanged.connect(
                lambda fmt, row=index: self.alter_ebooks_data(row, 3, fmt))

            output_fmt = QComboBox()
            for fmt in get_output_formats('epub'):
                output_fmt.addItem(fmt.lower())
                output_fmt.setStyleSheet('text-transform:uppercase;')
            table.setCellWidget(index, 2, output_fmt)
            self.alter_ebooks_data(index, 4, output_fmt.currentText())
            output_fmt.wheelEvent = lambda event: None
            output_fmt.currentTextChanged.connect(
                lambda fmt, row=index: self.alter_ebooks_data(row, 4, fmt))

            source_lang = SourceLang(book_lang=slang)
            table.setCellWidget(index, 3, source_lang)
            self.source_langs.append(source_lang)
            self.alter_ebooks_data(index, 5, source_lang.currentText())
            source_lang.currentTextChanged.connect(
                lambda lang, row=index: self.alter_ebooks_data(row, 5, lang))

            target_lang = TargetLang()
            table.setCellWidget(index, 4, target_lang)
            self.target_langs.append(target_lang)
            self.alter_ebooks_data(index, 6, target_lang.currentText())
            target_lang.currentTextChanged.connect(
                lambda lang, row=index: self.alter_ebooks_data(row, 6, lang))

        self.refresh_lang_codes()

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

        glossary_enabled = get_config('glossary_enabled')
        glossary_path = get_config('glossary_path')
        if glossary_enabled and not os.path.exists(glossary_path):
            return self.pop_alert(
                _('The specified glossary file does not exist.'), 'warning')

        for book_id, title, fmts, ifmt, ofmt, slang, tlang in \
                self.ebooks.values():
            self.translate_ebook(
                book_id, title, fmts, ifmt, ofmt, slang, tlang)
        self.ebooks.clear()
        self.done(0)

    def translate_ebook(self, book_id, title, fmts, ifmt, ofmt, slang, tlang):
        input_path = fmts[ifmt]
        if not get_config('to_library'):
            output_path = os.path.join(
                get_config('output_path'), '%s (%s).%s' % (title, tlang, ofmt))
        else:
            output_path = PersistentTemporaryFile(suffix='.' + ofmt).name

        job = self.gui.job_manager.run_job(
            Dispatcher(self.translate_done),
            'arbitrary_n',
            args=(
                'calibre_plugins.ebook_translator.convertion',
                'convert_book',
                (input_path, output_path, slang, tlang)),
            description=(_('[{} > {}] Translating "{}"')
                         .format(slang, tlang, title)))
        self.jobs[job] = book_id, title, ofmt, output_path
        self.gui.bookfere_translate_ebook_jobs.append(job)

    def translate_done(self, job):
        self.gui.bookfere_translate_ebook_jobs.remove(job)

        if job.failed:
            DEBUG or self.gui.job_exception(
                job, dialog_title=_('Translation job failed'))
            return

        book_id, title, ofmt, output_path = self.jobs.pop(job)

        if get_config('to_library'):
            with open(output_path, 'rb') as file:
                metadata = get_metadata(file, ofmt)
                # metadata.title = title
            book_id = self.db.create_book_entry(metadata)
            self.api.add_format(book_id, ofmt, output_path, run_hooks=False)
            self.gui.library_view.model().books_added(1)
            output_path = self.api.format_abspath(book_id, ofmt)
            # os.remove(temp_file)

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
            icon=self.icon)

    def layout_scroll_area(func):
        def scroll_widget(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)

            scroll_area = QScrollArea(widget)
            scroll_area.setWidgetResizable(True)
            # scroll_area.setFrameStyle(QFrame.NoFrame)
            if not QApplication.instance().is_dark_theme:
                scroll_area.setBackgroundRole(QPalette.Light)
            scroll_area.setWidget(func(self))
            layout.addWidget(scroll_area, 1)

            def save_updated_config():
                if self.tabs.currentIndex() == 1:
                    self.update_content_config()
                else:
                    self.update_setting_config()

            save_button = QPushButton(_('Save'))
            save_button.clicked.connect(save_updated_config)
            layout.addWidget(save_button)

            return widget
        return scroll_widget

    @layout_scroll_area
    def layout_content(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Translation Position
        position_group = QGroupBox(_('Translation Position'))
        position_layout = QHBoxLayout(position_group)
        after_original = QRadioButton(_('Add after original'))
        after_original.setChecked(True)
        before_original = QRadioButton(_('Add before original'))
        delete_original = QRadioButton(_('Add without original'))
        position_layout.addWidget(after_original)
        position_layout.addWidget(before_original)
        position_layout.addWidget(delete_original)
        position_layout.addStretch(1)
        layout.addWidget(position_group)

        position_map = dict(enumerate(['after', 'before', 'only']))
        position_rmap = dict((v, k) for k, v in position_map.items())
        position_btn_group = QButtonGroup(position_group)
        position_btn_group.addButton(after_original, 0)
        position_btn_group.addButton(before_original, 1)
        position_btn_group.addButton(delete_original, 2)

        position_btn_group.button(position_rmap.get(
            self.config.get('translation_position'))).setChecked(True)
        # Check the attribute for compatibility with PyQt5.
        click = getattr(position_btn_group, 'idClicked', None) or \
            position_btn_group.buttonClicked[int]
        click.connect(lambda btn_id: self.config.update(
            translation_position=position_map.get(btn_id)))

        # Translation Color
        color_group = QGroupBox(_('Translation Color'))
        color_layout = QHBoxLayout(color_group)
        self.translation_color = QLineEdit()
        self.translation_color.setPlaceholderText(
            _('CSS color value, e.g., #666666, grey, rgb(80, 80, 80)'))
        self.translation_color.setText(self.config.get('translation_color'))
        color_show = QLabel()
        color_show.setObjectName('color_show')
        color_show.setFixedWidth(25)
        self.setStyleSheet(
            '#color_show{margin:1px 0;border:1 solid #eee;border-radius:2px;}')
        color_button = QPushButton(_('Choose'))
        color_layout.addWidget(color_show)
        color_layout.addWidget(self.translation_color)
        color_layout.addWidget(color_button)
        layout.addWidget(color_group)

        def show_color():
            color = self.translation_color.text()
            valid = QColor(color).isValid()
            color_show.setStyleSheet(
                'background-color:{};border-color:{};'.format(
                    valid and color or 'transparent',
                    valid and color or '#eee'))
        show_color()

        def set_color(color):
            self.translation_color.setText(color.name())
            show_color()

        self.translation_color.textChanged.connect(show_color)

        color_picker = QColorDialog(self)
        color_picker.setOption(getattr(
            QColorDialog.ColorDialogOption, 'DontUseNativeDialog', None)
            or QColorDialog.DontUseNativeDialog)
        color_picker.colorSelected.connect(set_color)
        color_button.clicked.connect(color_picker.open)

        # Merge Translate
        merge_group = QGroupBox(
            '%s %s' % (_('Merge to Translate'), _('(Beta)')))
        merge_layout = QHBoxLayout(merge_group)
        merge_enabled = QCheckBox(_('Enable'))
        self.merge_length = QSpinBox()
        self.merge_length.setRange(1, 99999)
        merge_layout.addWidget(merge_enabled)
        merge_layout.addWidget(self.merge_length)
        merge_layout.addWidget(QLabel(_(
            'The number of characters to translate at one time')))
        merge_layout.addStretch(1)
        layout.addWidget(merge_group)

        self.merge_length.setValue(self.config.get('merge_length'))
        merge_enabled.setChecked(self.config.get('merge_enabled'))
        merge_enabled.clicked.connect(
            lambda checked: self.config.update(merge_enabled=checked))

        # Glossary
        glossary_group = QGroupBox(_('Translation Glossary'))
        glossary_layout = QHBoxLayout(glossary_group)
        self.glossary_enabled = QCheckBox(_('Enable'))
        self.glossary_path = QLineEdit()
        self.glossary_path.setPlaceholderText(_('Choose a glossary file'))
        glossary_choose = QPushButton(_('Choose'))
        glossary_layout.addWidget(self.glossary_enabled)
        glossary_layout.addWidget(self.glossary_path)
        glossary_layout.addWidget(glossary_choose)
        layout.addWidget(glossary_group)

        self.glossary_enabled.setChecked(self.config.get('glossary_enabled'))
        self.glossary_enabled.clicked.connect(
            lambda checked: self.config.update(glossary_enabled=checked))

        self.glossary_path.setText(self.config.get('glossary_path'))

        def choose_glossary_file():
            path = QFileDialog.getOpenFileName(filter="Text files (*.txt)")
            self.glossary_path.setText(path[0])
        glossary_choose.clicked.connect(choose_glossary_file)

        # Filter Content
        filter_group = QGroupBox(_('Do not Translate'))
        filter_layout = QVBoxLayout(filter_group)
        mode_group = QWidget()
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(QLabel(_('Mode:')))
        normal_mode = QRadioButton(_('Normal'))
        normal_mode.setChecked(True)
        inormal_mode = QRadioButton(_('Normal (case-sensitive)'))
        regex_mode = QRadioButton(_('Regular Expression'))
        mode_layout.addWidget(normal_mode)
        mode_layout.addWidget(inormal_mode)
        mode_layout.addWidget(regex_mode)
        mode_layout.addStretch(1)
        tip = QLabel()
        self.filter_rules = QPlainTextEdit()
        self.filter_rules.setMinimumHeight(150)
        self.filter_rules.insertPlainText(
            '\n'.join(self.config.get('filter_rules')))
        filter_layout.addWidget(mode_group)
        filter_layout.addWidget(get_divider())
        filter_layout.addWidget(tip)
        filter_layout.addWidget(self.filter_rules)
        layout.addWidget(filter_group)

        mode_map = dict(enumerate(['normal', 'case', 'regex']))
        mode_rmap = dict((v, k) for k, v in mode_map.items())
        mode_btn_group = QButtonGroup(mode_group)
        mode_btn_group.addButton(normal_mode, 0)
        mode_btn_group.addButton(inormal_mode, 1)
        mode_btn_group.addButton(regex_mode, 2)

        tips = (
            _('Exclude paragraph by keyword. One keyword per line:'),
            _('Exclude paragraph by case-sensitive keyword.'
              ' One keyword per line:'),
            _('Exclude paragraph by regular expression pattern.'
              ' One pattern per line:'),
        )

        def choose_filter_mode(btn_id):
            tip.setText(tips[btn_id])
            self.config.update(rule_mode=mode_map.get(btn_id))

        mode_btn_group.button(mode_rmap.get(
            self.config.get('rule_mode'))).setChecked(True)
        tip.setText(tips[mode_btn_group.checkedId()])

        click = getattr(mode_btn_group, 'idClicked', None) or \
            mode_btn_group.buttonClicked[int]
        click.connect(choose_filter_mode)

        layout.addStretch(1)

        return widget

    @layout_scroll_area
    def layout_setting(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Output Path
        radio_group = QGroupBox(_('Output Path'))
        radio_layout = QHBoxLayout()
        library_radio = QRadioButton(_('Library'))
        self.path_radio = QRadioButton(_('Path'))
        radio_layout.addWidget(library_radio)
        radio_layout.addWidget(self.path_radio)
        self.output_path_entry = QLineEdit()
        self.output_path_entry.setPlaceholderText(
            _('Choose a path to store translated book(s)'))
        self.output_path_entry.setText(self.config.get('output_path'))
        radio_layout.addWidget(self.output_path_entry)
        output_path_button = QPushButton(_('Choose ...'))

        radio_layout.addWidget(output_path_button)
        radio_group.setLayout(radio_layout)
        layout.addWidget(radio_group)

        def choose_output_type(checked):
            output_path_button.setDisabled(checked)
            self.output_path_entry.setDisabled(checked)
            self.config.update(to_library=checked)
        library_radio.toggled.connect(choose_output_type)

        if self.config.get('to_library'):
            library_radio.setChecked(True)
        else:
            self.path_radio.setChecked(True)
        choose_output_type(library_radio.isChecked())

        def choose_output_path():
            path = QFileDialog.getExistingDirectory()
            self.output_path_entry.setText(path)
        output_path_button.clicked.connect(choose_output_path)

        # Translate Engine
        engine_group = QGroupBox(_('Translation Engine'))
        engine_layout = QGridLayout(engine_group)
        engine_list = QComboBox()
        self.api_key = QLineEdit()
        engine_test = QPushButton(_('Test'))
        manage_engine = QPushButton(_('Custom'))
        engine_layout.addWidget(engine_list, 0, 0)
        engine_layout.addWidget(engine_test, 0, 1)
        engine_layout.addWidget(manage_engine, 0, 2)
        engine_layout.addWidget(self.api_key, 1, 0, 1, 3)
        engine_layout.setColumnStretch(0, 1)
        layout.addWidget(engine_group)

        # ChatGPT Prompt
        prompt_group = QGroupBox(_('ChatGPT Prompt'))
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_auto = QLineEdit()
        self.prompt_lang = QLineEdit()
        prompt_layout.addWidget(
            QLabel(_('For auto detecting source language:')))
        prompt_layout.addWidget(self.prompt_auto)
        prompt_layout.addWidget(
            QLabel(_('For specifying source language:')))
        prompt_layout.addWidget(self.prompt_lang)
        layout.addWidget(prompt_group)

        # preferred Language
        preferred_group = QGroupBox(_('Preferred Language'))
        preferred_layout = QGridLayout(preferred_group)
        self.preferred_target = TargetLang()
        self.preferred_target.set_codes(
            self.current_engine.lang_codes.get('target'))
        preferred_layout.addWidget(QLabel(_('Target Language')), 0, 0)
        preferred_layout.addWidget(self.preferred_target, 0, 1)
        preferred_layout.setColumnStretch(1, 1)
        layout.addWidget(preferred_group)

        def choose_default_engine(index):
            engine_name = engine_list.itemData(index)
            self.config.update(translate_engine=engine_name)
            self.current_engine = get_engine_class(engine_name)
            # show api key setting
            need_api_key = self.current_engine.need_api_key
            self.api_key.setVisible(need_api_key)
            if need_api_key:
                api_keys = self.config.get('api_key')
                self.api_key.clear()
                if engine_name in api_keys:
                    self.api_key.setText(api_keys.get(engine_name))
                self.api_key.setPlaceholderText(
                    self.current_engine.api_key_hint)
                self.api_key_validator = QRegularExpressionValidator(
                    QRegularExpression(self.current_engine.api_key_rule))
                self.api_key.setValidator(self.api_key_validator)
            # show prompt setting
            is_chatgpt = self.current_engine.is_chatgpt()
            prompt_group.setVisible(is_chatgpt)
            if is_chatgpt:
                chatgpt = self.current_engine
                prompts = self.config.get('chatgpt_prompt')
                inputs = {'auto': self.prompt_auto, 'lang': self.prompt_lang}
                for name, entry in inputs.items():
                    default_prompt = chatgpt.default_prompts.get(name)
                    entry.setPlaceholderText(default_prompt)
                    entry.setText(prompts.get(name) or default_prompt)
            # refresh preferred language
            self.preferred_target.refresh.emit(
                self.current_engine.lang_codes.get('target'),
                self.preferred_language.get(engine_name))
        engine_list.wheelEvent = lambda event: None
        engine_list.currentIndexChanged.connect(choose_default_engine)

        def refresh_engine_list():
            engine_list.currentIndexChanged.disconnect(choose_default_engine)
            engine_list.clear()
            for engine in builtin_engines:
                engine_list.addItem(_(engine.alias), engine.name)
            custom_engines = self.config.get('custom_engines')
            for name in sorted(custom_engines.keys(), key=sorted_mixed_keys):
                engine_list.addItem(name, name)
            engine_list.setCurrentText(_(self.current_engine.alias))
            choose_default_engine(engine_list.currentIndex())
            engine_list.currentIndexChanged.connect(choose_default_engine)
        refresh_engine_list()

        def manage_custom_translation_engine():
            manager = ManageCustomEngine(self, self.config)
            manager.finished.connect(refresh_engine_list)
            manager.show()
        manage_engine.clicked.connect(manage_custom_translation_engine)

        def make_test_engine():
            translator = self.current_engine()
            api_key = self.api_key.text()
            api_key and translator.set_api_key(api_key)
            self.proxy_enabled.isChecked() and translator.set_proxy(
                [self.proxy_host.text(), self.proxy_port.text()])
            translator.is_chatgpt() and translator.set_prompt(
                self.prompt_auto.text(), self.prompt_lang.text())
            EngineTester(self, translator)
        engine_test.clicked.connect(make_test_engine)

        # Network Proxy
        proxy_group = QGroupBox(_('Network Proxy'))
        proxy_layout = QHBoxLayout()

        self.proxy_enabled = QCheckBox(_('Enable'))
        self.proxy_enabled.setChecked(self.config.get('proxy_enabled'))
        self.proxy_enabled.toggled.connect(
            lambda checked: self.config.update(proxy_enabled=checked))
        proxy_layout.addWidget(self.proxy_enabled)

        self.proxy_host = QLineEdit()
        rule = r'^(http://|)([a-zA-Z\d]+:[a-zA-Z\d]+@|)' \
               r'(([a-zA-Z\d]|-)*[a-zA-Z\d]\.){1,}[a-zA-Z\d]+$'
        self.host_validator = QRegularExpressionValidator(
            QRegularExpression(rule))
        self.proxy_host.setPlaceholderText(_('Host'))
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

        # Miscellaneous
        misc_widget = QWidget()
        misc_layout = QHBoxLayout()
        misc_layout.setContentsMargins(0, 0, 0, 0)

        # Cache
        cache_group = QGroupBox(_('Cache'))
        cache_button = QPushButton(_('Clear'))
        self.cache_count = QLabel()
        self.recount_translation_cache()
        cache_enabled = QCheckBox(_('Enable'))
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.addWidget(cache_enabled)
        cache_layout.addWidget(get_divider())
        cache_layout.addWidget(self.cache_count)
        cache_layout.addWidget(cache_button)
        cache_layout.addStretch(1)
        misc_layout.addWidget(cache_group, 1)

        cache_enabled.setChecked(self.config.get('cache_enabled'))
        cache_enabled.toggled.connect(
            lambda checked: self.config.update(cache_enabled=checked))
        cache_button.clicked.connect(self.clear_translation_cache)

        # Request
        request_group = QGroupBox(_('Request'))
        self.attempt_limit = QSpinBox()
        self.attempt_limit.setRange(0, 9999)
        self.attempt_limit.setValue(self.config.get('request_attempt'))
        self.interval_max = QSpinBox()
        self.interval_max.setRange(1, 9999)
        self.interval_max.setValue(self.config.get('request_interval'))
        request_layout = QVBoxLayout(request_group)
        request_layout.addWidget(QLabel(_('Attempt times (Default 3):')))
        request_layout.addWidget(self.attempt_limit)
        request_layout.addWidget(QLabel(_('Max interval (Default 5s):')))
        request_layout.addWidget(self.interval_max)
        misc_layout.addWidget(request_group, 1)

        # Log
        log_group = QGroupBox(_('Log'))
        log_translation = QCheckBox(_('Show translation'))
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(log_translation)
        log_layout.addStretch(1)
        misc_layout.addWidget(log_group, 1)

        log_translation.setChecked(self.config.get('log_translation'))
        log_translation.toggled.connect(
            lambda checked: self.config.update(log_translation=checked))

        misc_widget.setLayout(misc_layout)
        layout.addWidget(misc_widget)

        layout.addStretch(1)

        return widget

    def clear_translation_cache(self):
        if len(self.gui.bookfere_translate_ebook_jobs) > 0:
            return self.pop_alert(
                _('Cannot clear cache while there are running jobs.'),
                'warning')
        TranslationCache.clean()
        self.recount_translation_cache()

    def recount_translation_cache(self):
        return self.cache_count.setText(
            _('Total: {}').format(TranslationCache.count()))

    def test_proxy_connection(self):
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if not (self.is_valid_data(self.host_validator, host) and port):
            return self.pop_alert(
                _('Proxy host or port is incorrect.'), level='warning')
        if is_proxy_availiable(host, port):
            return self.pop_alert(_('The proxy is available.'))
        return self.pop_alert(_('The proxy is not available.'), 'error')

    def refresh_lang_codes(self):
        lang_codes = self.current_engine.lang_codes
        for source_lang in self.source_langs:
            source_lang.refresh.emit(
                lang_codes.get('source'), not self.current_engine.is_custom())
        for target_lang in self.target_langs:
            target_lang.refresh.emit(
                lang_codes.get('target'),
                self.preferred_language.get(self.current_engine.name))

    def update_content_config(self):
        # Translation color
        translation_color = self.translation_color.text()
        if translation_color and not QColor(translation_color).isValid():
            return self.pop_alert(_('Invalid color value.'), 'warning')
        self.config.update(translation_color=translation_color or None)

        # Glossary file
        if self.config.get('glossary_enabled'):
            glossary_path = self.glossary_path.text()
            if not os.path.exists(glossary_path):
                return self.pop_alert(
                    _('The specified glossary file does not exist.'),
                    'warning')
            self.config.update(glossary_path=glossary_path)

        # Merge length
        self.config.update(merge_length=self.merge_length.value())

        # Filter rules
        rule_content = self.filter_rules.toPlainText()
        filter_rules = filter(None, [r for r in rule_content.split('\n')])
        if self.config.get('rule_mode') == 'regex':
            for rule in filter_rules:
                if not self.is_valid_regex(rule):
                    return self.pop_alert(
                        _('{} is not a valid regular expression.')
                        .format(rule), 'warning')
        self.config.update(filter_rules=list(filter_rules))

        save_config(self.config)
        self.pop_alert(_('The setting has been saved.'))

    def is_valid_data(self, validator, value):
        state = validator.validate(value, 0)[0]
        if isinstance(state, int):
            return state == 2  # Compatible with PyQt5
        return state.value == 2

    def update_setting_config(self):
        # Output path
        output_path = self.output_path_entry.text()
        if not (self.config.get('to_library') or os.path.exists(output_path)):
            return self.pop_alert(
                _('The specified path does not exist.'), 'warning')
        self.config.update(output_path=output_path.strip())

        # API key
        if self.current_engine.need_api_key:
            engine_info = self.config.get('api_key')
            api_key = self.api_key.text()
            if not self.is_valid_data(self.api_key_validator, api_key):
                return self.pop_alert(
                    self.current_engine.get_api_key_error(), 'warning')
            engine_info.update({self.config.get('translate_engine'): api_key})

        # ChatGPT prompt
        if self.current_engine.is_chatgpt():
            self.config.update(chatgpt_prompt={})
            prompt_config = self.config.get('chatgpt_prompt')
            auto_text = self.prompt_auto.text()
            if not ('{tlang}' in auto_text and '{text}' in auto_text):
                return self.pop_alert(
                    _('Prompt must include {} and {}.')
                    .format('{tlang}', '{text}'), 'warning')
            if auto_text != self.current_engine.default_prompts.get('auto'):
                prompt_config.update(auto=auto_text)
            lang_text = self.prompt_lang.text()
            if not ('{slang}' in lang_text and '{tlang}' and lang_text
                    and '{text}' in lang_text):
                return self.pop_alert(
                    _('Prompt must include {}, {} and {}.')
                    .format('{slang}', '{tlang}', '{text}'), 'warning')
            if lang_text != self.current_engine.default_prompts.get('lang'):
                prompt_config.update(lang=lang_text)

        # Preferred Language
        self.preferred_language.update(
            {self.current_engine.name: self.preferred_target.currentText()})

        # Custom engine
        if self.current_engine.is_custom() and len(
                self.config.get('custom_engines')) < 1:
            return self.pop_alert(
                _('Please add a custom translation engine first.'), 'warning')

        # Proxy setting
        proxy_setting = []
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if self.config.get('proxy_enabled') and not (
                self.is_valid_data(self.host_validator, host) and port):
            return self.pop_alert(
                _('Proxy host or port is incorrect.'), level='warning')
        if host:
            proxy_setting.append(host)
        if port:
            proxy_setting.append(int(port))
        self.config.update(proxy_setting=proxy_setting)

        # Request
        self.config.update(
            request_attempt=self.attempt_limit.value(),
            request_interval=self.interval_max.value())

        save_config(self.config)
        self.refresh_lang_codes()
        self.pop_alert(_('The setting has been saved.'))

    def is_valid_regex(self, rule):
        try:
            re.compile(rule)
        except Exception:
            return False
        return True

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
        version = QLabel(EbookTranslator.__version__)
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
            'h1,h2{font-size:large;}p,body > ul{margin:20px 0;}'
            'ul ul {list-style:circle;}ul ul ul{list-style:square;}'
            'ul,ol{-qt-list-indent:0;margin-left:10px;}li{margin:6px 0;}'
            'ol{margin-left:15px;}pre{background-color:#eee;font-size:10px}')
        html = re.sub(r'<img.*?>', '', markdown(self.get_readme()))
        document.setHtml(html)
        description.setDocument(document)
        description.setOpenExternalLinks(True)
        layout.addWidget(description, 2)

        return widget

    def get_readme(self):
        default = 'README.md'
        foreign = default.replace('.', '.%s.' % get_lang().replace('_', '-'))
        resource = self.get_resource(foreign) or self.get_resource(default)
        return resource.decode('utf-8')

    def get_resource(self, filename):
        """Replace the built-in get_resources function because it cannot
        prevent reporting to STDERR in the old version..
        """
        with zipfile.ZipFile(self.plugin.plugin_path) as zf:
            try:
                return zf.read(filename)
            except Exception:
                return None
