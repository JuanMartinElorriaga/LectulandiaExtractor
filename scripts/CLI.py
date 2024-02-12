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

        # Present the list of URLs to the user for selection
        selected_urls = click.prompt(
            'Select URLs to download (comma-separated, e.g., 1,2,3)',
            type         = str,
            default      = '1', # Default value can be adjusted
            show_default = True
        ).split(',')

        # Filter the URLs based on user selection
        selected_urls = [urls_from_author[int(index) - 1] for index in selected_urls]

        click.echo(f'Selected URLs: {selected_urls}')

        download_links = downloader.get_batch_download_links(selected_urls)
        click.echo(f'Total download links found for {author}: {len(download_links)}')

        if not click.confirm('Do you want to start downloading the books?', default=True):
            raise click.Abort("Download aborted by user.")

        downloader.batch_download_books(download_links, author)
        click.echo('Download completed successfully!')

    except Exception as e:
        click.echo(f'Error: {str(e)}')


if __name__ == '__main__':
    main()
