class ConversionFailed(Exception):
    pass


class TranslationCanceled(Exception):
    pass


class BadApiKeyFormat(TranslationCanceled):
    pass


class NoAvailableApiKey(TranslationCanceled):
    pass
