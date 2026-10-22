"""Export current source into two fresh repositories without local Git history."""
import argparse
import fnmatch
import json
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    '.git', '.stock-private', '.local', '.code-review-graph', '__pycache__',
    'node_modules', 'dist', 'data', 'datasets', 'runs', 'artifacts', 'coverage',
    '.pytest_cache', '.mypy_cache', '.ruff_cache', '.cache', 'secrets', 'credentials',
    'playwright-report', 'test-results', 'backups', 'logs',
}
SKIP_FILES = (
    '*.token', '*.key', '*.pem', '*.p12', '*.pfx', '*.log', '*.pid', '*.db', '*.db-*',
    '*.sqlite*', '*.pyc', '*.pyo', '*.tsbuildinfo', '*.local.json', '*.bak', '*.tmp',
    '*.pt', '*.pth', '*.onnx', '*.safetensors', '*.pkl', '*.pickle', '*.zip',
    '*.tar', '*.gz', '*.7z', '*.exe', '*.dll', '*.pdf', '*.csv', '*.parquet',
    '*.xlsx', '*.xls', '*.npy', '*.npz', '*.joblib', '*.bin', '*.orig',
    'initial-login.txt', 'config.json',
)


def copy_source(source, target, skip_core=False):
    if target.exists():
        raise SystemExit('Destination already exists; use a new empty destination')
    target.mkdir(parents=True)
    count = 0
    for parent, directories, files in os.walk(source, followlinks=False):
        directories[:] = [name for name in directories if name not in SKIP_DIRS
                          and not name.startswith('.venv') and not name.endswith('.egg-info')
                          and not (skip_core and Path(parent) == source and name == 'agent-core')
                          and not (Path(parent) / name).is_symlink()]
        for name in files:
            src = Path(parent) / name
            if src.is_symlink() or any(fnmatch.fnmatch(name, pattern) for pattern in SKIP_FILES):
                continue
            if name.startswith('.env') and name != '.env.example':
                continue
            if name == 'vite.config.js' and src.with_suffix('.ts').exists():
                continue
            if src.stat().st_size > 10 * 1024 * 1024:
                raise SystemExit('Unexpected large source file: ' + str(src.relative_to(source)))
            dst = target / src.relative_to(source)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-dir', required=True, type=Path)
    parser.add_argument('--core-dir', required=True, type=Path)
    args = parser.parse_args()
    main_dir, core_dir = args.main_dir.resolve(), args.core_dir.resolve()
    for target in (main_dir, core_dir):
        if target == ROOT or target in ROOT.parents:
            raise SystemExit('Destination must not replace a source directory')
        if target.is_relative_to(ROOT) and not target.is_relative_to(ROOT / '.stock-private'):
            raise SystemExit('In-project exports must stay under .stock-private')
    print(json.dumps({'mainFiles': copy_source(ROOT, main_dir, skip_core=True),
                      'coreFiles': copy_source(ROOT / 'agent-core', core_dir)}))


if __name__ == '__main__':
    main()
