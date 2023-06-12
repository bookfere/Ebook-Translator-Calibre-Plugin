import os
import os.path

from calibre.constants import DEBUG
from calibre.gui2 import Dispatcher
from calibre.ptempfile import PersistentTemporaryFile
from calibre.ebooks.metadata.meta import get_metadata, set_metadata

from .config import get_config


load_translations()


class ConvertionWorker:
    def __init__(self, gui, icon):
        self.gui = gui
        self.icon = icon
        self.config = get_config()
        self.db = gui.current_db
        self.api = self.db.new_api
        self.working_jobs = self.gui.bookfere_ebook_translator.jobs

    def translate_ebook(self, ebook, cache_only=False):
        input_path = ebook.get_input_path()
        if not self.config.get('to_library'):
            output_path = os.path.join(
                self.config.get('output_path'), '%s (%s).%s' % (
                    ebook.title[:200], ebook.target_lang, ebook.output_format))
        else:
            output_path = PersistentTemporaryFile(
                suffix='.' + ebook.output_format).name

        job = self.gui.job_manager.run_job(
            Dispatcher(self.translate_done),
            'arbitrary_n',
            args=(
                'calibre_plugins.ebook_translator.convertion', 'convert_book',
                (input_path, output_path, ebook.source_lang, ebook.target_lang,
                 cache_only)),
            description=(_('[{} > {}] Translating "{}"').format(
                ebook.source_lang, ebook.target_lang, ebook.title)))
        self.working_jobs[job] = (ebook, output_path)

    def translate_done(self, job):
        if job.failed:
            self.working_jobs.clear()
            DEBUG or self.gui.job_exception(
                job, dialog_title=_('Translation job failed'))
            return

        ebook, output_path = self.working_jobs.pop(job)

        if self.config.get('to_library'):
            with open(output_path, 'rb') as file:
                metadata = get_metadata(file, ebook.output_format)
            book_id = self.db.create_book_entry(metadata)
            self.api.add_format(
                book_id, ebook.output_format, output_path, run_hooks=False)
            self.gui.library_view.model().books_added(1)
            output_path = self.api.format_abspath(book_id, ebook.output_format)
            # os.remove(temp_file)

        ebook_metadata = self.config.get('ebook_metadata')
        if ebook_metadata:
            with open(output_path, 'r+b') as file:
                metadata = get_metadata(file, ebook.output_format)
                if ebook_metadata.get('language'):
                    metadata.language = ebook.lang_code
                subjects = ebook_metadata.get('subjects')
                metadata.tags = subjects or ['Translate by Ebook Translator']
                # metadata.title = 'Custom Title'
                # metadata.authors = ['bookfere.com']
                # metadata.author_sort = 'bookfere.com'
                # metadata.book_producer = 'Ebook Translator'
                set_metadata(file, metadata, ebook.output_format)

        self.gui.status_bar.show_message(
            job.description + ' ' + _('completed'), 5000)

        self.gui.proceed_question(
            lambda payload: payload(
                'ebook-viewer',
                kwargs={'args': ['ebook-viewer', output_path]}),
            self.gui.job_manager.launch_gui_app,
            job.log_path,
            _('Ebook Translation Log'),
            _('Translation Completed'),
            _('The translation of "{}" was completed. '
              'Do you want to open the book?').format(ebook.title),
            log_is_file=True,
            icon=self.icon)
