import json

from calibre_plugins.ebook_translator.engines.base import Base


load_translations()


class CustomTranslate(Base):
    raise NotImplementedError()
