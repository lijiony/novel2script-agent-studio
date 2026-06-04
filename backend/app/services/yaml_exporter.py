from io import StringIO
from ruamel.yaml import YAML


def export_yaml(payload: dict) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    yaml.dump(payload, stream)
    return stream.getvalue()
