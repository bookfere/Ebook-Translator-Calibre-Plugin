import re
import os
import os.path

from .lib.config import get_config
from .lib.utils import css, is_proxy_availiable
from .lib.translation import get_engine_class

from .engines import (
    builtin_engines, GeminiPro, ChatgptTranslate, AzureChatgptTranslate,
    ClaudeTranslate, PapagoTranslate)
from .engines.custom import CustomTranslate
from .components import (
    Footer, AlertMessage, TargetLang, SourceLang, EngineList, EngineTester,
    ManageCustomEngine, InputFormat, OutputFormat, set_shortcut)

try:
    from qt.core import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QPushButton, QPlainTextEdit,
        QTabWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QFileDialog, QColor,
        QIntValidator, QScrollArea, QRadioButton, QGridLayout, QCheckBox,
        QButtonGroup, QColorDialog, QSpinBox, QPalette, QApplication, QFrame,
        QComboBox, QRegularExpression, pyqtSignal, QFormLayout, QDoubleSpinBox,
        QSettings, QSpacerItem, QRegularExpressionValidator, QBoxLayout)
except ImportError:
    from PyQt5.Qt import (
        Qt, QLabel, QDialog, QWidget, QLineEdit, QPushButton, QPlainTextEdit,
        QTabWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QFileDialog, QColor,
        QIntValidator, QScrollArea, QRadioButton, QGridLayout, QCheckBox,
        QButtonGroup, QColorDialog, QSpinBox, QPalette, QApplication, QFrame,
        QComboBox, QRegularExpression, pyqtSignal, QFormLayout, QDoubleSpinBox,
        QSettings, QSpacerItem, QRegularExpressionValidator, QBoxLayout)

load_translations()


class TranslationSetting(QDialog):
    save_config = pyqtSignal(int)

    def __init__(self, plugin, parent, icon):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.icon = icon
        self.alert = AlertMessage(self)

        self.config = get_config()
        self.current_engine = get_engine_class()

        self.main_layout()

    def _divider(self):
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setFrameShadow(QFrame.Sunken)
        # divider.setFrameStyle(QFrame.HLine | QFrame.Sunken)
        return divider

    def main_layout(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        general_index = self.tabs.addTab(self.layout_general(), _('General'))
        engine_index = self.tabs.addTab(self.layout_engine(), _('Engine'))
        content_index = self.tabs.addTab(self.layout_content(), _('Content'))
        self.tabs.setStyleSheet('QTabBar::tab {min-width:120px;}')
        self.tabs.currentChanged.connect(lambda _: self.config.refresh())

        def save_setting(index):
            actions = {
                general_index: self.update_general_config,
                engine_index: self.update_engine_config,
                content_index: self.update_content_config,
            }
            if actions.get(index)():
                self.config.update(cache_path=get_config().get('cache_path'))
                self.config.commit()
                self.alert.pop(_('The setting has been saved.'))
        self.save_config.connect(save_setting)

        layout.addWidget(self.tabs)
        layout.addWidget(Footer())

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

            save_button = QPushButton(_('&Save'))
            layout.addWidget(save_button)

            def save_current_config():
                self.save_config.emit(self.tabs.currentIndex())
            save_button.clicked.connect(save_current_config)
            set_shortcut(
                save_button, 'save', save_current_config,save_button.text())

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
        mode_layout.addWidget(self._divider(), 1, 1, 1, 4)
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
        output_path_button = QPushButton(_('Choose'))

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
        self.proxy_host.setPlaceholderText(
            _('Host') + ' (127.0.0.1, user:pass@127.0.0.1)')
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

        misc_widget = QWidget()
        misc_layout = QHBoxLayout(misc_widget)
        misc_layout.setContentsMargins(0, 0, 0, 0)

        # Cache
        cache_group = QGroupBox(_('Cache'))
        cache_layout = QHBoxLayout(cache_group)
        cache_enabled = QCheckBox(_('Enable'))
        cache_manage = QLabel(_('Manage'))
        cache_layout.addWidget(cache_enabled)
        cache_layout.addStretch(1)
        cache_layout.addWidget(cache_manage)
        misc_layout.addWidget(cache_group, 1)

        cache_manage.setStyleSheet('color:blue;text-decoration:underline;')
        cursor = cache_manage.cursor()
        cursor.setShape(Qt.PointingHandCursor)
        cache_manage.setCursor(cursor)
        cache_manage.mouseReleaseEvent = lambda event: self.plugin.show_cache()

        cache_enabled.setChecked(self.config.get('cache_enabled'))
        cache_enabled.toggled.connect(
            lambda checked: self.config.update(cache_enabled=checked))

        # Job Log
        log_group = QGroupBox(_('Job Log'))
        log_translation = QCheckBox(_('Show translation'))
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(log_translation)
        log_layout.addStretch(1)
        misc_layout.addWidget(log_group, 1)

        # Notification
        notice_group = QGroupBox(_('Notification'))
        notice_layout = QHBoxLayout(notice_group)
        notice = QCheckBox(_('Enable'))
        notice_layout.addWidget(notice)
        misc_layout.addWidget(notice_group, 1)

        layout.addWidget(misc_widget)

        log_translation.setChecked(self.config.get('log_translation', True))
        log_translation.toggled.connect(
            lambda checked: self.config.update(log_translation=checked))

        notice.setChecked(self.config.get('show_notification', True))
        notice.toggled.connect(
            lambda checked: self.config.update(show_notification=checked))

        # Search path
        path_group = QGroupBox(_('Search Paths'))
        path_layout = QVBoxLayout(path_group)
        path_desc = QLabel(
            _('The plugin will search for external programs via these paths.'))
        self.path_list = QPlainTextEdit()
        self.path_list.setMinimumHeight(100)
        path_layout.addWidget(path_desc)
        path_layout.addWidget(self.path_list)

        self.path_list.setPlainText('\n'.join(self.config.get('search_paths')))

        layout.addWidget(path_group)

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

        # Using Tip
        self.tip_group = QGroupBox(_('Usage Tip'))
        tip_layout = QVBoxLayout(self.tip_group)
        self.using_tip = QLabel()
        self.using_tip.setTextFormat(Qt.RichText)
        self.using_tip.setWordWrap(True)
        self.using_tip.setOpenExternalLinks(True)
        tip_layout.addWidget(self.using_tip)
        layout.addWidget(self.tip_group)

        # API Keys
        self.keys_group = QGroupBox(_('API Keys'))
        keys_layout = QVBoxLayout(self.keys_group)
        self.api_keys = QPlainTextEdit()
        self.api_keys.setFixedHeight(100)
        auto_change = QLabel('%s %s' % (_('Tip: '), _(
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

        # Abort Translation
        abort_translation_group = QGroupBox(_('Abort Translation'))
        abort_translation_layout = QHBoxLayout(abort_translation_group)
        max_error_count = QSpinBox()
        max_error_count.setMinimum(0)
        abort_translation_layout.addWidget(QLabel(_('Max errors')))
        abort_translation_layout.addWidget(max_error_count)
        abort_translation_layout.addWidget(QLabel(
            _('The number of consecutive errors to abort translation.')), 1)
        layout.addWidget(abort_translation_group, 1)

        self.disable_wheel_event(max_error_count)

        self.set_form_layout_policy(request_layout)
        self.disable_wheel_event(concurrency_limit)
        self.disable_wheel_event(request_attempt)
        self.disable_wheel_event(request_interval)
        self.disable_wheel_event(request_timeout)

        # GeminiPro Setting
        gemini_group = QGroupBox(_('Tune Gemini'))
        gemini_group.setVisible(False)
        gemini_layout = QFormLayout(gemini_group)
        self.set_form_layout_policy(gemini_layout)

        self.gemini_prompt = QPlainTextEdit()
        self.gemini_prompt.setFixedHeight(80)
        gemini_layout.addRow(_('Prompt'), self.gemini_prompt)

        gemini_temperature = QDoubleSpinBox()
        gemini_temperature.setDecimals(1)
        gemini_temperature.setSingleStep(0.1)
        gemini_temperature.setRange(0, 1)

        gemini_top_p = QDoubleSpinBox()
        gemini_top_p.setDecimals(1)
        gemini_top_p.setSingleStep(0.1)
        gemini_top_p.setRange(0, 1)

        gemini_top_k = QSpinBox()
        gemini_top_k.setSingleStep(1)
        gemini_top_k.setRange(0, 40)
        # gemini_top_k.setMinimum(0)

        gemini_sampling = QWidget()
        gemini_sampling_layout = QHBoxLayout(gemini_sampling)
        gemini_sampling_layout.setContentsMargins(0, 0, 0, 0)
        gemini_sampling_layout.addWidget(QLabel('temperature'))
        gemini_sampling_layout.addWidget(gemini_temperature)
        gemini_sampling_layout.addSpacing(20)
        gemini_sampling_layout.addWidget(QLabel('topP'))
        gemini_sampling_layout.addWidget(gemini_top_p)
        gemini_sampling_layout.addSpacing(20)
        gemini_sampling_layout.addWidget(QLabel('topK'))
        gemini_sampling_layout.addWidget(gemini_top_k)
        gemini_sampling_layout.addStretch(1)

        gemini_layout.addRow(_('Sampling'), gemini_sampling)

        self.disable_wheel_event(gemini_temperature)
        self.disable_wheel_event(gemini_top_p)
        self.disable_wheel_event(gemini_top_k)

        layout.addWidget(gemini_group)

        # ChatGPT Setting
        chatgpt_group = QGroupBox()
        chatgpt_group.setVisible(False)
        chatgpt_layout = QFormLayout(chatgpt_group)
        self.set_form_layout_policy(chatgpt_layout)

        self.chatgpt_prompt = QPlainTextEdit()
        self.chatgpt_prompt.setMinimumHeight(80)
        self.chatgpt_prompt.setMaximumHeight(80)
        chatgpt_layout.addRow(_('Prompt'), self.chatgpt_prompt)
        self.chatgpt_endpoint = QLineEdit()
        chatgpt_layout.addRow(_('Endpoint'), self.chatgpt_endpoint)

        chatgpt_model = QWidget()
        chatgpt_model_layout = QHBoxLayout(chatgpt_model)
        chatgpt_model_layout.setContentsMargins(0, 0, 0, 0)
        chatgpt_model_select = QComboBox()
        chatgpt_model_custom = QLineEdit()
        chatgpt_model_layout.addWidget(chatgpt_model_select)
        chatgpt_model_layout.addWidget(chatgpt_model_custom)
        chatgpt_layout.addRow(_('Model'), chatgpt_model)

        self.disable_wheel_event(chatgpt_model_select)

        sampling_widget = QWidget()
        sampling_layout = QHBoxLayout(sampling_widget)
        sampling_layout.setContentsMargins(0, 0, 0, 0)
        temperature = QRadioButton('temperature')
        temperature_value = QDoubleSpinBox()
        temperature_value.setDecimals(1)
        temperature_value.setSingleStep(0.1)
        top_p = QRadioButton('top_p')
        top_p_value = QDoubleSpinBox()
        top_p_value.setDecimals(1)
        top_p_value.setSingleStep(0.1)
        top_p_value.setRange(0, 1)
        top_k = QLabel('top_k')
        top_k_value = QSpinBox()
        top_k_value.setSingleStep(1)
        top_k_value.setRange(1, 40)
        sampling_layout.addWidget(temperature)
        sampling_layout.addWidget(temperature_value)
        sampling_layout.addSpacing(20)
        sampling_layout.addWidget(top_p)
        sampling_layout.addWidget(top_p_value)
        sampling_layout.addSpacing(20)
        sampling_layout.addWidget(top_k)
        sampling_layout.addWidget(top_k_value)
        sampling_layout.addStretch(1)
        chatgpt_layout.addRow(_('Sampling'), sampling_widget)

        self.disable_wheel_event(temperature_value)
        self.disable_wheel_event(top_p_value)

        stream_enabled = QCheckBox(_('Enable streaming text like in ChatGPT'))
        chatgpt_layout.addRow(_('Stream'), stream_enabled)

        sampling_btn_group = QButtonGroup(sampling_widget)
        sampling_btn_group.addButton(temperature, 0)
        sampling_btn_group.addButton(top_p, 1)

        def change_sampling_method(button):
            self.current_engine.config.update(sampling=button.text())
        sampling_btn_group.buttonClicked.connect(change_sampling_method)

        layout.addWidget(chatgpt_group)

        # Papago Setting
        papago_group = QGroupBox()
        papago_group.setTitle(_('Papago Client'))
        papago_group.setVisible(False)
        papago_layout = QFormLayout(papago_group)
        self.set_form_layout_policy(papago_layout)

        self.papago_client_id = QLineEdit()
        self.papago_client_secret = QLineEdit()
        self.papago_glossary_key = QLineEdit()
        papago_layout.addRow(_('Client Id'), self.papago_client_id)
        papago_layout.addRow(_('Client Secret'), self.papago_client_secret)
        papago_layout.addRow(_('Glossary Key'), self.papago_glossary_key)

        layout.addWidget(papago_group)

        def show_gemini_preferences():
            if not issubclass(self.current_engine, GeminiPro):
                gemini_group.setVisible(False)
                return
            config = self.current_engine.config
            gemini_group.setVisible(True)
            self.gemini_prompt.setPlaceholderText(self.current_engine.prompt)
            self.gemini_prompt.setPlainText(
                config.get('prompt', self.current_engine.prompt))
            gemini_temperature.setValue(
                config.get('temperature', self.current_engine.temperature))
            gemini_temperature.valueChanged.connect(
                lambda value: config.update(temperature=round(value, 1)))
            gemini_top_p.setValue(
                config.get('top_p', self.current_engine.top_p))
            gemini_top_p.valueChanged.connect(
                lambda value: config.update(top_p=value))
            gemini_top_k.setValue(
                config.get('top_k', self.current_engine.top_k))
            gemini_top_k.valueChanged.connect(
                lambda value: config.update(top_k=value))

        def show_chatgpt_preferences():
            is_chatgpt = issubclass(self.current_engine, ChatgptTranslate)
            is_claude = issubclass(self.current_engine, ClaudeTranslate)
            if not is_chatgpt and not is_claude:
                chatgpt_group.setVisible(False)
                return
            chatgpt_group.setVisible(True)
            if is_chatgpt:
                temperature_value.setRange(0, 2)
                chatgpt_group.setTitle(_('Tune ChatGPT'))
            elif is_claude:
                temperature_value.setRange(0, 1)
                chatgpt_group.setTitle(_('Tune Claude'))
            config = self.current_engine.config
            # Prompt
            self.chatgpt_prompt.setPlaceholderText(self.current_engine.prompt)
            self.chatgpt_prompt.setPlainText(
                config.get('prompt', self.current_engine.prompt))
            # Endpoint
            self.chatgpt_endpoint.setPlaceholderText(
                self.current_engine.endpoint)
            self.chatgpt_endpoint.setText(
                config.get('endpoint', self.current_engine.endpoint))
            self.chatgpt_endpoint.setCursorPosition(0)
            # Model
            if self.current_engine.model is not None:
                chatgpt_model_select.clear()
                if issubclass(self.current_engine, AzureChatgptTranslate):
                    chatgpt_model_select.addItem(
                        _('The model depends on your Azure project.'))
                    chatgpt_model_select.setDisabled(True)
                    chatgpt_model_custom.setVisible(False)
                    return
                chatgpt_model_select.setDisabled(False)
                chatgpt_model_select.addItems(self.current_engine.models)
                chatgpt_model_select.addItem(_('Custom'))
                model = config.get('model', self.current_engine.model)
                chatgpt_model_select.setCurrentText(
                    model if model in self.current_engine.models
                    else _('Custom'))

                def setup_chatgpt_model(model):
                    if model in self.current_engine.models:
                        chatgpt_model_custom.setVisible(False)
                    else:
                        chatgpt_model_custom.setVisible(True)
                        if model != _('Custom'):
                            chatgpt_model_custom.setText(model)
                setup_chatgpt_model(model)

                def update_chatgpt_model(model):
                    if not model or _(model) == _('Custom'):
                        model = self.current_engine.models[0]
                    config.update(model=model)

                def change_chatgpt_model(model):
                    setup_chatgpt_model(model)
                    update_chatgpt_model(model)

                chatgpt_model_custom.textChanged.connect(
                    lambda model: update_chatgpt_model(model=model.strip()))
                chatgpt_model_select.currentTextChanged.connect(
                    change_chatgpt_model)
                self.save_config.connect(
                    lambda: chatgpt_model_select.setCurrentText(
                        config.get('model')))

            # Sampling
            sampling = config.get('sampling', self.current_engine.sampling)
            btn_id = self.current_engine.samplings.index(sampling)
            sampling_btn_group.button(btn_id).setChecked(True)

            temperature_value.setValue(
                config.get('temperature', self.current_engine.temperature))
            temperature_value.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    temperature=round(value, 1)))
            top_p_value.setValue(
                config.get('top_p', self.current_engine.top_p))
            top_p_value.valueChanged.connect(
                lambda value: self.current_engine.config.update(top_p=value))
            top_k.setVisible(is_claude)
            top_k_value.setVisible(is_claude)
            if is_claude:
                top_k_value.setValue(
                    config.get('top_k', self.current_engine.top_k))
                top_k_value.valueChanged.connect(
                    lambda value: self.current_engine.config
                    .update(top_k=value))
            # Stream
            stream_enabled.setChecked(
                config.get('stream', self.current_engine.stream))
            stream_enabled.toggled.connect(
                lambda checked: config.update(stream=checked))
            chatgpt_group.setVisible(True)

        def show_papago_preferences():
            is_papago = issubclass(self.current_engine, PapagoTranslate)
            if not is_papago:
                papago_group.setVisible(False)
                return
            config = self.current_engine.config
            papago_group.setVisible(True)

            self.papago_client_id.setText(
                config.get('client_id', self.current_engine.client_id))
            self.papago_client_secret.setText(
                config.get('client_secret', self.current_engine.client_secret))
            self.papago_glossary_key.setText(
                config.get('glossary_key', self.current_engine.glossary_key))

        def choose_default_engine(index):
            engine_name = engine_list.itemData(index)
            self.config.update(translate_engine=engine_name)
            self.current_engine = get_engine_class(engine_name)
            # Refresh preferred language
            source_lang = self.current_engine.config.get('source_lang')
            self.source_lang.refresh.emit(
                self.current_engine.lang_codes.get('source'), source_lang,
                not issubclass(self.current_engine, CustomTranslate))
            target_lang = self.current_engine.config.get('target_lang')
            self.target_lang.refresh.emit(
                self.current_engine.lang_codes.get('target'), target_lang)
            # show use notice
            show_tip = self.current_engine.using_tip is not None
            self.tip_group.setVisible(show_tip)
            show_tip and self.using_tip.setText(self.current_engine.using_tip)
            # show api key setting
            self.set_api_keys()
            # Request setting
            value = self.current_engine.config.get('concurrency_limit')
            if value is None:
                value = self.current_engine.concurrency_limit
            concurrency_limit.setValue(value)
            value = self.current_engine.config.get('request_interval')
            if value is None:
                value = self.current_engine.request_interval
            request_interval.setValue(float(value))
            value = self.current_engine.config.get('request_attempt')
            if value is None:
                value = self.current_engine.request_attempt
            request_attempt.setValue(value)
            value = self.current_engine.config.get('request_timeout')
            if value is None:
                value = self.current_engine.request_timeout
            request_timeout.setValue(float(value))
            value = self.current_engine.config.get('max_error_count')
            if value is None:
                value = self.current_engine.max_error_count
            max_error_count.setValue(value)
            concurrency_limit.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    concurrency_limit=value))
            request_interval.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    request_interval=round(value, 1)))
            request_attempt.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    request_attempt=value))
            request_timeout.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    request_timeout=round(value, 1)))
            max_error_count.valueChanged.connect(
                lambda value: self.current_engine.config.update(
                    max_error_count=value))
            show_gemini_preferences()
            show_chatgpt_preferences()
            show_papago_preferences()
        choose_default_engine(engine_list.findData(self.current_engine.name))
        engine_list.currentIndexChanged.connect(choose_default_engine)

        def refresh_engine_list():
            """Prevent engine list auto intercept the text changed signal."""
            engine_list.currentIndexChanged.disconnect(choose_default_engine)
            engine_list.refresh()
            index = engine_list.findData(self.config.get('translate_engine'))
            index = 0 if index == -1 else index
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
                translator.set_search_paths(self.get_search_paths())
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
            self.api_keys.setPlaceholderText(self.current_engine.api_key_hint)
            api_keys = self.current_engine.config.get('api_keys', [])
            self.api_keys.clear()
            for api_key in api_keys:
                self.api_keys.appendPlainText(api_key)

    @layout_scroll_area
    def layout_content(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Translation Position
        position_radios = QWidget()
        position_radios_layout = QVBoxLayout(position_radios)
        position_radios_layout.setContentsMargins(0, 0, 0, 0)
        below_original = QRadioButton(_('Below original'))
        below_original.setChecked(True)
        above_original = QRadioButton(_('Above original'))
        right_to_original = QRadioButton(
            '%s (%s)' % (_('Right to original'), _('Beta')))
        left_to_original = QRadioButton(
            '%s (%s)' % (_('Left to original'), _('Beta')))
        delete_original = QRadioButton(_('With no original'))
        position_radios_layout.addWidget(below_original)
        position_radios_layout.addWidget(above_original)
        position_radios_layout.addWidget(right_to_original)
        position_radios_layout.addWidget(left_to_original)
        position_radios_layout.addWidget(delete_original)
        position_radios_layout.addStretch(1)

        position_samples = QWidget()
        position_samples_layout = QVBoxLayout(position_samples)
        position_samples_layout.setContentsMargins(0, 0, 0, 0)
        position_samples_layout.setSpacing(10)
        original_sample = QLabel(_('Original'))
        original_sample.setAlignment(Qt.AlignCenter)
        original_sample.setWordWrap(True)
        original_sample.setStyleSheet(
            'border:1px solid rgba(127,127,127,.3);'
            'background-color:rgba(127,127,127,.1);padding:10px;'
            'color:rgba(0,0,0,.3);font-size:28px;')
        translation_sample = QLabel(_('Translation'))
        translation_sample.setAlignment(Qt.AlignCenter)
        translation_sample.setWordWrap(True)
        translation_sample.setStyleSheet(
            'border:1px solid rgba(127,127,127,.3);'
            'background-color:rgba(127,127,127,.1);padding:10px;'
            'color:black;font-size:28px;')
        position_samples_layout.addWidget(original_sample, 1)
        position_samples_layout.addWidget(translation_sample, 1)

        position_setup = QWidget()
        position_setup.setVisible(False)
        position_setup_layout = QHBoxLayout(position_setup)
        position_setup_layout.setContentsMargins(0, 0, 0, 0)
        column_gap_type = QComboBox()
        column_gap_value = QSpinBox()
        column_gap_value.setRange(1, 100)
        position_setup_layout.addWidget(QLabel(_('Column Gap')))
        position_setup_layout.addWidget(column_gap_type)
        position_setup_layout.addWidget(column_gap_value)
        percentage_unit = QLabel('%')
        position_setup_layout.addWidget(percentage_unit)
        position_setup_layout.addStretch(1)

        self.disable_wheel_event(column_gap_type)
        self.disable_wheel_event(column_gap_value)

        column_gap_type.addItem(_('Percentage'), 'percentage')
        column_gap_type.addItem(_('Space count'), 'space_count')

        column_gap_config = self.config.get('column_gap').copy()

        current_type = column_gap_config.get('_type')
        current_index = column_gap_type.findData(current_type)
        percentage_unit.setVisible(current_type == 'percentage')
        column_gap_type.setCurrentIndex(current_index)
        column_gap_value.setValue(column_gap_config.get(current_type))

        def change_column_gap_value(value):
            gap_type = column_gap_type.currentData()
            column_gap_config.update({gap_type: value})
            self.config.update(column_gap=column_gap_config)
        column_gap_value.valueChanged.connect(change_column_gap_value)

        def change_column_gap_type(index):
            gap_type = column_gap_type.itemData(index)
            percentage_unit.setVisible(gap_type == 'percentage')
            column_gap_value.setValue(column_gap_config.get(gap_type))
            column_gap_config.update(_type=gap_type)
            self.config.update(column_gap=column_gap_config)
        column_gap_type.currentIndexChanged.connect(change_column_gap_type)

        position_preview = QWidget()
        position_preview_layout = QVBoxLayout(position_preview)
        position_preview_layout.setSpacing(10)
        position_preview_layout.setContentsMargins(0, 0, 0, 0)
        position_preview_layout.addWidget(position_samples, 1)
        position_preview_layout.addWidget(position_setup)

        position_group = QGroupBox(_('Translation Position'))
        position_layout = QHBoxLayout(position_group)
        position_layout.addWidget(position_preview, 1)
        position_layout.addSpacing(10)
        position_layout.addWidget(position_radios)

        layout.addWidget(position_group)

        position_map = dict(enumerate(
            ['below', 'above', 'right', 'left', 'only']))
        position_rmap = dict((v, k) for k, v in position_map.items())
        # Add alias for compatibility with lower versions.
        position_rmap['after'] = 0
        position_rmap['before'] = 1
        position_btn_group = QButtonGroup(position_group)
        position_btn_group.addButton(below_original, 0)
        position_btn_group.addButton(above_original, 1)
        position_btn_group.addButton(right_to_original, 2)
        position_btn_group.addButton(left_to_original, 3)
        position_btn_group.addButton(delete_original, 4)

        map_key = self.config.get('translation_position', 'below')
        if map_key not in position_rmap.keys():
            map_key = 'below'
        position_btn_group.button(position_rmap.get(map_key)).setChecked(True)
        # Check the attribute for compatibility with PyQt5.
        position_btn_click = getattr(position_btn_group, 'idClicked', None) \
            or position_btn_group.buttonClicked[int]

        names = ('TopToBottom', 'BottomToTop', 'LeftToRight', 'RightToLeft')
        directions = []
        for name in names:
            direction = getattr(QBoxLayout, name, None)
            if direction is None:
                direction = getattr(QBoxLayout.Direction, name)
            directions.append(direction)

        def choose_option(btn_id):
            original_sample.setVisible(btn_id != 4)
            position_samples.layout().setDirection(
                directions[btn_id] if btn_id != 4 else directions[0])
            position_setup.setVisible(btn_id in [2, 3])
            self.config.update(translation_position=position_map.get(btn_id))
        choose_option(position_btn_group.checkedId())
        position_btn_click.connect(choose_option)

        # Color group
        color_group = QWidget()
        color_group_layout = QHBoxLayout(color_group)
        color_group_layout.setContentsMargins(0, 0, 0, 0)

        # Original text color
        original_color_group = QGroupBox(_('Original Text Color'))
        original_color_layout = QHBoxLayout(original_color_group)
        self.original_color = QLineEdit()
        self.original_color.setText(self.config.get('original_color'))
        self.original_color.setPlaceholderText(
            '%s %s' % (_('e.g.,'), '#0055ff'))
        original_color_show = QLabel()
        original_color_show.setObjectName('original_color_show')
        original_color_show.setFixedWidth(25)
        self.setStyleSheet(
            '#original_color{margin:1px 0;border:1 solid #eee'
            ';border-radius:2px;}')
        original_color_button = QPushButton(_('Choose'))
        original_color_layout.addWidget(original_color_show)
        original_color_layout.addWidget(self.original_color)
        original_color_layout.addWidget(original_color_button)
        color_group_layout.addWidget(original_color_group)

        # Translation Color
        translation_color_group = QGroupBox(_('Translation Text Color'))
        translation_color_layout = QHBoxLayout(translation_color_group)
        self.translation_color = QLineEdit()
        self.translation_color.setPlaceholderText(
            '%s %s' % (_('e.g.,'), '#0055ff'))
        self.translation_color.setText(self.config.get('translation_color'))
        translation_color_show = QLabel()
        translation_color_show.setObjectName('translation_color')
        translation_color_show.setFixedWidth(25)
        self.setStyleSheet(
            '#translation_color{margin:1px 0;border:1 solid #eee;'
            'border-radius:2px;}')
        translation_color_button = QPushButton(_('Choose'))
        translation_color_layout.addWidget(translation_color_show)
        translation_color_layout.addWidget(self.translation_color)
        translation_color_layout.addWidget(translation_color_button)
        color_group_layout.addWidget(translation_color_group)

        layout.addWidget(color_group)

        def show_color(color_show, color):
            valid = QColor(color).isValid()
            color_show.setStyleSheet(
                'background-color:{};border-color:{};'
                .format(valid and color or 'black',
                        valid and color or 'black'))
        show_color(original_color_show, self.original_color.text())
        show_color(translation_color_show, self.translation_color.text())

        self.original_color.textChanged.connect(
            lambda: show_color(
                original_color_show, self.original_color.text()))
        self.translation_color.textChanged.connect(
            lambda: show_color(
                translation_color_show, self.translation_color.text()))

        def create_color_picker(color_widget, color_show):
            color_picker = QColorDialog(self)
            color_picker.setOption(getattr(
                QColorDialog.ColorDialogOption, 'DontUseNativeDialog', None)
                or QColorDialog.DontUseNativeDialog)
            color_picker.colorSelected.connect(
                lambda color: color_widget.setText(color.name()))
            color_picker.colorSelected.connect(
                lambda color: show_color(color_show, color.name()))
            return color_picker

        original_color_picker = create_color_picker(
            self.original_color, original_color_show)
        original_color_button.clicked.connect(original_color_picker.open)
        translation_color_picker = create_color_picker(
            self.translation_color, translation_color_show)
        translation_color_button.clicked.connect(translation_color_picker.open)

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

        # Priority element
        priority_group = QGroupBox(_('Priority Element'))
        priority_layout = QVBoxLayout(priority_group)
        self.priority_rules = QPlainTextEdit()
        self.priority_rules.setPlaceholderText(
            '%s %s' % (_('e.g.,'), 'section, #content, div.portion'))
        self.priority_rules.setMinimumHeight(100)
        self.priority_rules.insertPlainText(
            '\n'.join(self.config.get('priority_rules')))
        priority_layout.addWidget(QLabel(
            _('CSS selectors for priority elements. One rule per line:')))
        priority_layout.addWidget(self.priority_rules)
        priority_layout.addWidget(QLabel('%s%s' % (
            _('Tip: '),
            _('Stop further extraction once elements match these rules.'))))
        layout.addWidget(priority_group)

        # Ignore element
        element_group = QGroupBox(_('Ignore Element'))
        element_layout = QVBoxLayout(element_group)
        self.ignore_rules = QPlainTextEdit()
        self.ignore_rules.setPlaceholderText(
            '%s %s' % (_('e.g.,'), 'table, table#report, table.list'))
        self.ignore_rules.setMinimumHeight(100)
        self.ignore_rules.insertPlainText(
            '\n'.join(self.config.get(
                'ignore_rules', self.config.get('element_rules'))))
        element_layout.addWidget(QLabel(
            _('CSS selectors to exclude elements. One rule per line:')))
        element_layout.addWidget(self.ignore_rules)
        element_layout.addWidget(QLabel('%s%s' % (
            _('Tip: '),
            _('Do not translate elements that matches these rules.'))))
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
        filter_layout.addWidget(self._divider())
        filter_layout.addWidget(tip)
        filter_layout.addWidget(self.filter_rules)
        filter_layout.addWidget(QLabel('%s%s' % (
            _('Tip: '), _('Do not translate extracted elements that contain '
            'these rules.'))))
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

        # Reserve element
        reserve_group = QGroupBox(_('Reserve Element'))
        reserve_layout = QVBoxLayout(reserve_group)
        self.reserve_rules = QPlainTextEdit()
        self.reserve_rules.setPlaceholderText(
            '%s %s' % (_('e.g.,'), 'span.footnote, a#footnote'))
        self.reserve_rules.setMinimumHeight(100)
        self.reserve_rules.insertPlainText(
            '\n'.join(self.config.get('reserve_rules')))
        reserve_layout.addWidget(QLabel(
            _('CSS selectors to reserve elements. One rule per line:')))
        reserve_layout.addWidget(self.reserve_rules)
        reserve_layout.addWidget(QLabel('%s%s' % (
            _('Tip: '),
            _('Keep elements that match these rules for extraction.'))))
        layout.addWidget(reserve_group)

        # Ebook Metadata
        metadata_group = QGroupBox(_('Ebook Metadata'))
        metadata_layout = QFormLayout(metadata_group)
        self.set_form_layout_policy(metadata_layout)
        self.metadata_translation = QCheckBox(
            _('Translate all of the metadata information'))
        self.metadata_lang_mark = QCheckBox(
            _('Append target language to title metadata'))
        self.metadata_lang_code = QCheckBox(
            _('Set target language code to language metadata'))
        self.metadata_subject = QPlainTextEdit()
        self.metadata_subject.setPlaceholderText(
            _('Subjects of ebook (one subject per line)'))
        metadata_layout.addRow(
            _('Metadata Translation'), self.metadata_translation)
        metadata_layout.addRow(_('Language Mark'), self.metadata_lang_mark)
        metadata_layout.addRow(_('Language Code'), self.metadata_lang_code)
        metadata_layout.addRow(_('Append Subjects'), self.metadata_subject)
        layout.addWidget(metadata_group)

        self.metadata_translation.setChecked(
            self.config.get('ebook_metadata.metadata_translation', False))
        self.metadata_lang_mark.setChecked(
            self.config.get('ebook_metadata.lang_mark', False))
        self.metadata_lang_code.setChecked(self.config.get(
            'ebook_metadata.lang_code',
            self.config.get('ebook_metadata.language', False)))  # old key
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

    def get_search_paths(self):
        path_list = self.path_list.toPlainText()
        return [p for p in path_list.split('\n') if os.path.exists(p)]

    def update_general_config(self):
        # Output path
        if not self.config.get('to_library'):
            output_path = self.output_path_entry.text()
            if not os.path.exists(output_path):
                self.alert.pop(
                    _('The specified path does not exist.'), 'warning')
                return False
            self.config.update(output_path=output_path.strip())

        # Merge length
        self.config.update(merge_length=self.merge_length.value())

        # Proxy setting
        proxy_setting = []
        host = self.proxy_host.text()
        port = self.proxy_port.text()
        if self.config.get('proxy_enabled') or (host or port):
            if not (self.is_valid_data(self.host_validator, host) and port):
                self.alert.pop(
                    _('Proxy host or port is incorrect.'), level='warning')
                return False
            proxy_setting.append(host)
            proxy_setting.append(int(port))
            self.config.update(proxy_setting=proxy_setting)
        len(proxy_setting) < 1 and self.config.delete('proxy_setting')

        # Search paths
        search_paths = self.get_search_paths()
        self.config.update(search_paths=search_paths)
        self.path_list.setPlainText('\n'.join(search_paths))

        return True

    def get_engine_config(self):
        config = self.current_engine.config
        # API key
        if self.current_engine.need_api_key:
            api_keys = []
            api_key_validator = QRegularExpressionValidator(
                QRegularExpression(self.current_engine.api_key_pattern))
            key_str = re.sub('\n+', '\n', self.api_keys.toPlainText()).strip()
            for key in [k.strip() for k in key_str.split('\n')]:
                if not self.is_valid_data(api_key_validator, key):
                    self.alert.pop(
                        self.current_engine.api_key_error_message(), 'warning')
                    return None
                api_keys.append(key)
            config.update(api_keys=api_keys)
            self.set_api_keys()

        # ChatGPT preference
        if issubclass(self.current_engine, ChatgptTranslate) or \
                issubclass(self.current_engine, ClaudeTranslate):
            self.update_prompt(self.chatgpt_prompt, config)
            endpoint = self.chatgpt_endpoint.text().strip()
            if 'endpoint' in config:
                del config['endpoint']
            if endpoint and endpoint != self.current_engine.endpoint:
                config.update(endpoint=endpoint)

        if self.current_engine == GeminiPro:
            self.update_prompt(self.gemini_prompt, config)

        # Papapo preference
        if issubclass(self.current_engine, PapagoTranslate):
            client_id = self.papago_client_id.text().strip()
            if 'client_id' in config:
                del config['client_id']
            if client_id and client_id != self.current_engine.client_id:
                config.update(client_id=client_id)

            client_secret = self.papago_client_secret.text().strip()
            if 'client_secret' in config:
                del config['client_secret']
            if client_secret and client_secret != self.current_engine.client_secret:
                config.update(client_secret=client_secret)

            glossary_key = self.papago_glossary_key.text().strip()
            if 'glossary_key' in config:
                del config['glossary_key']
            if glossary_key and glossary_key != self.current_engine.glossary_key:
                config.update(glossary_key=glossary_key)

        # Preferred Language
        source_lang = self.source_lang.currentText()
        if 'source_lang' in config:
            del config['source_lang']
        if source_lang != _('Auto detect'):
            config.update(source_lang=source_lang)
        config.update(target_lang=self.target_lang.currentText())

        return config

    def update_prompt(self, widget, config):
        prompt = widget.toPlainText().strip()
        if prompt and '<tlang>' not in prompt:
            self.alert.pop(
                _('the prompt must include {}.').format('<slang>'),
                'warning')
            return None
        if 'prompt' in config:
            del config['prompt']
        if prompt and prompt != self.current_engine.prompt:
            config.update(prompt=prompt)

    def update_engine_config(self):
        config = self.get_engine_config()
        if not config:
            return False
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
        return True

    def update_content_config(self):
        # Original text color
        original_color = self.original_color.text()
        if original_color and not QColor(original_color).isValid():
            self.alert.pop(_('Invalid color value.'), 'warning')
            return False
        self.config.update(original_color=original_color or None)

        # Translation color
        translation_color = self.translation_color.text()
        if translation_color and not QColor(translation_color).isValid():
            self.alert.pop(_('Invalid color value.'), 'warning')
            return False
        self.config.update(translation_color=translation_color or None)

        # Glossary file
        if self.config.get('glossary_enabled'):
            glossary_path = self.glossary_path.text()
            if not os.path.exists(glossary_path):
                self.alert.pop(
                    _('The specified glossary file does not exist.'),
                    'warning')
                return False
            self.config.update(glossary_path=glossary_path)

        # Priority rules
        rule_content = self.priority_rules.toPlainText()
        priority_rules = [r for r in rule_content.split('\n') if r.strip()]
        for rule in priority_rules:
            if css(rule) is None:
                self.alert.pop(
                    _('{} is not a valid CSS seletor.')
                    .format(rule), 'warning')
                return False
        self.config.delete('priority_rules')
        priority_rules and self.config.update(priority_rules=priority_rules)

        # Filter rules
        rule_content = self.filter_rules.toPlainText()
        filter_rules = [r for r in rule_content.split('\n') if r.strip()]
        if self.config.get('rule_mode') == 'regex':
            for rule in filter_rules:
                if not self.is_valid_regex(rule):
                    self.alert.pop(
                        _('{} is not a valid regular expression.')
                        .format(rule), 'warning')
                    return False
        self.config.delete('filter_rules')
        filter_rules and self.config.update(filter_rules=filter_rules)

        # Element rules
        rule_content = self.ignore_rules.toPlainText()
        ignore_rules = [r for r in rule_content.split('\n') if r.strip()]
        for rule in ignore_rules:
            if css(rule) is None:
                self.alert.pop(
                    _('{} is not a valid CSS seletor.')
                    .format(rule), 'warning')
                return False
        self.config.delete('element_rules')
        self.config.delete('ignore_rules')
        ignore_rules and self.config.update(ignore_rules=ignore_rules)

        # Reserve rules
        rule_content = self.reserve_rules.toPlainText()
        reserve_rules = [r for r in rule_content.split('\n') if r.strip()]
        for rule in reserve_rules:
            if css(rule) is None:
                self.alert.pop(
                    _('{} is not a valid CSS seletor.')
                    .format(rule), 'warning')
                return False
        self.config.delete('reserve_rules')
        reserve_rules and self.config.update(reserve_rules=reserve_rules)

        # Ebook metadata
        ebook_metadata = self.config.get('ebook_metadata').copy()
        ebook_metadata.clear()
        ebook_metadata.update(
            metadata_translation=self.metadata_translation.isChecked())
        ebook_metadata.update(lang_mark=self.metadata_lang_mark.isChecked())
        ebook_metadata.update(lang_code=self.metadata_lang_code.isChecked())
        subject_content = self.metadata_subject.toPlainText().strip()
        if subject_content:
            subjects = [s.strip() for s in subject_content.split('\n')]
            ebook_metadata.update(subjects=subjects)
        self.config.update(ebook_metadata=ebook_metadata)
        return True

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
