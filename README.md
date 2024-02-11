# LectulandiaExtractor
Repo para descargar libros en español programáticamente desde el dominio [Lectulandia](https://ww3.lectulandia.com/).


## Scripts
- `extractor.py`: script de descarga de archivos
    - Utiliza *Robobrowser*, que maneja *BeautifulSoup* por detrás
    - Reemplazar `library_folder` en `download_book()` con el path deseado. Se recomienda utilizar el mismo path que la *Calibre Library* en caso de existir.

Forked desde repo original [LectulandiaExtractor](https://github.com/Sarrablo/LectulandiaExtractor).


### TODO
- Si el autor posee mas de una pagina, descargarlas todas, no solamente la primera
- Agregar errores, por ejemplo cuando el autor no se encuentra en la base
- Armar log file de fallos
- Aplicar multi-thread a la descarga en batch