class UnexpectedResult(Exception):
    pass


class ConversionFailed(Exception):
    pass


class ConversionAbort(Exception):
    pass


class TranslationFailed(Exception):
    pass


class TranslationCanceled(Exception):
    pass


class BadApiKeyFormat(TranslationCanceled):
    pass


class NoAvailableApiKey(TranslationCanceled):
    pass


class UnsupportedModel(Exception):
    pass
