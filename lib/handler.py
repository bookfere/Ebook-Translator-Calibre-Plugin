import sys
import asyncio
import concurrent.futures

from .utils import log, traceback_error
from .exception import TranslationCanceled


class Handler:
    def __init__(self, paragraphs, concurrency_limit, translate_paragraph,
                 process_translation, request_interval):
        self.queue = asyncio.Queue()
        self.done_queue = asyncio.Queue()

        for paragraph in paragraphs:
            self.queue.put_nowait(paragraph)

        self.concurrency_limit = concurrency_limit or self.queue.qsize()
        self.translate_paragraph = translate_paragraph
        self.process_translation = process_translation
        self.request_interval = request_interval

    async def translation_worker(self):
        while True:
            paragraph = await self.queue.get()
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, self.translate_paragraph, paragraph)
                paragraph.error = None
                if self.queue.qsize() > 0 and not paragraph.is_cache:
                    await asyncio.sleep(self.request_interval)
                self.done_queue.put_nowait(paragraph)
                self.queue.task_done()
            except TranslationCanceled:
                await self.cancel_tasks()
                break
            except Exception:
                paragraph.error = traceback_error()
                self.done_queue.put_nowait(paragraph)
                self.queue.task_done()

    async def processing_worker(self):
        while True:
            paragraph = await self.done_queue.get()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await asyncio.get_running_loop().run_in_executor(
                    pool, self.process_translation, paragraph)
            self.done_queue.task_done()

    async def cancel_tasks(self):
        self.queue.task_done()
        while not self.queue.empty():
            await self.queue.get()
            self.queue.task_done()
        while not self.done_queue.empty():
            await self.done_queue.get()
            self.done_queue.task_done()

    async def create_tasks(self):
        tasks = []
        for _ in range(self.concurrency_limit):
            tasks.append(asyncio.create_task(self.translation_worker()))
        tasks.append(asyncio.create_task(self.processing_worker()))
        return tasks

    async def process_tasks(self):
        tasks = await self.create_tasks()
        await self.queue.join()
        await self.done_queue.join()
        # Terminate infinitive loop worker.
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    def handle(self):
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(
                asyncio.WindowsProactorEventLoopPolicy())
        try:
            loop = asyncio.get_event_loop()
        except Exception:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(self.process_tasks())
