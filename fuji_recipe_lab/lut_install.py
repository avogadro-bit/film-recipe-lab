"""Install user-supplied Fuji LUTs; no download, redistribution or fallback look."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile

from .official_luts import MANIFEST, load_lut, user_lut_directory


def install_archive(archive, destination=None):
    destination=Path(destination) if destination is not None else user_lut_directory()
    verified={}
    with ZipFile(archive) as source:
        # Read only the ten known members; never extract ZIP paths to disk.
        for film,info in MANIFEST['files'].items():
            matches=[m for m in source.infolist() if m.filename==info['original']]
            if len(matches)!=1:
                raise ValueError(f'Incompatible archive: missing or ambiguous entry for {film}')
            member=matches[0]
            if member.file_size>16*1024*1024:
                raise ValueError(f'LUT is too large: {film}')
            raw=source.read(member)
            if hashlib.sha256(raw).hexdigest()!=info['sha256']:
                raise ValueError(f'Unrecognized or modified LUT: {film}')
            verified[info['file']]=raw
    # All hashes must pass before any installed LUT is changed.
    destination.mkdir(parents=True,exist_ok=True)
    for name,raw in verified.items():
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=destination,delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(raw)
            os.replace(temporary,destination/name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    load_lut.cache_clear()
    return destination


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path,help='GFX ETERNA 55 v1.10 ZIP downloaded by you')
    args=parser.parse_args()
    try:
        location=install_archive(args.archive)
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(1,f'Installation failed: {exc}\n')
    print(f'10 LUTs verified and installed in {location}. Restart the studio if needed.')


if __name__=='__main__':
    main()
