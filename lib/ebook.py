from typing import Iterator, Iterable


class Ebook:
    def __init__(self, id, title, files, input_format, source_lang,
                 extra_formats=[]):
        self.id = id
        self.files = files
        self.input_format = input_format
        self.source_lang = source_lang
        self.extra_formats = extra_formats

        self.output_format = None
        self.target_lang = None
        self.lang_code = None

        self.title = title
        self.custom_title = None
        self.encoding = 'utf-8'
        self.target_direction = 'auto'

    def set_input_format(self, format):
        self.input_format = format

    def set_output_format(self, format):
        self.output_format = format

    def set_source_lang(self, lang):
        self.source_lang = lang

    def set_target_lang(self, lang):
        self.target_lang = lang

    def set_lang_code(self, code):
        self.lang_code = code

    def set_custom_title(self, title):
        self.custom_title = title

    def set_encoding(self, encoding):
        self.encoding = encoding

    def set_target_direction(self, direction):
        self.target_direction = direction

    def get_input_path(self):
        return self.files.get(self.input_format)

    def is_extra_format(self):
        return self.input_format in self.extra_formats


class Ebooks(Iterable):

    def __init__(self):
        self.ebooks: list[Ebook] = []

    def add(self, *args):
        self.ebooks.append(Ebook(*args))

    def first(self) -> Ebook:
        return self.ebooks.pop(0)

    def clear(self):
        del self.ebooks[:]

    def __len__(self):
        return len(self.ebooks)

    def __iter__(self) -> Iterator[Ebook]:
        for ebook in self.ebooks:
            yield ebook

    def __getitem__(self, index) -> Ebook:
        return self.ebooks[index]
