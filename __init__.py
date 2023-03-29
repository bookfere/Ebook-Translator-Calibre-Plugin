from calibre.customize import InterfaceActionBase


__license__ = 'GPL v3'
__copyright__ = '2023, bookfere.com <bookfere@gmail.com>'
__docformat__ = 'restructuredtext en'

load_translations()


class EbookTranslator(InterfaceActionBase):
    name = 'Ebook Translator'
    title = _(name)
    supported_platforms = ['windows', 'osx', 'linux']
    author = 'bookfere.com'
    version = (1, 0, 2)
    minimum_calibre_version = (1, 0, 0)

    actual_plugin = 'calibre_plugins.ebook_translator.ui:EbookTranslatorGui'

    @classmethod
    def get_version(cls):
        return 'v' + '.'.join(map(str, cls.version))

    def is_customizable(self):
        return False
