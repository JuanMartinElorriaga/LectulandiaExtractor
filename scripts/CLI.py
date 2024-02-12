import click
from extractor import Downloader

@click.command()
@click.option('--author', prompt='Enter the author name', help='Author name to download books from')
@click.option('--proxy', default=None, help='Proxy to be used for the requests')
@click.option('--output-dir', default=r'F:\Calibre Library', help='Directory to save downloaded books')
def main(author, proxy, output_dir):
    downloader = Downloader(proxy=proxy, library_folder=output_dir)

    try:
        author_url = downloader.get_author_url(author)
        click.echo(f'Author URL: {author_url}')

        urls_from_author = downloader.get_urls_from_author_url(author_url)
        click.echo(f'Total URLs found for {author}: {len(urls_from_author)}')

        download_links = downloader.get_batch_download_links(urls_from_author)
        click.echo(f'Total download links found for {author}: {len(download_links)}')

        click.confirm('Do you want to start downloading the books?', abort=True, default=True)

        downloader.batch_download_books(download_links, author)
        click.echo('Download completed successfully!')

    except Exception as e:
        click.echo(f'Error: {str(e)}')


if __name__ == '__main__':
    main()
