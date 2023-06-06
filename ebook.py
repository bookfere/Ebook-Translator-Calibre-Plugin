class Ebooks:
    class Ebook:
        def __init__(self, id, title, files, input_format, output_format,
                     source_lang, target_lang):
            self.id = id
            self.title = title
            self.files = files
            self.input_format = input_format
            self.output_format = output_format
            self.source_lang = source_lang
            self.target_lang = target_lang

        def set_source_lang(self, lang):
            self.source_lang = lang

        def set_target_lang(self, lang):
            self.target_lang = lang

        def get_input_path(self):
            return self.files.get(self.input_format)

        def set_title(self, title):
            self.title = title

    def __init__(self):
        self.ebooks = []

    def add(self, id, title, files, input_format, output_format,
            source_lang, target_lang):
        self.ebooks.append(self.Ebook(
            id, title, files, input_format, output_format, source_lang,
            target_lang))

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
