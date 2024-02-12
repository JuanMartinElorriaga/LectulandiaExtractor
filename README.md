# LectulandiaExtractor
Repo para descargar libros en español programáticamente desde el dominio [Lectulandia](https://ww3.lectulandia.com/).


## Descripción
El programa actualmente permite, a partir de un autor dado, descargar la totalidad de libros *epub* presentes en [Lectulandia](https://ww3.lectulandia.com/). También es posible descargar la totalidad de libros presentes en una página (page) en particular.
El código se trata de un scrapper basado en *Robobrowser*, el cual maneja *BeautifulSoup* por detrás para navegar y seleccionar el contenido de la página web.

La función de descarga posee además un paginador, de forma tal que no solo se descargue la primera página visible en la interfaz, sino la totalidad de páginas.

Forked desde repo original [LectulandiaExtractor](https://github.com/Sarrablo/LectulandiaExtractor).

## Scripts
- `extractor.py`: script de descarga de archivos
    - Reemplazar `library_folder` en `download_book()` con el path deseado. Se recomienda utilizar el mismo path que la *Calibre Library* en caso de existir.


### TODO
- Armar log file de fallos
- Aplicar multi-thread a la descarga en batch
- Agregar funcionalidad para descargar un único libro, en lugar de toda la colección del autor
- Mejorar el sistema de búsqueda de autor para los casos de match parcial.
- Armar una GUI con Tkinter, PyQt o Kivy.