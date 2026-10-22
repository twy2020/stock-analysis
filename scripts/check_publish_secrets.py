"""Check exported source against local credential values without printing secrets."""
import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE = re.compile(r'(?:key|password|secret|(?:access|refresh)?token(?:sha256)?)$', re.I)


def private_values():
    values = set()

    def remember(value):
        if isinstance(value, str):
            value = value.strip().strip('\"\'')
            if len(value) >= 12 and len(set(value)) > 4 and not value.startswith(('replace-', 'configure-')):
                values.add(value.encode())

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if SENSITIVE.search(key):
                    remember(item)
                if isinstance(item, (list, dict)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    sources = [ROOT / 'rag-chat-saas/.env']
    for directory in (ROOT / '.stock-private', ROOT / 'agent-core/.local', ROOT / 'rag-chat-saas/.local'):
        if directory.exists():
            sources.extend(p for p in directory.iterdir() if p.is_file())
            credentials = directory / 'credentials'
            if credentials.exists():
                sources.extend(p for p in credentials.rglob('*') if p.is_file())
    for path in sources:
        if not path.exists() or path.stat().st_size > 16 * 1024 * 1024:
            continue
        try:
            text = path.read_text('utf-8-sig')
        except (UnicodeError, OSError):
            continue
        if path.suffix in ('.token', '.key', '.pem'):
            remember(text)
        if path.suffix == '.json':
            try:
                visit(json.loads(text))
            except ValueError:
                pass
        for line in text.splitlines():
            key, separator, value = line.partition('=')
            if separator and SENSITIVE.search(key.strip()):
                remember(value)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs='+', type=Path)
    args = parser.parse_args()
    values = private_values()
    findings = []
    count = 0
    for directory in args.directories:
        for path in directory.rglob('*'):
            if not path.is_file() or '.git' in path.relative_to(directory).parts:
                continue
            count += 1
            if any(secret in path.read_bytes() for secret in values):
                findings.append(str(path.relative_to(directory)))
    print(json.dumps({'credentialValuesChecked': len(values), 'filesChecked': count,
                      'matchingFiles': findings}))
    if findings:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
