import re
import os
import sys
import os.path
from subprocess import Popen

from .components import (
    layout_info, AlertMessage, TargetLang, SourceLang, EngineList,
    EngineTester, get_divider, ManageCustomEngine, InputFormat, OutputFormat)
from .config import get_config
from .utils import css, is_proxy_availiable
from .cache import TranslationCache
from .translation import get_engine_class
from .engines import builtin_engines


try:
    from qt.core import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QPushButton, QPlainTextEdit,
        QTabWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QFileDialog, QColor,
        QIntValidator, QScrollArea, QRadioButton, QGridLayout, QCheckBox,
        QButtonGroup, QColorDialog, QSpinBox, QPalette, QApplication,
        QComboBox, QRegularExpression, pyqtSignal, QFormLayout, QDoubleSpinBox,
        QSpacerItem, QRegularExpressionValidator)
except ImportError:
    from PyQt5.Qt import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QPushButton, QPlainTextEdit,
        QTabWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QFileDialog, QColor,
        QIntValidator, QScrollArea, QRadioButton, QGridLayout, QCheckBox,
        QButtonGroup, QColorDialog, QSpinBox, QPalette, QApplication,
        QComboBox, QRegularExpression, pyqtSignal, QFormLayout, QDoubleSpinBox,
        QSpacerItem, QRegularExpressionValidator)

load_translations()


class TranslationSetting(QDialog):
    cache_count = pyqtSignal()
    save_config = pyqtSignal(int)

    def __init__(self, plugin, parent, icon):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.icon = icon
        self.alert = AlertMessage(self)

        self.config = get_config()
        self.current_engine = get_engine_class()

        self.main_layout()

    def main_layout(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        tab_1 = self.tabs.addTab(self.layout_general(), _('General'))
        tab_2 = self.tabs.addTab(self.layout_engine(), _('Engine'))
        tab_3 = self.tabs.addTab(self.layout_content(), _('Content'))
        self.tabs.setStyleSheet('QTabBar::tab {min-width:120px;}')

        config_actions = {
            tab_1: self.update_general_config,
            tab_2: self.update_engine_config,
            tab_3: self.update_content_config,
        }
        self.save_config.connect(lambda index: config_actions.get(index)())

        def tabs_clicked(index):
            index == 0 and self.cache_count.emit()
            self.config.refresh()
        self.tabs.tabBarClicked.connect(tabs_clicked)

        layout.addWidget(self.tabs)
        layout.addWidget(layout_info())

    def layout_scroll_area(func):
        def scroll_widget(self):
            widget = QWidget()
            layout = QVBoxLayout(widget)

            scroll_area = QScrollArea(widget)
            scroll_area.setWidgetResizable(True)
            # Compatible with lower versions of Calibre
            instance = QApplication.instance()
            if not (getattr(instance, 'is_dark_theme', None) and
                    instance.is_dark_theme):
                scroll_area.setBackgroundRole(QPalette.Light)
            scroll_area.setWidget(func(self))
            layout.addWidget(scroll_area, 1)

            save_button = QPushButton(_('Save'))
            layout.addWidget(save_button)

            save_button.clicked.connect(
                lambda: self.save_config.emit(self.tabs.currentIndex()))

            return widget
        return scroll_widget

    @layout_scroll_area
    def layout_general(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Preferred Method
        mode_group = QGroupBox(_('Preferred Mode'))
        mode_layout = QGridLayout(mode_group)
        advanced_mode = QRadioButton(_('Advanced Mode'))
        batch_mode = QRadioButton(_('Batch Mode'))
        icon_button = QLabel()
        icon_button.setPixmap(self.icon.pixmap(52, 52))
        mode_layout.addWidget(icon_button, 0, 0, 3, 1)
        mode_layout.addWidget(advanced_mode, 0, 1)
        mode_layout.addWidget(batch_mode, 0, 2)
        mode_layout.addItem(QSpacerItem(0, 0), 0, 3)
        mode_layout.addWidget(get_divider(), 1, 1, 1, 4)
        mode_layout.addWidget(QLabel(
            _('Choose a translation mode for clicking the icon button.')),
            2, 1, 1, 4)
        mode_layout.setColumnStretch(3, 1)
        layout.addWidget(mode_group)

        mode_map = dict(enumerate(['advanced', 'batch']))
        mode_rmap = dict((v, k) for k, v in mode_map.items())
        mode_btn_group = QButtonGroup(mode_group)
        mode_btn_group.addButton(advanced_mode, 0)
        mode_btn_group.addButton(batch_mode, 1)

        preferred_mode = self.config.get('preferred_mode')
        if preferred_mode is not None:
            mode_btn_group.button(
                mode_rmap.get(preferred_mode)).setChecked(True)
        mode_btn_click = getattr(mode_btn_group, 'idClicked', None) \
            or mode_btn_group.buttonClicked[int]
        mode_btn_click.connect(
            lambda btn_id: self.config.update(
                preferred_mode=mode_map.get(btn_id)))

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
        output_path_button = QPushButton(_('Choose...'))

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

        # preferred Format
        format_group = QGroupBox(_('Preferred Format'))
        format_layout = QFormLayout(format_group)
        input_format = InputFormat()
        output_format = OutputFormat()
        format_layout.addRow(_('Input Format'), input_format)
        format_layout.addRow(_('Output Format'), output_format)
        layout.addWidget(format_group)

        self.set_form_layout_policy(format_layout)

        input_format.setCurrentText(self.config.get('input_format'))
        output_format.setCurrentText(self.config.get('output_format'))

        def change_input_format(format):
            if format == _('Ebook Specific'):
                self.config.delete('input_format')
            else:
                self.config.update(input_format=format)
        input_format.currentTextChanged.connect(change_input_format)
        output_format.currentTextChanged.connect(
            lambda format: self.config.update(output_format=format))

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
            'The number of characters to translate at once.')))
        merge_layout.addStretch(1)
        layout.addWidget(merge_group)

        self.disable_wheel_event(self.merge_length)

        self.merge_length.setValue(self.config.get('merge_length'))
        merge_enabled.setChecked(self.config.get('merge_enabled'))
        merge_enabled.clicked.connect(
            lambda checked: self.config.update(merge_enabled=checked))

        # Network Proxy
        proxy_group = QGroupBox(_('HTTP Proxy'))
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
        cache_reveal = QPushButton(_('Reveal'))
        cache_size = QLabel()
        cache_enabled = QCheckBox(_('Enable'))
        cache_layout = QVBoxLayout(cache_group)
        cache_layout.addWidget(cache_enabled)
        cache_layout.addWidget(get_divider())
        cache_layout.addWidget(cache_size)
        cache_layout.addWidget(cache_button)
        cache_layout.addWidget(cache_reveal)
        cache_layout.addStretch(1)
        misc_layout.addWidget(cache_group, 1)

        def recount_translation_cache():
            return cache_size.setText(
                _('Total: {}').format(TranslationCache.count()))
        self.cache_count.connect(recount_translation_cache)

        cache_enabled.setChecked(self.config.get('cache_enabled'))
        cache_enabled.toggled.connect(
            lambda checked: self.config.update(cache_enabled=checked))

        def clear_translation_cache():
            self.plugin.clear_caches()
            self.cache_count.emit()
        self.cache_count.emit()
        cache_button.clicked.connect(clear_translation_cache)

        def reveal_cache_files():
            cache_dir = TranslationCache.get_dir()
            if not os.path.exists(cache_dir):
                return self.alert.pop(_('No cache exists.'), 'warning')
            cmd = 'open'
            if sys.platform.startswith('win32'):
                cmd = 'explorer'
            if sys.platform.startswith('linux'):
                cmd = 'xdg-open'
            Popen([cmd, cache_dir])
        cache_reveal.clicked.connect(reveal_cache_files)

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

    @layout_scroll_area
    def layout_engine(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Translate Engine
        engine_group = QGroupBox(_('Translation Engine'))
        engine_layout = QHBoxLayout(engine_group)
        engine_list = EngineList(self.current_engine.name)
        engine_test = QPushButton(_('Test'))
        manage_engine = QPushButton(_('Custom'))
        engine_layout.addWidget(engine_list, 1)
        engine_layout.addWidget(engine_test)
        engine_layout.addWidget(manage_engine)
        layout.addWidget(engine_group)

        # API Keys
        self.keys_group = QGroupBox(_('API Keys'))
        keys_layout = QVBoxLayout(self.keys_group)
        self.api_keys = QPlainTextEdit()
        self.api_keys.setFixedHeight(100)
        auto_change = QLabel('%s %s' % (_('Tip:'), _(
            'API keys will auto-switch if the previous one is unavailable.')))
        auto_change.setVisible(False)
        keys_layout.addWidget(self.api_keys)
        keys_layout.addWidget(auto_change)
        layout.addWidget(self.keys_group)

        self.api_keys.textChanged.connect(lambda: auto_change.setVisible(
            len(self.api_keys.toPlainText().strip().split('\n')) > 1))

        # preferred Language
        language_group = QGroupBox(_('Preferred Language'))
        language_layout = QFormLayout(language_group)
        self.source_lang = SourceLang()
        self.target_lang = TargetLang()
        language_layout.addRow(_('Source Language'), self.source_lang)
        language_layout.addRow(_('Target Language'), self.target_lang)
        layout.addWidget(language_group)

        self.set_form_layout_policy(language_layout)

        # Network Request
        request_group = QGroupBox(_('HTTP Request'))
        concurrency_limit = QSpinBox()
        concurrency_limit.setRange(0, 9999)
        if sys.version_info < (3, 7, 0):
            concurrency_limit.setValue(1)
            concurrency_limit.setDisabled(True)
        request_interval = QDoubleSpinBox()
        request_interval.setRange(0, 9999)
        request_interval.setDecimals(1)
        request_attempt = QSpinBox()
        request_attempt.setRange(0, 9999)
        request_timeout = QDoubleSpinBox()
        request_timeout.setRange(0, 9999)
        request_timeout.setDecimals(1)
        request_layout = QFormLayout(request_group)
        request_layout.addRow(_('Concurrency limit'), concurrency_limit)
        request_layout.addRow(_('Interval (seconds)'), request_interval)
        request_layout.addRow(_('Attempt times'), request_attempt)
        request_layout.addRow(_('Timeout (seconds)'), request_timeout)
        layout.addWidget(request_group, 1)

        concurrency_limit.valueChanged.connect(
            lambda value: self.current_engine.config.update(
            concurrency_limit=round(value, 1)))
        request_attempt.valueChanged.connect(
            lambda value: self.current_engine.config.update(
            request_attempt=round(value, 1)))
        request_interval.valueChanged.connect(
            lambda value: self.current_engine.config.update(
            request_interval=round(value, 1)))
        request_timeout.valueChanged.connect(
            lambda value: self.current_engine.config.update(
            request_timeout=round(value, 1)))

        self.set_form_layout_policy(request_layout)
        self.disable_wheel_event(concurrency_limit)
        self.disable_wheel_event(request_attempt)
        self.disable_wheel_event(request_interval)
        self.disable_wheel_event(request_timeout)

        # ChatGPT Setting
        chatgpt_group = QGroupBox(_('Tune ChatGPT'))
        chatgpt_group.setVisible(False)
        endpoint_layout = QFormLayout(chatgpt_group)
        self.set_form_layout_policy(endpoint_layout)

        self.prompt = QPlainTextEdit()
        self.prompt.setMinimumHeight(80)
        self.prompt.setMaximumHeight(80)
        endpoint_layout.addRow(_('Prompt'), self.prompt)
        self.chatgpt_endpoint = QLineEdit()
        endpoint_layout.addRow(_('Endpoint'), self.chatgpt_endpoint)

        chatgpt_model = QComboBox()
        endpoint_layout.addRow(_('Model'), chatgpt_model)

        chatgpt_model.currentTextChanged.connect(
            lambda model: self.current_engine.config.update(model=model))

        self.disable_wheel_event(chatgpt_model)

        sampling_widget = QWidget()
        sampling_layout = QHBoxLayout(sampling_widget)
        sampling_layout.setContentsMargins(0, 0, 0, 0)
        temperature = QRadioButton('temperature')
        temperature_value = QDoubleSpinBox()
        temperature_value.setDecimals(1)
        temperature_value.setSingleStep(0.1)
        temperature_value.setRange(0, 2)
        top_p = QRadioButton('top_p')
        top_p_value = QDoubleSpinBox()
        top_p_value.setDecimals(1)
        top_p_value.setSingleStep(0.1)
        top_p_value.setRange(0, 1)
        sampling_layout.addWidget(temperature)
        sampling_layout.addWidget(temperature_value)
        sampling_layout.addSpacing(20)
        sampling_layout.addWidget(top_p)
        sampling_layout.addWidget(top_p_value)
        sampling_layout.addStretch(1)
        endpoint_layout.addRow(_('Sampling'), sampling_widget)

        self.disable_wheel_event(temperature_value)
        self.disable_wheel_event(top_p_value)

        stream_enabled = QCheckBox(_('Enable streaming text like in ChatGPT'))
        endpoint_layout.addRow(_('Stream'), stream_enabled)

        temperature_value.valueChanged.connect(
            lambda value: self.current_engine.config.update(
            temperature=round(value, 1)))

        sampling_btn_group = QButtonGroup(sampling_widget)
        sampling_btn_group.addButton(temperature, 0)
        sampling_btn_group.addButton(top_p, 1)

        def change_sampling_method(button):
            self.current_engine.config.update(sampling=button.text())
        sampling_btn_group.buttonClicked.connect(change_sampling_method)

        top_p_value.valueChanged.connect(
            lambda value: self.current_engine.config.update(top_p=value))

        layout.addWidget(chatgpt_group)

        def show_chatgpt_preferences():
            if not self.current_engine.is_chatgpt():
                chatgpt_group.setVisible(False)
                return
            config = self.current_engine.config
            # Prompt
            self.prompt.setPlaceholderText(self.current_engine.prompt)
            self.prompt.setPlainText(
                config.get('prompt', self.current_engine.prompt))
            # Endpoint
            self.chatgpt_endpoint.setPlaceholderText(
                self.current_engine.endpoint)
            self.chatgpt_endpoint.setText(
                config.get('endpoint', self.current_engine.endpoint))
            # Model
            chatgpt_model.clear()
            chatgpt_model.addItems(self.current_engine.models)
            chatgpt_model.setCurrentText(
                config.get('model', self.current_engine.model))
            # Sampling
            sampling = config.get('sampling', self.current_engine.sampling)
            btn_id = self.current_engine.samplings.index(sampling)
            sampling_btn_group.button(btn_id).setChecked(True)

            temperature_value.setValue(
                config.get('temperature', self.current_engine.temperature))
            top_p_value.setValue(
                config.get('top_p', self.current_engine.top_p))
            # Stream
            stream_enabled.setChecked(
                config.get('stream', self.current_engine.stream))
            stream_enabled.toggled.connect(
                lambda checked: config.update(stream=checked))
            chatgpt_group.setVisible(True)

        def choose_default_engine(index):
            engine_name = engine_list.itemData(index)
            if self.current_engine.name != engine_name:
                self.config.update(translate_engine=engine_name)
                self.current_engine = get_engine_class(engine_name)
            # refresh preferred language
            source_lang = self.current_engine.config.get('source_lang')
            self.source_lang.refresh.emit(
                self.current_engine.lang_codes.get('source'), source_lang,
                not self.current_engine.is_custom())
            target_lang = self.current_engine.config.get('target_lang')
            self.target_lang.refresh.emit(
                self.current_engine.lang_codes.get('target'), target_lang)
            self.set_api_keys()  # show api key setting
            # Request setting
            concurrency_limit.setValue(
                self.current_engine.config.get(
                'concurrency_limit', self.current_engine.concurrency_limit))
            request_attempt.setValue(
                self.current_engine.config.get(
                'request_attempt', self.current_engine.request_attempt))
            request_interval.setValue(
                self.current_engine.config.get(
                'request_interval', self.current_engine.request_interval))
            request_timeout.setValue(
                self.current_engine.config.get(
                'request_timeout', self.current_engine.request_timeout))
            # show prompt setting
            show_chatgpt_preferences()
        choose_default_engine(engine_list.findData(self.current_engine.name))
        engine_list.currentIndexChanged.connect(choose_default_engine)

        def refresh_engine_list():
            """Prevent engine list auto intercept the text changed signal."""
            engine_list.currentIndexChanged.disconnect(choose_default_engine)
            engine_list.refresh()
            index = engine_list.findData(self.config.get('translate_engine'))
            choose_default_engine(index)
            engine_list.setCurrentIndex(index)
            engine_list.currentIndexChanged.connect(choose_default_engine)

        def manage_custom_translation_engine():
            manager = ManageCustomEngine(self)
            manager.finished.connect(refresh_engine_list)
            manager.show()
        manage_engine.clicked.connect(manage_custom_translation_engine)

        def make_test_translator():
            config = self.get_engine_config()
            if config is not None:
                self.current_engine.set_config(config)
                translator = self.current_engine()
                self.proxy_enabled.isChecked() and translator.set_proxy(
                    [self.proxy_host.text(), self.proxy_port.text()])
                EngineTester(self, translator)
        engine_test.clicked.connect(make_test_translator)

        layout.addStretch(1)

        return widget

    def set_api_keys(self):
        need_api_key = self.current_engine.need_api_key
        self.keys_group.setVisible(need_api_key)
        if need_api_key:
            self.api_keys.clear()
            self.api_keys.setPlaceholderText(
                self.current_engine.api_key_hint)
            api_keys = self.current_engine.config.get('api_keys', [])
            for api_key in api_keys:
                self.api_keys.appendPlainText(api_key)

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
        position_btn_click = getattr(position_btn_group, 'idClicked', None) \
            or position_btn_group.buttonClicked[int]
        position_btn_click.connect(lambda btn_id: self.config.update(
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
                'background-color:{};border-color:{};'
                .format(valid and color or 'transparent',
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

        # Filter element
        element_group = QGroupBox(_('Ignore Element'))
        element_layout = QVBoxLayout(element_group)
        self.element_rules = QPlainTextEdit()
        self.element_rules.setMinimumHeight(100)
        self.element_rules.insertPlainText(
            '\n'.join(self.config.get('element_rules')))

        element_layout.addWidget(QLabel(
            _('CSS selectors to exclude elements. One rule per line:')))
        element_layout.addWidget(self.element_rules)
        element_layout.addWidget(QLabel('%s %s' % (
            _('e.g.'), 'table, table#report, table.list')))
        layout.addWidget(element_group)

        # Filter Content
        filter_group = QGroupBox(_('Ignore Paragraph'))
        filter_layout = QVBoxLayout(filter_group)

        scope_group = QWidget()
        scope_layout = QHBoxLayout(scope_group)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.addWidget(QLabel(_('Scope')))
        scope_text = QRadioButton(_('Text only'))
        scope_text.setChecked(True)
        scope_element = QRadioButton(_('HTML element'))
        scope_layout.addWidget(scope_text)
        scope_layout.addWidget(scope_element, 1)

        mode_group = QWidget()
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(QLabel(_('Mode')))
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
        self.filter_rules.setMinimumHeight(100)
        self.filter_rules.insertPlainText(
            '\n'.join(self.config.get('filter_rules')))

        filter_layout.addWidget(scope_group)
        filter_layout.addWidget(mode_group)
        filter_layout.addWidget(get_divider())
        filter_layout.addWidget(tip)
        filter_layout.addWidget(self.filter_rules)
        layout.addWidget(filter_group)

        scope_map = dict(enumerate(['text', 'html']))
        scope_rmap = dict((v, k) for k, v in scope_map.items())
        scope_btn_group = QButtonGroup(scope_group)
        scope_btn_group.addButton(scope_text, 0)
        scope_btn_group.addButton(scope_element, 1)

        scope_btn_group.button(scope_rmap.get(
            self.config.get('filter_scope'))).setChecked(True)

        scope_btn_click = getattr(scope_btn_group, 'idClicked', None) or \
            scope_btn_group.buttonClicked[int]
        scope_btn_click.connect(
            lambda btn_id: self.config.update(
                filter_scope=scope_map.get(btn_id)))

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
              ' One pattern per line:'))

        def choose_filter_mode(btn_id):
            tip.setText(tips[btn_id])
            self.config.update(rule_mode=mode_map.get(btn_id))

        mode_btn_group.button(mode_rmap.get(
            self.config.get('rule_mode'))).setChecked(True)
        tip.setText(tips[mode_btn_group.checkedId()])

        mode_btn_click = getattr(mode_btn_group, 'idClicked', None) or \
            mode_btn_group.buttonClicked[int]
        mode_btn_click.connect(choose_filter_mode)

        # Ebook Metadata
        metadata_group = QGroupBox(_('Ebook Metadata'))
        metadata_layout = QFormLayout(metadata_group)
        self.set_form_layout_policy(metadata_layout)
        self.metadata_lang = QCheckBox(_('Set "Target Language" to metadata'))
        self.metadata_subject = QPlainTextEdit()
        self.metadata_subject.setPlaceholderText(
            _('Subjects of ebook (one subject per line)'))
        metadata_layout.addRow(_('Language'), self.metadata_lang)
        metadata_layout.addRow(_('Subject'), self.metadata_subject)
        layout.addWidget(metadata_group)

        self.metadata_lang.setChecked(
            self.config.get('ebook_metadata.language', False))
        self.metadata_subject.setPlainText(
            '\n'.join(self.config.get('ebook_metadata.subjects', [])))

        layout.addStretch(1)

        return widget

    def test_proxy_connection(self):
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if not (self.is_valid_data(self.host_validator, host) and port):
            return self.alert.pop(
                _('Proxy host or port is incorrect.'), level='warning')
        if is_proxy_availiable(host, port):
            return self.alert.pop(_('The proxy is available.'))
        return self.alert.pop(_('The proxy is not available.'), 'error')

    def is_valid_data(self, validator, value):
        state = validator.validate(value, 0)[0]
        if isinstance(state, int):
            return state == 2  # Compatible with PyQt5
        return state.value == 2

    def update_general_config(self):
        # Output path
        if not self.config.get('to_library'):
            output_path = self.output_path_entry.text()
            if not os.path.exists(output_path):
                return self.alert.pop(
                    _('The specified path does not exist.'), 'warning')
            self.config.update(output_path=output_path.strip())

        # Merge length
        self.config.update(merge_length=self.merge_length.value())

        # Proxy setting
        proxy_setting = []
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if self.config.get('proxy_enabled') or (host or port):
            if not (self.is_valid_data(self.host_validator, host) and port):
                return self.alert.pop(
                    _('Proxy host or port is incorrect.'), level='warning')
            proxy_setting.append(host)
            proxy_setting.append(int(port))
            self.config.update(proxy_setting=proxy_setting)
        len(proxy_setting) < 1 and self.config.delete('proxy_setting')

        self.config.commit()
        self.alert.pop(_('The setting has been saved.'))

    def get_engine_config(self):
        config = self.current_engine.config

        # API key
        if self.current_engine.need_api_key:
            api_keys = []
            api_key_validator = QRegularExpressionValidator(
                QRegularExpression(self.current_engine.api_key_pattern))
            key_str = re.sub('\n+', '\n', self.api_keys.toPlainText()).strip()
            for key in [key.strip() for key in key_str.split('\n')]:
                if not self.is_valid_data(api_key_validator, key):
                    self.alert.pop(
                        self.current_engine.api_key_error_message(), 'warning')
                    return None
                api_keys.append(key)
            config.update(api_keys=api_keys)
            self.set_api_keys()

        # ChatGPT prefrence
        if self.current_engine.is_chatgpt():
            prompt = self.prompt.toPlainText()
            if prompt and '<tlang>' not in prompt:
                self.alert.pop(
                    _('the prompt must include {}.').format('<slang>'),
                    'warning')
                return None
            if prompt != self.current_engine.prompt:
                config.update(prompt=prompt)
            endpoint = self.chatgpt_endpoint.text()
            if 'endpoint' in config:
                del config['endpoint']
            if endpoint and endpoint != self.current_engine.endpoint:
                config.update(endpoint=endpoint)

        # Preferred Language
        source_lang = self.source_lang.currentText()
        if 'source_lang' in config:
            del config['source_lang']
        if source_lang != _('Auto detect'):
            config.update(source_lang=source_lang)
        config.update(target_lang=self.target_lang.currentText())

        return config

    def update_engine_config(self):
        config = self.get_engine_config()
        if not config:
            return
        # Do not update directly as you may get default preferences!
        engine_config = self.config.get('engine_preferences').copy()
        engine_config.update({self.current_engine.name: config})
        # Cleanup unused engine preferences
        engine_names = [engine.name for engine in builtin_engines]
        engine_names += self.config.get('custom_engines').keys()
        for name in engine_config.copy():
            if name not in engine_names:
                engine_config.pop(name)
        # Update modified engine preferences
        self.config.update(engine_preferences=engine_config)
        self.config.commit()
        self.alert.pop(_('The setting has been saved.'))

    def update_content_config(self):
        # Translation color
        translation_color = self.translation_color.text()
        if translation_color and not QColor(translation_color).isValid():
            return self.alert.pop(_('Invalid color value.'), 'warning')
        self.config.update(translation_color=translation_color or None)

        # Glossary file
        if self.config.get('glossary_enabled'):
            glossary_path = self.glossary_path.text()
            if not os.path.exists(glossary_path):
                return self.alert.pop(
                    _('The specified glossary file does not exist.'),
                    'warning')
            self.config.update(glossary_path=glossary_path)

        # Filter rules
        rule_content = self.filter_rules.toPlainText()
        filter_rules = [r for r in rule_content.split('\n') if r]
        if self.config.get('rule_mode') == 'regex':
            for rule in filter_rules:
                if not self.is_valid_regex(rule):
                    return self.alert.pop(
                        _('{} is not a valid regular expression.')
                        .format(rule), 'warning')
        self.config.delete('filter_rules')
        filter_rules and self.config.update(filter_rules=filter_rules)

        # Element rules
        rule_content = self.element_rules.toPlainText()
        element_rules = [r for r in rule_content.split('\n') if r]
        for rule in element_rules:
            if css(rule) is None:
                return self.alert.pop(
                    _('{} is not a valid CSS seletor.')
                    .format(rule), 'warning')
        self.config.delete('element_rules')
        element_rules and self.config.update(element_rules=element_rules)

        # Ebook metadata
        ebook_metadata = self.config.get('ebook_metadata').copy()
        self.config.delete('ebook_metadata')
        if self.metadata_lang.isChecked():
            ebook_metadata.update(language=True)
        elif 'language' in ebook_metadata:
            del ebook_metadata['language']
        subject_content = self.metadata_subject.toPlainText().strip()
        if subject_content:
            subjects = [s.strip() for s in subject_content.split('\n')]
            ebook_metadata.update(subjects=subjects)
        elif 'subjects' in ebook_metadata:
            del ebook_metadata['subjects']
        if ebook_metadata:
            self.config.update(ebook_metadata=ebook_metadata)

        self.config.commit()
        self.alert.pop(_('The setting has been saved.'))

    def is_valid_regex(self, rule):
        try:
            re.compile(rule)
        except Exception:
            return False
        return True

    def disable_wheel_event(self, widget):
        widget.wheelEvent = lambda event: None

    def set_form_layout_policy(self, layout):
        field_policy = getattr(
            QFormLayout.FieldGrowthPolicy, 'AllNonFixedFieldsGrow', None) \
            or QFormLayout.AllNonFixedFieldsGrow
        layout.setFieldGrowthPolicy(field_policy)
        layout.setLabelAlignment(Qt.AlignRight)
