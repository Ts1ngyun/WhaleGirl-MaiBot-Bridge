"""Restore one installer backup; refuse to overwrite files changed after install."""
from pathlib import Path
import argparse, hashlib, json, shutil

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('backup');p.add_argument('--apply',action='store_true');args=p.parse_args()
    root=Path(__file__).resolve().parent
    backup=Path(args.backup).resolve()
    if not backup.is_relative_to((root/'backups').resolve()):raise ValueError('Select a backup inside this installation')
    records=json.loads((backup/'restore.json').read_text(encoding='utf-8'))
    for row in records:
        path=Path(row['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['installed_sha256']:
            raise ValueError('File changed after installation; manual merge required: '+str(path))
    for row in reversed(records):
        path=Path(row['path']);print('Restore:',path)
        if args.apply:
            if row['backup'] is not None:shutil.copy2(backup/row['backup'],path)
            else:path.unlink()
    print('Done.' if args.apply else 'Preview only. Stop both programs before using --apply.')

if __name__=='__main__':main()
