import click
from urllib.parse import urlparse, unquote

from extractor import Downloader

@click.command()
@click.option('--author', prompt='Nombre de autor', help='Nombre de autor desde el cual descargar libros')
@click.option('--proxy', default=None, help='Proxy para los requests')
@click.option('--output-dir', default=r'F:\Calibre Library', help='Directorio local en donde descargar los libros')
def main(author, proxy, output_dir):
    downloader = Downloader(proxy=proxy, library_folder=output_dir)

    try:
        author_url = downloader.get_author_url(author)
        click.echo(f'URL del autor: {author_url}')

        urls_from_author = downloader.get_urls_from_author_url(author_url)
        click.echo(f'Total de links encontrados para {author.title()}: {len(urls_from_author)}')

        # Display the list of URLs to the user
        click.echo('\nLista de libros:')

        for i, url in enumerate(urls_from_author, start=1):
            book = unquote(urlparse(url).path.strip('/').split('/')[-1]).replace('-', ' ')
            click.echo(f"{i}. {book}")

        # Prompt the user to select URLs for download
        selected_indices = click.prompt(
            'Seleccionar libro(s) para descargar (ej., 1,2,3, o ALL para todos)',
            type         = str,
            default      = 'ALL',
            show_default = True
        )

        # Filter the URLs based on user selection
        if selected_indices.upper() == 'ALL':
            selected_urls = urls_from_author
        else:
            selected_indices = selected_indices.split(',')
            selected_urls    = [urls_from_author[int(index) - 1] for index in selected_indices]

        #click.echo(f'Libros seleccionados: {selected_urls}')
        download_links = downloader.get_batch_download_links(selected_urls)
        click.echo(f'Total de libros encontrados para {author}: {len(download_links)}')

        if not click.confirm('Quieres comenzar con la descarga?', default=True):
            raise click.Abort("Descarga abortada por el usuario.")

        downloader.batch_download_books(download_links, author)
        click.echo('Descarga finalizada!')

    except Exception as e:
        click.echo(f'Error: {str(e)}')


if __name__ == '__main__':
    main()
