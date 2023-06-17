import re


class Ebooks:
    class Ebook:
        def __init__(self, id, title, files, input_format, source_lang):
            self.id = id
            self.title = title
            self.files = files
            self.input_format = input_format
            self.source_lang = source_lang

            self.output_format = None
            self.target_lang = None
            self.lang_code = None

        def set_title(self, title):
            self.title = re.sub(r'^\.+|[\/\\\\<>:"|?*\n\t]', '', title)

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

        def get_input_path(self):
            return self.files.get(self.input_format)

    def __init__(self):
        self.ebooks = []

    def add(self, id, title, files, input_format, source_lang):
        self.ebooks.append(
            self.Ebook(id, title, files, input_format, source_lang))

    def first(self):
        return self.ebooks.pop(0)

    def clear(self):
        del self.ebooks[:]

    def __len__(self):
        return len(self.ebooks)

    def __iter__(self):
        for ebook in self.ebooks:
            yield ebook

    def __getitem__(self, index):
        return self.ebooks[index]
