from copy import deepcopy
from tests.service_helpers import manifest


def drawio_manifest():
    value=deepcopy(manifest('linux'))
    value.update(schema_version='1.1',product='drawio',service_model='saas',definition_key='drawio-trial')
    value['runtime']['components']={'drawio':{'version':'32.6.1','source_sha256':'d'*64},
        'tomcat':{'version':'11.0.27','source_sha256':'e'*64},'java':{'version':'21.0.9'}}
    value['runtime']['packages'].append({'name':'openjdk-21-jre-headless','version':'21.0.9-1','architecture':'amd64'})
    value['preparation'].update(recipe_id='drawio-tomcat11-ubuntu-24.04-v1',bootstrap_id='drawio-v1')
    value['secret_metadata'].update(generated_fields=['access_password'],owner_reveal_fields=['access_password'],guest_only_fields=[])
    value['access'].update(kind='https',port=443)
    value['health'].update(bootstrap_probe_id='drawio-ready-v1',recurring_probe_id='drawio-status-v1')
    value['validation']['checks']+=['unique_secrets','editable_diagram_cycle','authorized_perimeter','deployment_without_provider']
    return value
