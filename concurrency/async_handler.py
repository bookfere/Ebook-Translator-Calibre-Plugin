import asyncio
import concurrent.futures

from ..exceptions import TranslationCanceled


class AsyncHandler:
    def __init__(self, concurrency_limit, translate_paragraph,
                 process_translation, paragraphs):
        self.queue = asyncio.Queue()
        for paragraph in paragraphs:
            self.queue.put_nowait(paragraph)
        self.done_queue = asyncio.Queue()

        self.concurrency_limit = concurrency_limit or self.queue.qsize()
        self.translate_paragraph = translate_paragraph
        self.process_translation = process_translation

    async def translation_worker(self):
        while True:
            try:
                paragraph = await self.queue.get()
                await asyncio.get_running_loop().run_in_executor(
                    None, self.translate_paragraph, paragraph)
                self.done_queue.put_nowait(paragraph)
                self.queue.task_done()
            except TranslationCanceled:
                self.queue.task_done()
                while not self.queue.empty():
                    await self.queue.get()
                    self.queue.task_done()
                break
            except Exception as e:
                paragraph.error = str(e)
                self.done_queue.put_nowait(paragraph)
                self.queue.task_done()

    async def processing_worker(self):
        while True:
            paragraph = await self.done_queue.get()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await asyncio.get_running_loop().run_in_executor(
                    pool, self.process_translation, paragraph)
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
        # Terminate infinitive loop worker
        for task in tasks:
            task.cancel()
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass

    def handle(self):
        asyncio.run(self.process_tasks())
