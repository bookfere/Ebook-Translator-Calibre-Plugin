import re
import zipfile

from calibre.library.comments import markdown
from calibre.utils.localization import get_lang

from . import EbookTranslator
from .components import layout_info


try:
    from qt.core import (
        Qt, QLabel, QDialog, QWidget, QVBoxLayout, QTextBrowser, QTextDocument)
except ImportError:
    from PyQt5.Qt import (
        Qt, QLabel, QDialog, QWidget, QVBoxLayout, QTextBrowser, QTextDocument)

load_translations()


class AboutDialog(QDialog):
    def __init__(self, plugin, parent, icon):
        QDialog.__init__(self, parent)
        self.plugin = plugin
        self.gui = parent
        self.icon = icon

        layout = QVBoxLayout(self)

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

        layout.addWidget(brand, 1)
        layout.addWidget(description, 2)
        layout.addWidget(layout_info())

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
