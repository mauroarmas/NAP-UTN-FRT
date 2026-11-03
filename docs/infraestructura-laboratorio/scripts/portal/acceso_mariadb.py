"""Cliente de comprobación de una instancia MariaDB con el acceso revelado (corre en la PC; necesita pymysql).

  acceso_mariadb.py escribir ACCESO.json MARCA.txt   escribe una fila con una marca aleatoria y guarda la marca
  acceso_mariadb.py leer     ACCESO.json MARCA.txt   comprueba que la fila se recupera (p. ej. tras detener/iniciar)

Verifica la CA entregada y la identidad del servidor (TLS obligatorio). No imprime la contraseña.
"""
import json
import os
import secrets
import ssl
import sys
import tempfile


def contexto_tls(acceso):
    archivo = tempfile.NamedTemporaryFile('w', suffix='.crt', delete=False)
    archivo.write(acceso['ca']); archivo.close()
    try:
        contexto = ssl.create_default_context(cafile=archivo.name)
    finally:
        os.unlink(archivo.name)
    contexto.check_hostname = True; contexto.verify_mode = ssl.CERT_REQUIRED
    return contexto


def conectar(acceso, contexto):
    import pymysql
    return pymysql.connect(host=acceso['host'], port=int(acceso['puerto']), user=acceso['usuario'], password=acceso['password'],
                           database=acceso['base'], ssl=contexto, connect_timeout=8)


def main(argv):
    if len(argv) != 4 or argv[1] not in ('escribir', 'leer'):
        sys.exit(__doc__)
    modo, ruta_acceso, ruta_marca = argv[1:]
    acceso = json.load(open(ruta_acceso))
    con = conectar(acceso, contexto_tls(acceso)); cur = con.cursor()
    cur.execute("select 1, (select variable_value from information_schema.session_status where variable_name='Ssl_version')")
    print('conexión', cur.fetchone())
    if modo == 'escribir':
        marca = secrets.token_hex(12)
        cur.execute("create table if not exists nap_portal (id int primary key, marca varchar(64))")
        cur.execute("replace into nap_portal values (1, %s)", (marca,)); con.commit()
        descriptor = os.open(ruta_marca, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as destino:
            destino.write(marca)
        print('escrito')
    else:
        cur.execute("select marca from nap_portal where id=1"); fila = cur.fetchone()
        print('recuperado coincide:', fila is not None and fila[0] == open(ruta_marca).read())
    con.close()


if __name__ == '__main__':
    main(sys.argv)
