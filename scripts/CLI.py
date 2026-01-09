import click
from urllib.parse import urlparse, unquote
from extractor import Downloader
import os

from calibre_utils import add_folder_to_calibre
from config.settings import settings
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

console = Console()

@click.command()
@click.option('--author', prompt='Nombre de autor', help='Nombre de autor desde el cual descargar libros')
@click.option('--download_folder', prompt='Path de descarga', default=settings.DEFAULT_DOWNLOAD_FOLDER, help='Directorio local en donde descargar los libros')
@click.option('--calibre_library', prompt='Path de base Calibre', default=settings.DEFAULT_CALIBRE_LIBRARY, help='Directorio de la libreria Calibre')
@click.option('--proxy', default=None, help='Proxy para los requests')
@click.option('--dry-run', is_flag=True, help='Simular descarga sin descargar archivos (preview)')
def main(author, proxy, download_folder, calibre_library, dry_run):
    downloader = Downloader(proxy, download_folder, calibre_library)

    try:
        author_url = downloader.get_author_url(author)
        click.echo(f'URL del autor: {author_url}')

        urls_from_author = downloader.get_urls_from_author_url(author_url)
        click.echo(f'Total de links encontrados para {author.title()}: {len(urls_from_author)}')

        # Display the list of URLs to the user
        click.echo(click.style('\nLista de libros:', fg='cyan'))

        for i, url in enumerate(urls_from_author, start=1):
            book = unquote(urlparse(url).path.strip('/').split('/')[-1]).replace('-', ' ')
            click.echo(f"{click.style(i, fg='yellow')}. {click.style(book, fg='yellow')}")


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

        download_links, failed_links = downloader.get_batch_download_links(selected_urls)
        console.print(f'\n[cyan]Total de libros a descargar de {author.title()}: {len(download_links)}[/cyan]')
        if failed_links:
            console.print(f'[yellow]⚠ {len(failed_links)} libro(s) no pudieron obtener link de descarga[/yellow]')

        # Dry-run mode: just preview
        if dry_run:
            console.print("\n[yellow]MODO DRY-RUN: Vista previa sin descargar archivos[/yellow]")
            for i, link in enumerate(download_links, 1):
                console.print(f"  {i}. {link}")
            console.print(f"\n[yellow]Se descargarían {len(download_links)} libros[/yellow]")
            return

        if not click.confirm('Quieres comenzar con la descarga?', default=True):
            raise click.Abort("❌ Descarga abortada por el usuario.")

        # Download with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Descargando libros de {author.title()}...",
                total=len(download_links)
            )

            results = downloader.batch_download_books(download_links, author)

            # Update progress for each download
            for _ in download_links:
                progress.update(task, advance=1)

        # Combine all failures (link fetch + download)
        all_failures = failed_links + results['fallidos']

        # Show summary table
        table = Table(title=f"\nResumen de Descarga - {author.title()}")
        table.add_column("Estado", style="bold")
        table.add_column("Cantidad", justify="right")

        table.add_row("✓ Exitosos", f"[green]{len(results['exitosos'])}[/green]")
        table.add_row("⊘ Omitidos (duplicados)", f"[yellow]{len(results['omitidos'])}[/yellow]")
        table.add_row("✗ Fallidos", f"[red]{len(all_failures)}[/red]")

        console.print(table)

        # Show failed books if any
        if all_failures:
            console.print("\n[red]Libros fallidos:[/red]")
            for item in all_failures:
                console.print(f"  • {item['url']}")
                console.print(f"    Error: {item['error']}")

        console.print(click.style('\n✔ Proceso finalizado!', fg='green'))

        # Agregar a Calibre (calibre.exe debe estar apagado)
        if click.confirm('Quieres actualizar la base de datos Calibre?', default=True):
            author_folder = os.path.join(download_folder, author)
            add_folder_to_calibre(author_folder, calibre_library)

    except Exception as e:
        click.echo(click.style(f'Error: {str(e)}', fg='red'))


if __name__ == '__main__':
    main()
