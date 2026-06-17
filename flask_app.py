"""
WSGI entrypoint para PythonAnywhere.

En el panel Web de PythonAnywhere, editar el archivo WSGI y dejarlo así:

    import sys
    path = "/home/TU_USUARIO/tickets-platform"
    if path not in sys.path:
        sys.path.insert(0, path)

    from flask_app import app as application

Donde "TU_USUARIO" es tu usuario de PythonAnywhere y la carpeta es donde
clonaste el repo.
"""

from checkin_app import app

# PythonAnywhere busca la variable `application` por defecto, pero también
# acepta `app`. Exponemos ambas por las dudas.
application = app
