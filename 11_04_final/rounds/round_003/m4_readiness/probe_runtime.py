import importlib.metadata as metadata
import json
import sys

packages = {}
for name in ['torch', 'tabicl', 'numpy', 'scikit-learn']:
    try:
        packages[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        packages[name] = None
print(json.dumps({'python': sys.executable, 'version': sys.version, 'packages': packages}))
