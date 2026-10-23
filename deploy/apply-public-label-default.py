"""Patch only the reviewed validator in an existing runtime module."""
import ast
import hashlib
from pathlib import Path


def function(source: str, name: str):
    node = next(node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    return node, ast.get_source_segment(source, node)


target = Path('/app/app/routers/sources.py')
original = target.read_text()
reviewed = Path('/tmp/reviewed-sources.py').read_text()
expected = {
    '_checked_label': '42d49659fd810bf5f519ad165ef3906676927cbc969e3d0aef86503208051500',
    'upload_source': '4a4a92ce1eb91d42036dee61ea3e4748a1d75ae66fbc3a83dcec51bf68d18fc8',
    'create_url_source': '079066a0f8303f42882d1cf4b87e691ee8430e3b152424a9a8371006bab9457f',
}
changes = []
for name, expected_hash in expected.items():
    node, old = function(original, name)
    _, replacement = function(reviewed, name)
    assert old == replacement or hashlib.sha256(old.encode()).hexdigest() == expected_hash, f'Runtime {name} changed; review before patching'
    changes.append((node, replacement))
lines = original.splitlines(keepends=True)
for node, replacement in sorted(changes, key=lambda change: change[0].lineno, reverse=True):
    lines[node.lineno - 1:node.end_lineno] = [replacement + '\n']
updated = ''.join(lines)
_, scope_helper = function(reviewed, '_checked_create_scope')
assert not any(getattr(node, 'name', None) == '_checked_create_scope' for node in ast.parse(original).body)
updated += '\n\n' + scope_helper + '\n'
compile(updated, str(target), 'exec')
target.write_text(updated)
print('Patched reviewed upload validators and handlers; retained other runtime source behavior')
