from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate


load_translations()


class DeeplProTranslate(DeeplTranslate):
    name = 'DeepL(Pro)'
    endpoint = 'https://api.deepl.com/v2/translate'
