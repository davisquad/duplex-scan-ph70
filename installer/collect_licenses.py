"""Preserve installed package license/notice files in the app distribution."""
from pathlib import Path
import importlib.metadata as metadata
import shutil
import sys

target = Path('dist/Duplex Scan/THIRD-PARTY-LICENSES')
target.mkdir(parents=True,exist_ok=True)
rows = []
for dist in metadata.distributions():
    name = dist.metadata['Name']
    rows.append(f'{name} {dist.version}')
    for file in dist.files or []:
        relative = Path(str(file))
        if '..' in relative.parts: continue
        if not any(word in relative.name.lower() for word in ('license','copying','notice')) and 'licenses' not in relative.parts:
            continue
        source = Path(dist.locate_file(file))
        if source.is_file():
            destination = target/name/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination)
python_license = Path(sys.base_prefix)/'LICENSE.txt'
if python_license.exists(): shutil.copy2(python_license,target/'Python-LICENSE.txt')
(target/'PACKAGES.txt').write_text('\n'.join(sorted(rows))+'\n',encoding='utf-8')
