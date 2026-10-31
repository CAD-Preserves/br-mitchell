#!/usr/bin/env bash
# Generate Doxygen documentation if available and refresh Markdown API reference in docs/.
set -euo pipefail
cd "$(dirname "$0")"

if command -v doxygen >/dev/null 2>&1; then
  doxygen docs/Doxyfile
fi

python -c "import ast, glob, os; lines = ['# API Reference (\`core/\`)', '']; files = sorted(glob.glob('core/*.py')); [lines.extend(['## \`' + os.path.basename(f) + '\`', '', (ast.get_docstring(ast.parse(open(f, encoding='utf-8').read())) or '').strip(), ''] + ['* **\`' + n.name + '\`** — ' + ((ast.get_docstring(n) or '').splitlines()[0] if ast.get_docstring(n) else '') for n in ast.walk(ast.parse(open(f, encoding='utf-8').read())) if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and not n.name.startswith('_')] + ['']) for f in files]; open('docs/api_reference.md', 'w', encoding='utf-8').write('\n'.join(lines)); print('Generated docs/api_reference.md')"

