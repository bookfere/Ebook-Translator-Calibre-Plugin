from calibre.utils.localization import get_lang
from calibre_plugins.ebook_translator import EbookTranslator


try:
    from qt.core import QWidget, QHBoxLayout, QLabel
except ImportError:
    from PyQt5.Qt import QWidget, QHBoxLayout, QLabel

load_translations()


def layout_info():
    widget = QWidget()
    widget.setStyleSheet('color:grey')
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    app_author = EbookTranslator.author
    site = QLabel(
        '<span style="color:crimson;">♥</span> by <a href="https://{0}">{0}</a>'
        .format(app_author))
    site.setOpenExternalLinks(True)
    layout.addWidget(site)
    layout.addStretch(1)
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
    layout.addWidget(link)

    return widget
