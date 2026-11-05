"""Sólo construcción: fuentes oficiales por versión y digest exactos."""
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import tarfile
import urllib.request
import subprocess


def download(url,checksum,limit):
    if not re.fullmatch('[a-f0-9]{64}',checksum):raise ValueError('Digest requerido')
    with urllib.request.urlopen(url,timeout=30) as source:data=source.read(limit+1)
    if len(data)>limit or hashlib.sha256(data).hexdigest()!=checksum:raise ValueError('Fuente alterada')
    return data


def install_application(plan):
    components=plan['manifest']['runtime']['components']
    drawio,tomcat=components['drawio'],components['tomcat']
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',drawio['version']) or not re.fullmatch(r'11\.0\.[0-9]+',tomcat['version']):raise ValueError('Versión no fijada')
    java=subprocess.check_output(['/usr/bin/java','-version'],stderr=subprocess.STDOUT,text=True)
    if ('"'+components['java']['version']+'"') not in java:raise ValueError('JRE distinto del inventario aprobado')
    war=download('https://github.com/jgraph/drawio/releases/download/v'+drawio['version']+'/draw.war',drawio['source_sha256'],256*1024**2)
    archive=download('https://archive.apache.org/dist/tomcat/tomcat-11/v'+tomcat['version']+'/bin/apache-tomcat-'+tomcat['version']+'.tar.gz',tomcat['source_sha256'],32*1024**2)
    dest=Path('/opt/nap-drawio/tomcat');dest.mkdir(parents=True,exist_ok=False)
    prefix='apache-tomcat-'+tomcat['version']
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
        members=tar.getmembers()
        if len(members)>20000 or sum(m.size for m in members)>256*1024**2:raise ValueError('Archivo excesivo')
        for m in members:
            parts=PurePosixPath(m.name).parts
            if not parts or parts[0]!=prefix or '..' in parts or not(m.isfile() or m.isdir()):raise ValueError('Miembro inválido')
        for m in members:
            m.name='/'.join(PurePosixPath(m.name).parts[1:])
            if m.name:tar.extract(m,dest,filter='data')
    import shutil
    shutil.rmtree(dest/'webapps');(dest/'webapps').mkdir()
    (dest/'webapps/ROOT.war').write_bytes(war)
    subprocess.run(['/usr/sbin/useradd','--system','--home-dir','/opt/nap-drawio','--shell','/usr/sbin/nologin','napdrawio'],check=True)
    subprocess.run(['/usr/bin/chown','-R','napdrawio:napdrawio',str(dest)],check=True)
    Path('/usr/lib/systemd/system/nap-drawio.service').write_text('[Unit]\nAfter=network.target\n[Service]\nType=simple\nUser=napdrawio\nGroup=napdrawio\nExecStart=/opt/nap-drawio/tomcat/bin/catalina.sh run\nNoNewPrivileges=true\nPrivateTmp=true\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n')
