class TranslationFailed(Exception):
    pass


class TranslationCanceled(TranslationFailed):
    pass


class BadApiKeyFormat(TranslationCanceled):
    pass


class NoAvailableApiKey(TranslationCanceled):
    pass
