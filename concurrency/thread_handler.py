import traceback
from threading import Thread

from ..exceptions import TranslationCanceled


try:
    import queue
except ImportError:
    import Queue as queue


class ThreadHandler:
    def __init__(self, concurrency_limit, translate_paragraph,
                 process_translation, paragraphs):
        self.queue = queue.Queue()
        for paragraph in paragraphs:
            self.queue.put_nowait(paragraph)
        self.done_queue = queue.Queue()

        self.process_translation = process_translation
        self.translate_paragraph = translate_paragraph
        self.concurrency_limit = concurrency_limit or 30

    def translation_thread(self):
        while not self.queue.empty():
            try:
                paragraph = self.queue.get()
                self.translate_paragraph(paragraph)
                self.done_queue.put(paragraph)
                self.queue.task_done()
            except TranslationCanceled:
                self.queue.task_done()
                while not self.queue.empty():
                    self.queue.get()
                    self.queue.task_done()
                break
            except Exception:
                paragraph.error = traceback.format_exc()
                self.done_queue.put(paragraph)
                self.queue.task_done()

    def processing_thread(self):
        while True:
            paragraph = self.done_queue.get()
            if paragraph is None:
                break
            self.process_translation(paragraph)
            self.done_queue.task_done()

    def create_threads(self):
        threads = []
        for _ in range(self.concurrency_limit):
            thread = Thread(target=self.translation_thread)
            thread.start()
            threads.append(thread)
        return threads

    def handle(self):
        Thread(target=self.processing_thread).start()
        for thread in self.create_threads():
            thread.join()
        self.done_queue.put(None)
