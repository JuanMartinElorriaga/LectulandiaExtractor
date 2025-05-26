import subprocess

def add_folder_to_calibre(author_dir:str, calibre_library:str):
    """ Funcion helper para actualizar la base de calibre con el nuevo bulk descargado """
    print(f"\n Agregando a calibre los archivos descargados del autor: {author_dir}")
    try:
        subprocess.run([
            "calibredb", "add", author_dir,
            "-r",
            "--with-library", calibre_library
        ], check=True)
        print(f"✔ PROCESO FINALIZADO!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al agregar {author_dir} a calibre: {e}")
