from calibre.utils.localization import get_lang
from calibre_plugins.ebook_translator import EbookTranslator


try:
    from qt.core import QWidget, QHBoxLayout, QLabel
except ImportError:
    from PyQt5.Qt import QWidget, QHBoxLayout, QLabel

load_translations()


class Footer(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.status = QLabel()

        app_author = EbookTranslator.author
        github = 'https://github.com/bookfere/Ebook-Translator-Calibre-Plugin'
        if 'zh' in get_lang():
            feedback = 'https://{}/post/1057.html'.format(app_author)
            donate = 'https://{}/donate'.format(app_author)
        else:
            feedback = '{}/issues'.format(github)
            donate = 'https://www.paypal.com/paypalme/bookfere'
        link = QLabel(
            '<span style="color:crimson;">♥</span> by <a href="https://{0}">'
            '{0}</a> ｜ <a href="{1}">GitHub</a> ｜ <a href="{2}">{4}</a>'
            ' ｜ <a href="{3}">{5}</a>'.format(
                app_author, github, feedback, donate, _('Feedback'),
                _('Donate')))
        link.setStyleSheet('color:grey')
        link.setOpenExternalLinks(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addWidget(link)
