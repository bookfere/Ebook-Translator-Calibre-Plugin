from calibre.customize import InterfaceActionBase

from calibre_plugins.ebook_translator.utils import _z


__license__ = 'GPL v3'
__copyright__ = '2023, bookfere.com <bookfere@gmail.com>'
__docformat__ = 'restructuredtext en'

load_translations()


class EbookTranslator(InterfaceActionBase):
    name = _z('Ebook Translator')
    title = _(name)
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'bookfere.com'
    version = (1, 2, 1)
    __version__ = 'v' + '.'.join(map(str, version))
    minimum_calibre_version = (1, 0, 0)

    actual_plugin = 'calibre_plugins.ebook_translator.ui:EbookTranslatorGui'

    def is_customizable(self):
        return False
