import time
import uuid
from types import GeneratorType

from qt.core import (  # type: ignore
    Qt, pyqtSignal, pyqtSlot, QDialog, QThread, QGridLayout, QPushButton,
    QPlainTextEdit, QObject, QTextCursor, QLabel, QComboBox, QSpacerItem)

from ..lib.utils import log, sorted_mixed_keys, traceback_error
from ..lib.config import get_config
from ..engines.custom import (
    create_engine_template, load_engine_data, CustomTranslate)
from ..engines import builtin_engines, GoogleFreeTranslateNew

from .lang import SourceLang, TargetLang
from .alert import AlertMessage
from .shortcut import set_shortcut


load_translations()  # type: ignore


class EngineList(QComboBox):
    def __init__(self, default=None):
        QComboBox.__init__(self)
        self.default = default
        self.wheelEvent = lambda event: None
        self.refresh()

    def layout(self):
        engines = sorted(builtin_engines, key=lambda item: not item.free)
        for engine in engines:
            previous_index = engines.index(engine) - 1
            if not engine.free and engines[previous_index].free:
                self.insertSeparator(previous_index + 1)
            self.addItem(_(engine.alias), engine.name)
        custom_engines = get_config().get('custom_engines') or {}
        if len(custom_engines) > 0:
            self.insertSeparator(len(builtin_engines) + 1)
        for name in sorted(custom_engines.keys(), key=sorted_mixed_keys):
            self.addItem(name, name)
        if self.default:
            self.setCurrentIndex(self.findData(self.default))

    def refresh(self):
        self.clear()
        self.layout()


class EngineWorker(QObject):
    clear = pyqtSignal()
    translate = pyqtSignal(str)
    result = pyqtSignal(str)
    complete = pyqtSignal()
    check = pyqtSignal()
    usage = pyqtSignal(object)

    def __init__(self, translator):
        QObject.__init__(self)
        self.translator = translator
        self.translate.connect(self.translate_text)
        self.check.connect(self.check_usage)

    @pyqtSlot(str)
    def translate_text(self, text):
        self.clear.emit()
        self.result.emit(_('Translating...'))
        try:
            translation = self.translator.translate(text)
            if isinstance(translation, GeneratorType):
                clear = True
                for text in translation:
                    if clear:
                        self.clear.emit()
                        clear = False
                    self.result.emit(text)
                    time.sleep(0.05)
            else:
                self.clear.emit()
                self.result.emit(translation)
            self.complete.emit()
        except Exception:
            self.clear.emit()
            error_message = traceback_error()
            self.result.emit(error_message)
            log.error(error_message)

    @pyqtSlot()
    def check_usage(self):
        self.usage.emit(self.translator.get_usage())


class EngineTester(QDialog):
    usage_thread = QThread()
    translation_thread = QThread()

    def __init__(self, parent, translator):
        QDialog.__init__(self, parent)
        self.parent = parent
        self.translator = translator
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(_('Test Translation Engine'))
        self.setModal(True)
        self.setMinimumWidth(500)
        # self.setMaximumHeight(300)
        self.layout()
        self.show()

    def layout(self):
        layout = QGridLayout(self)

        source = QPlainTextEdit()
        source.setPlainText('Hello World!')
        cursor = source.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        source.setTextCursor(cursor)
        layout.addWidget(source, 0, 0, 1, 3)

        target = QPlainTextEdit()
        layout.addWidget(target, 1, 0, 1, 3)

        source_lang = SourceLang()
        source_lang.set_codes(
            self.translator.lang_codes.get('source'),
            not isinstance(self.translator, CustomTranslate))
        layout.addWidget(source_lang, 2, 0)

        def change_source_lang(lang):
            self.translator.set_source_lang(lang)
        change_source_lang(source_lang.currentText())
        source_lang.currentTextChanged.connect(change_source_lang)

        target_lang = TargetLang()
        target_lang.set_codes(
            self.translator.lang_codes.get('target'),
            self.parent.target_lang.currentText())
        layout.addWidget(target_lang, 2, 1)

        def change_target_lang(lang):
            self.translator.set_target_lang(lang)
        change_target_lang(target_lang.currentText())
        target_lang.currentTextChanged.connect(change_target_lang)

        translate = QPushButton(_('Translate'))
        layout.addWidget(translate, 2, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        usage = QLabel(_('Usage: checking...'))
        usage.setVisible(False)
        layout.addWidget(usage, 3, 0, 1, 3)

        self.usage_worker = EngineWorker(self.translator)
        self.usage_worker.moveToThread(self.usage_thread)
        self.usage_thread.finished.connect(self.usage_worker.deleteLater)
        self.usage_thread.start()

        def check_usage(text):
            if text is not None:
                usage.setText(_('Usage: {}').format(text))
                usage.setVisible(True)
            else:
                usage.setVisible(False)
        self.usage_worker.usage.connect(check_usage)
        self.usage_worker.check.emit()

        self.translate_worker = EngineWorker(self.translator)
        self.translate_worker.moveToThread(self.translation_thread)
        self.translation_thread.finished.connect(
            self.translate_worker.deleteLater)
        self.translation_thread.start()

        self.translate_worker.clear.connect(target.clear)
        self.translate_worker.result.connect(target.insertPlainText)
        self.translate_worker.complete.connect(self.usage_worker.check.emit)

        def test_translate():
            self.translate_worker.translate.emit(source.toPlainText())
        translate.clicked.connect(test_translate)

    def done(self, result):
        QDialog.done(self, result)
        self.usage_thread.quit()
        self.usage_thread.wait()
        self.translation_thread.quit()
        self.translation_thread.wait()


class ManageCustomEngine(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.parent = parent
        self.config = parent.config
        self.alert = AlertMessage(self)

        self.custom_engines = self.config.get('custom_engines').copy()
        self.engine_config = self.config.get('engine_preferences').copy()
        self.default_name = self.config.get('translate_engine')

        self.setWindowTitle(_('Custom Translation Engine'))
        self.setModal(True)
        self.setMinimumWidth(600)
        self.layout()

    def layout(self):
        layout = QGridLayout(self)
        custom_list = QComboBox()
        custom_add = QPushButton(_('Add'))
        custom_del = QPushButton(_('Delete'))
        custom_engine_data = QPlainTextEdit()
        custom_engine_data.setMinimumHeight(400)
        custom_clear = QPushButton(_('Clear'))
        custom_restore = QPushButton(_('Restore'))
        custom_verify = QPushButton(_('Verify'))
        custom_save = QPushButton(_('&Save'))
        layout.addWidget(custom_list, 0, 0, 1, 3)
        layout.addWidget(custom_add, 0, 3)
        layout.addWidget(custom_del, 0, 4)
        layout.addWidget(custom_engine_data, 1, 0, 1, 5)
        layout.addWidget(custom_clear, 2, 0)
        layout.addWidget(custom_restore, 2, 1)
        layout.addItem(QSpacerItem(0, 0), 2, 2)
        layout.addWidget(custom_verify, 2, 3)
        layout.addWidget(custom_save, 2, 4)
        layout.setColumnStretch(2, 1)

        def refresh_list():
            custom_list.clear()
            engines = sorted(self.custom_engines.keys(), key=sorted_mixed_keys)
            custom_list.addItems(engines)
        refresh_list()
        index = custom_list.findText(self.default_name)
        custom_list.setCurrentIndex(index if index != -1 else 0)

        def add_data():
            name = 'New Engine - %s' % uuid.uuid4().hex[:5]
            template = create_engine_template(name)
            custom_list.addItem(name)
            custom_list.setCurrentText(name)
            custom_engine_data.setPlainText(template)
            self.custom_engines[name] = template
        if len(self.custom_engines) < 1:
            add_data()

        def restore_data(name=None):
            name = name or custom_list.currentText()
            content = self.custom_engines.get(name)
            custom_engine_data.setPlainText(content)
        restore_data()

        def verify_data():
            valid, data = load_engine_data(custom_engine_data.toPlainText())
            if not valid:
                return self.alert.pop(data, 'warning')
            self.alert.pop(_('Valid engine data format.'))

        def save_data():
            current_name = custom_list.currentText()
            if not current_name:  # If all engine was deleted
                self.default_name = GoogleFreeTranslateNew.name
            else:
                # Validate the custom engine data
                raw_data = custom_engine_data.toPlainText()
                valid, data = load_engine_data(raw_data)
                if not valid:
                    return self.alert.pop(data, 'warning')
                # Check if the engine name exists
                new_name = data.get('name') or ''
                if new_name.lower() != current_name.lower():
                    exist_names = [
                        name.lower() for name in self.custom_engines]
                    if new_name.lower() in exist_names:
                        return self.alert.pop(
                            _('The engine name is already in use.'), 'warning')
                # Refresh custom engine data
                default_name = get_config().get('translate_engine')
                if self.default_name == current_name:
                    self.default_name = new_name
                    if current_name in self.engine_config:
                        data = self.engine_config.pop(current_name)
                        self.engine_config[new_name] = data
                if default_name == current_name:
                    default_name = new_name
                self.config.update(translate_engine=default_name)
                del self.custom_engines[current_name]
                self.custom_engines[new_name] = raw_data
                # Refresh the custom engine list
                refresh_list()
                custom_list.setCurrentText(new_name)
            # Update the custom engine
            self.config.update(custom_engines=self.custom_engines.copy())
            self.config.update(engine_preferences=self.engine_config.copy())
            self.config.commit()
            # Restore the selected engine
            self.config.update(translate_engine=self.default_name)
            self.alert.pop(_('The setting has been saved.'))

        def delete_data():
            current_index = custom_list.currentIndex()
            current_name = custom_list.itemText(current_index)
            if current_name in self.custom_engines:
                del self.custom_engines[current_name]
            if current_name in self.engine_config:
                del self.engine_config[current_name]
            if current_name == self.default_name:
                self.default_name = GoogleFreeTranslateNew.name
            custom_list.removeItem(current_index)

        def disable_save_button():
            disabled = custom_list.count() < 1
            custom_del.setDisabled(disabled)
            custom_clear.setDisabled(disabled)
            custom_restore.setDisabled(disabled)
            custom_verify.setDisabled(disabled)
        disable_save_button()

        custom_list.currentTextChanged.connect(disable_save_button)
        custom_list.currentTextChanged.connect(restore_data)
        custom_add.clicked.connect(add_data)
        custom_del.clicked.connect(delete_data)
        custom_clear.clicked.connect(custom_engine_data.clear)
        custom_restore.clicked.connect(restore_data)
        custom_verify.clicked.connect(verify_data)
        custom_save.clicked.connect(save_data)
        set_shortcut(custom_save, 'save', save_data, custom_save.text())

    def done(self, result):
        QDialog.done(self, result)
        self.parent.raise_()
        self.parent.activateWindow()
