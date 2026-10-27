"""Build the published Rate4Site source locally, without modifying its code."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

SOURCE_URL='https://www.tau.ac.il/~itaymay/cp/rate4site.3.2.source.zip'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',help='Use a previously downloaded source ZIP')
    parser.add_argument('--data-dir',default=str(Path(__file__).parent/'data'))
    args=parser.parse_args()
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        raise SystemExit('A C++ compiler is required (Apple command-line tools on macOS).')
    if args.archive:
        archive=Path(args.archive).read_bytes()
    else:
        print('Downloading the official Rate4Site source…',flush=True)
        with urlopen(SOURCE_URL,timeout=60) as response:
            archive=response.read()
    digest=hashlib.sha256(archive).hexdigest()
    destination=Path(args.data_dir).expanduser().resolve()/'tools'
    destination.mkdir(parents=True,exist_ok=True)
    flags='-O2 -std=c++03 -Wno-deprecated -DDOUBLEREP'
    with tempfile.TemporaryDirectory(prefix='molecule-rate4site-') as temp:
        directory=Path(temp)
        with ZipFile(io.BytesIO(archive)) as source:
            for entry in source.infolist():
                if not (directory/entry.filename).resolve().is_relative_to(directory):
                    raise ValueError('Unsafe path in the source archive.')
            source.extractall(directory)
        project=next(directory.glob('*/sourceMar09'))
        print('Building the extended-range arithmetic version…',flush=True)
        subprocess.run(['make','-f','Makefile_slow','-j4','CXX='+compiler,'CXXFLAGS='+flags],cwd=project,check=True)
        shutil.copy2(project/'rate4site',destination/'rate4site')
    (destination/'rate4site').chmod(0o755)
    (destination/'rate4site-build.json').write_text(json.dumps(dict(source_url=SOURCE_URL,
        source_sha256=digest,compiler=compiler,flags=flags),indent=2)+'\n')
    print('Installed '+str(destination/'rate4site'))


if __name__=='__main__':
    main()
