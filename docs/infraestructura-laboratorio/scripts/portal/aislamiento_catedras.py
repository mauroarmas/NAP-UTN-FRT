"""Comprobaciones entre DOS instancias de cátedras distintas (corre en la PC; necesita pymysql).

  aislamiento_catedras.py ACCESO_A.json ACCESO_B.json

Con las credenciales reveladas a cada cátedra comprueba: cada clave abre su base y la cruzada es rechazada (error 1045),
y que cada base guarda su propia marca y no ve la de la otra. Usa la CA entregada (puede ser un conjunto de varias CA).
"""
import json
import secrets
import sys

from acceso_mariadb import conectar, contexto_tls


def intento(etiqueta, servidor, credencial, contexto):
    import pymysql
    try:
        con = conectar({**servidor, 'usuario': credencial['usuario'], 'password': credencial['password']}, contexto)
        cur = con.cursor(); cur.execute('select 1'); con.close()
        return etiqueta + ': CONECTA'
    except pymysql.err.OperationalError as error:
        return '%s: rechazado, error %s' % (etiqueta, error.args[0])


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    a, b = (json.load(open(ruta)) for ruta in argv[1:])
    contexto = contexto_tls(a)
    print(intento('A con su clave en su servidor ', a, a, contexto))
    print(intento('B con su clave en su servidor ', b, b, contexto))
    print(intento('A con la clave de B (cruzado) ', a, b, contexto))
    print(intento('B con la clave de A (cruzado) ', b, a, contexto))
    marcas = {}
    for nombre, acceso in (('A', a), ('B', b)):
        marcas[nombre] = secrets.token_hex(8)
        con = conectar(acceso, contexto); cur = con.cursor()
        cur.execute('create table if not exists nap_aislamiento (id int primary key, marca varchar(32))')
        cur.execute('replace into nap_aislamiento values (1, %s)', (marcas[nombre],)); con.commit(); con.close()
    for nombre, acceso, ajena in (('A', a, 'B'), ('B', b, 'A')):
        con = conectar(acceso, contexto); cur = con.cursor()
        cur.execute('select marca from nap_aislamiento where id=1'); propia = cur.fetchone()[0] == marcas[nombre]
        cur.execute('show databases'); bases = sorted(fila[0] for fila in cur.fetchall()); con.close()
        print('instancia %s: ve su propia marca y no la de %s = %s | bases visibles: %s' % (nombre, ajena, propia and marcas[nombre] != marcas[ajena], bases))


if __name__ == '__main__':
    main(sys.argv)
