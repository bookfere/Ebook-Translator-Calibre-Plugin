from qt.core import (  # type: ignore
    pyqtSignal, QDialog, QPushButton, QPlainTextEdit, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, Qt)

from ..lib.config import get_config


load_translations()  # type: ignore


class ModeSelection(QDialog):
    choose_action = pyqtSignal()

    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.layout_main()

    def layout_main(self):
        layout = QHBoxLayout(self)

        choose_group = QGroupBox(
            _('Choose a translation mode for clicking the icon button.'))
        choose_group.setAlignment(Qt.AlignCenter)
        choose_layout = QGridLayout(choose_group)
        choose_group.setStyleSheet('QLabel {font-size:20px}')

        advanced_label = QLabel(_('Advanced Mode'))
        advanced_label.setAlignment(Qt.AlignCenter)

        advanced_description = QPlainTextEdit()
        advanced_description.setPlainText(_(
            'This mode provides additional options for the translation '
            'process, allowing for more control and customization.'))
        advanced_description.setReadOnly(True)
        advanced_button = QPushButton(_('Choose'))

        batch_label = QLabel(_('Batch Mode'))
        batch_label.setAlignment(Qt.AlignCenter)

        batch_description = QPlainTextEdit()
        batch_description.setPlainText(_(
            'This mode allows users to translate multiple ebooks at once, '
            'streamlining the translation process and saving time.'))
        batch_description.setReadOnly(True)
        batch_button = QPushButton(_('Choose'))

        novel_label = QLabel(_('Novel Mode'))
        novel_label.setAlignment(Qt.AlignCenter)

        novel_description = QPlainTextEdit()
        novel_description.setPlainText(_(
            'Chapter-aware translation for novels with LLMs (ChatGPT, '
            'Claude, Gemini, Ollama). Maintains a running summary and a '
            'dynamic glossary of characters and places for consistent, '
            'context-aware translation across the whole book.'))
        novel_description.setReadOnly(True)
        novel_button = QPushButton(_('Choose'))

        choose_layout.addWidget(advanced_label, 0, 0)
        choose_layout.addWidget(advanced_description, 1, 0)
        choose_layout.addWidget(advanced_button, 2, 0)
        choose_layout.addWidget(batch_label, 0, 1)
        choose_layout.addWidget(batch_description, 1, 1)
        choose_layout.addWidget(batch_button, 2, 1)
        choose_layout.addWidget(novel_label, 0, 2)
        choose_layout.addWidget(novel_description, 1, 2)
        choose_layout.addWidget(novel_button, 2, 2)

        advanced_button.clicked.connect(
            lambda: self.save_preferred_mode('advanced'))
        batch_button.clicked.connect(
            lambda: self.save_preferred_mode('batch'))
        novel_button.clicked.connect(
            lambda: self.save_preferred_mode('novel'))

        layout.addWidget(choose_group)

    def save_preferred_mode(self, mode):
        get_config().set('preferred_mode', mode)
        self.done(0)
        self.choose_action.emit()
