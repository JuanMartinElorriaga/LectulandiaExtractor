from queue import Queue
from threading import Thread
import werkzeug
werkzeug.cached_property = werkzeug.utils.cached_property
from robobrowser import RoboBrowser
import re
import time
from requests import Session

class Downloader():
    def __init__(self, proxy=None, worker_num=0):
        self.worker_num = worker_num
        session         = Session()
        if proxy is not None:
            session.proxies = {'http': proxy, 'https': proxy}
        self.browser    = RoboBrowser(history=True, parser='html.parser', session=session)

    def get_download_link(self, book_url):
        self.browser.open(book_url)
        for link in self.browser.find_all("a"):
            if "download.php?t=1" in str(link):
                return f"https://www.lectulandia.cc{link['href']}"

    def download_book(self, download_url):
        self.browser.open(download_url)
        pattern = re.compile("var linkCode = \"(.*?)\";")
        section = pattern.findall(str(self.browser.parsed))
        bee_url = f'https://www.beeupload.net/file/{section[0]}'
        self.browser.open(bee_url)
        try:
            filename = self.browser.find(
                "div", id="fileDescription").find_all("p")[1].text.replace(
                    "Name: ", "")

            size = self.browser.find(
                "div", id="fileDescription").find_all("p")[2].text
            file_url = self.browser.find("a", id="downloadB")
            time.sleep(2)
            self.browser.follow_link(file_url)
            with open(f"books/{filename}", "wb") as epub_file:
                epub_file.write(self.browser.response.content)
            return filename, size
        except:
            print(self.browser.parsed)

    def get_book_page_list(self, page):
        self.browser.open(f'https://www.lectulandia.cc/book/page/{page}/')
        return [
            f"https://www.lectulandia.cc{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")
        ]

    def download_full_page(self, page):
        print(f"Downloading page: {page} ")
        books = self.get_book_page_list(page)
        for book in books:
            time.sleep(2)
            download_url = self.get_download_link(book)
            print(f"Worker: {self.worker_num} on page: {page}", self.download_book(download_url))


class Worker(Thread):
    def __init__(self, queue, worker_number, proxy=None):
        Thread.__init__(self)
        self.queue      = queue
        self.downloader = Downloader(proxy)
        self.wrk_num    = worker_number

    def run(self):
        while True:
            page = self.queue.get()
            try:
                print(f"Worker: {self.wrk_num} downloading page: {page}")
                self.downloader.download_full_page(page)
            finally:
                self.queue.task_done()


def main():
    pages   = [x + 1 for x in range(8)]
    proxies = None#[None, "https://188.168.75.254:56899"]
    queue   = Queue()
    for x in range(2):
        worker = Worker(queue, x, proxies[x])
        worker.daemon = True
        worker.start()

    for page in pages:
        queue.put(page)

    queue.join()


if __name__ == '__main__':
    main()
