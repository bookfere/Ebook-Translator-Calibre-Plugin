import time
import uuid
from types import GeneratorType

from .lang import SourceLang, TargetLang
from .alert import AlertMessage
from ..utils import sorted_mixed_keys
from ..engines.custom import get_engine_template, load_engine_data
from ..config import defaults, get_config
from ..engines import builtin_engines


try:
    from qt.core import (
        pyqtSignal, pyqtSlot, QDialog, QThread, QGridLayout, QPushButton,
        QPlainTextEdit, QObject, QTextCursor, QLabel, QComboBox, QSpacerItem)
except ImportError:
    from PyQt5.Qt import (
        pyqtSignal, pyqtSlot, QDialog, QThread, QGridLayout, QPushButton,
        QPlainTextEdit, QObject, QTextCursor, QLabel, QComboBox, QSpacerItem)

load_translations()


class EngineList(QComboBox):
    def __init__(self, default=None, parent=None):
        QComboBox.__init__(self, parent)
        self.wheelEvent = lambda event: None
        self.refresh(default)

    def refresh(self, default=None):
        self.clear()
        for engine in builtin_engines:
            self.addItem(_(engine.alias), engine.name)
        custom_engines = get_config().get('custom_engines')
        for name in sorted(custom_engines.keys(), key=sorted_mixed_keys):
            self.addItem(name, name)
        default and self.setCurrentIndex(self.findData(default))


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
        except Exception as e:
            self.clear.emit()
            self.result.emit(str(e))
            # raise e

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
        cursor.movePosition(
            getattr(QTextCursor, 'End', None) or QTextCursor.MoveOperation.End)
        source.setTextCursor(cursor)
        layout.addWidget(source, 0, 0, 1, 3)

        target = QPlainTextEdit()
        layout.addWidget(target, 1, 0, 1, 3)

        source_lang = SourceLang()
        source_lang.set_codes(self.translator.source_codes,
                              not self.translator.is_custom())
        layout.addWidget(source_lang, 2, 0)

        def change_source_lang(lang):
            self.translator.set_source_lang(lang)
        change_source_lang(source_lang.currentText())
        source_lang.currentTextChanged.connect(change_source_lang)

        target_lang = TargetLang()
        target_lang.set_codes(self.translator.target_codes,
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
        self.usage_thread.terminate()
        self.translation_thread.terminate()
        QDialog.done(self, result)


class ManageCustomEngine(QDialog):
    def __init__(self, parent):
        QDialog.__init__(self, parent)
        self.config = get_config()
        self.alert = AlertMessage(self)
        self.setWindowTitle(_('Custom Translation Engine'))
        self.setModal(True)
        self.setMinimumWidth(600)
        self.layout()
        # self.show()

    def layout(self):
        layout = QGridLayout(self)
        custom_list = QComboBox()
        custom_add = QPushButton(_('Add'))
        custom_del = QPushButton(_('Delete'))
        custom_engine_data = QPlainTextEdit()
        custom_engine_data.setMinimumHeight(400)
        custom_clear = QPushButton(_('Clear'))
        custom_reset = QPushButton(_('Reset'))
        custom_verify = QPushButton(_('Verify'))
        custom_save = QPushButton(_('Save'))
        layout.addWidget(custom_list, 0, 0, 1, 3)
        layout.addWidget(custom_add, 0, 3)
        layout.addWidget(custom_del, 0, 4)
        layout.addWidget(custom_engine_data, 1, 0, 1, 5)
        layout.addWidget(custom_clear, 2, 0)
        layout.addWidget(custom_reset, 2, 1)
        layout.addItem(QSpacerItem(0, 0), 2, 2)
        layout.addWidget(custom_verify, 2, 3)
        layout.addWidget(custom_save, 2, 4)
        layout.setColumnStretch(2, 1)

        custom_engines = self.config.get('custom_engines').copy()
        default_engine = defaults.get('translate_engine')
        current_engine = self.config.get('translate_engine')
        engine_preferences = self.config.get('engine_preferences')

        def refresh_list():
            custom_list.clear()
            for name in sorted(custom_engines.keys(), key=sorted_mixed_keys):
                custom_list.addItem(name)
        refresh_list()
        custom_list.setCurrentText(current_engine)

        def add_data():
            name = 'New Engine - %s' % uuid.uuid4().hex[:5]
            data = get_engine_template(name)
            custom_list.addItem(name)
            custom_list.setCurrentText(name)
            custom_engine_data.setPlainText(data)
            custom_engines[name] = data

        def reset_data(text=None):
            content = custom_engines.get(text or custom_list.currentText())
            custom_engine_data.setPlainText(content)
        reset_data()

        def verify_data():
            valid, data = load_engine_data(custom_engine_data.toPlainText())
            if not valid:
                return self.alert.pop(data, 'warning')
            self.alert.pop(_('Valid engine data format.'))

        def save_data():
            current_name = custom_list.currentText()
            if not current_name:
                self.config.update(
                    translate_engine=default_engine, custom_engines={})
            else:
                raw_data = custom_engine_data.toPlainText()
                valid, data = load_engine_data(raw_data)
                if not valid:
                    return self.alert.pop(data, 'warning')
                new_name = data.get('name')
                if current_name.lower() != new_name.lower():
                    exist_names = [name.lower() for name in custom_engines]
                    if new_name.lower() in exist_names:
                        return self.alert.pop(
                            _('The engine name is already in use.'), 'warning')
                del custom_engines[current_name]
                custom_engines[new_name] = raw_data
                self.config.update(custom_engines=custom_engines)
                refresh_list()
                custom_list.setCurrentText(new_name)
            self.config.commit()
            self.alert.pop(_('The setting has been saved.'))
            # self.done(0)

        def delete_data():
            if custom_list.count() < 1:
                return self.alert.pop(_('No custom engine to delete.'))
            current_index = custom_list.currentIndex()
            current_name = custom_list.itemText(current_index)
            del custom_engines[current_name]
            custom_list.removeItem(current_index)
            if current_name == current_engine:
                self.config.update(translate_engine=default_engine)
            if current_name in engine_preferences:
                del engine_preferences[current_name]

        custom_list.currentTextChanged.connect(reset_data)
        custom_add.clicked.connect(add_data)
        custom_del.clicked.connect(delete_data)
        custom_clear.clicked.connect(custom_engine_data.clear)
        custom_reset.clicked.connect(reset_data)
        custom_verify.clicked.connect(verify_data)
        custom_save.clicked.connect(save_data)
