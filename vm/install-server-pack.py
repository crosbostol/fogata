#!/usr/bin/env python3
"""Import a fresh server pack into an already installed, stopped Pelican server.

Never imports a world, executes a pack script, or overwrites an existing world.
Keep the original archive and perform updates using a separate migration process.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import uuid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--server', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--heap-mib', type=int, default=5120)
    p.add_argument('--accept-minecraft-eula', action='store_true')
    args = p.parse_args()
    if not args.accept_minecraft_eula:
        p.error('Explicit Minecraft EULA acceptance required')
    sid = str(uuid.UUID(args.server))
    target = Path('/var/lib/pelican/volumes') / sid
    if not 1024 <= args.heap_mib <= 5120 or not 1024 <= args.port <= 65535:
        p.error('Heap/port outside supported limits')
    if (target / 'world').exists() or not (target / 'unix_args.txt').exists():
        p.error('Requires a fresh installed Forge server without a world')
    state = json.loads(subprocess.check_output(['docker','inspect','--format','{{json .State}}',sid]))
    if state.get('Running'):
        p.error('Stop the server first')
    with args.archive.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != args.sha256:
            p.error('Archive checksum mismatch')
    owner = target.stat()
    with tempfile.TemporaryDirectory(prefix='fogata-pack-') as staging:
        with tarfile.open(args.archive) as t:
            for member in t.getmembers():
                if member.issym() or member.islnk():
                    p.error('Links are not supported in server packs')
            t.extractall(staging, filter='data')
        source = Path(staging) / 'pack'
        if not (source / 'mods').is_dir():
            p.error('Archive must contain pack/mods')
        for name in ('mods','config','defaultconfigs','kubejs','customnpcs','tacz'):
            if (source / name).is_dir():
                if (target / name).exists():
                    p.error('Existing pack content: use a fresh server')
        for name in ('mods','config','defaultconfigs','kubejs','customnpcs','tacz'):
            if (source / name).is_dir(): shutil.copytree(source / name,target / name)
        props = source / 'default-server.properties'
        text = props.read_text() if props.exists() else ''
        text += f'\nserver-port={args.port}\nonline-mode=true\nwhite-list=true\nenforce-whitelist=true\nview-distance=6\nsimulation-distance=4\n'
        (target / 'server.properties').write_text(text)
        (target / 'user_jvm_args.txt').write_text(f'-Xms512M\n-Xmx{args.heap_mib}M\n')
        (target / 'eula.txt').write_text('eula=true\n')
        for root, dirs, files in os.walk(target):
            os.chown(root,owner.st_uid,owner.st_gid)
            for name in files: os.chown(Path(root)/name,owner.st_uid,owner.st_gid)
    print('Fresh server pack imported. Configure whitelist before starting.')


if __name__ == '__main__': main()
