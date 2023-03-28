from calibre_plugins.ebook_translator.engines.deepl import DeeplTranslate


load_translations()


class DeeplProTranslate(DeeplTranslate):
    def get_endpoint(self):
        return 'https://api.deepl.com/v2/translate'
