class Downloader():
    def __init__(self, proxy=None, worker_num=0):
        self.worker_num = worker_num
        session         = Session()
        if proxy is not None:
            session.proxies = {'http': proxy, 'https': proxy}
        self.browser = RoboBrowser(history=True, parser='html.parser', session=session)

    def get_author_url(self, author):
        ''' Get author url from input given '''
        author_name = author.replace(" ", "-").lower()
        author_url  = f'https://ww3.lectulandia.com/autor/{author_name}'
        return author_url

    def get_books_titles_from_author_url(self, author_url):
        self.browser.open(author_url)
        books_titles_from_author = [
            f"{book['title']}"
            for book in self.browser.find_all("a", class_="title")]
        print(f'Number of titles retrieved: {len(books_titles_from_author)}')
        return books_titles_from_author

    def get_urls_from_author_url(self, author_url):
        self.browser.open(author_url)
        urls_from_author = [
            f"https://ww3.lectulandia.com{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")]
        return urls_from_author


    def get_download_link(self, book_url):
        self.browser.open(book_url)
        for link in self.browser.find_all("a"):
            if "download.php?t=1" in str(link):
                return f"https://www.lectulandia.com{link['href']}"


    def get_batch_download_links(self, urls_from_author):
        download_links = [self.get_download_link(book_url) for book_url in urls_from_author]
        return download_links


    def download_book(self, download_url):
        self.browser.open(download_url)
        pattern = re.compile("var linkCode = \"(.*?)\";")
        section = pattern.findall(str(self.browser.parsed))
        ant_url = f'https://www.antupload.com/file/{section[0]}'
        print(ant_url)
        self.browser.open(ant_url)
        print('opened')
        try:
            filename = self.browser.find(
                "div", id="fileDescription").find_all("p")[1].text.replace(
                    "Name: ", "")
            print(filename)

            size = self.browser.find(
                "div", id="fileDescription").find_all("p")[2].text
            file_url = self.browser.find("a", id="downloadB")
            print(size)
            time.sleep(2)
            self.browser.follow_link(file_url)
            with open(f"books/{filename}", "wb") as epub_file:
                epub_file.write(self.browser.response.content)
            return filename, size
        except:
            print(self.browser.parsed)


    def get_book_page_list(self, page:int):
        self.browser.open(f'https://ww3.lectulandia.com/book/page/{page}/')
        return [
            f"https://www.lectulandia.cc{book['href']}"
            for book in self.browser.find_all("a", class_="card-click-target")
        ]

    def download_full_page(self, page:int):
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
