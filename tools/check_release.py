"""Checks every style and the userscript before they reach people's browsers (run by GitHub on every push).

    python tools/check_release.py [--base <commit>]

- each style / userscript has its header: a name starting "Showdown Plus", a namespace, a version (1.2.3) and an
  update link pointing at its own file on GitHub ("my settings" must have NO update link: it is never updated)
- with --base: every file that changed since that commit has a higher version than it had there, so Stylus and
  Tampermonkey see the update (and files that didn't change keep theirs, so nobody re-downloads them)
- the CSS braces balance, and every embedded picture decodes and is the type it says it is
- a style over 2.5 MB gets a warning
Exits with an error if anything fails.
"""
import base64, binascii, glob, re, subprocess, sys

RAW = 'https://raw.githubusercontent.com/dasmins/showdown-plus/main/'
SETTINGS = 'styles/showdown-plus-my-settings.user.css'
MAGIC = {'gif': b'GIF8', 'png': b'\x89PNG', 'webp': b'RIFF'}
errors, warnings = [], []


def files():
    out = glob.glob('styles/*.user.css') + glob.glob('styles/maps/*.user.css') + glob.glob('vfx/*/showdown-vfx-*.user.css')
    return sorted(out) + ['userscript/showdown-pin-controls.user.js']


def meta(text, js):
    if js:
        m = re.search(r'// ==UserScript==(.*?)// ==/UserScript==', text, re.S)
        pat = r'^//\s*@(\S+)\s+(.*?)\s*$'
    else:
        m = re.search(r'/\* ==UserStyle==(.*?)==/UserStyle== \*/', text, re.S)
        pat = r'^@(\S+)\s+(.*?)\s*$'
    if not m:
        return None
    return {k: v for k, v in re.findall(pat, m.group(1), re.M)}


def ver(v):
    return tuple(int(x) for x in v.split('.'))


def braces(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', '""', css)
    depth = 0
    for ch in css:
        depth += (ch == '{') - (ch == '}')
        if depth < 0:
            return False
    return depth == 0


def main():
    base = sys.argv[sys.argv.index('--base') + 1] if '--base' in sys.argv else None
    if base and set(base) == {'0'}:
        base = None                                   # (the first push of a branch: nothing to compare with)
    for p in files():
        text = open(p, encoding='utf-8').read()
        js = p.endswith('.js')
        m = meta(text, js)
        if m is None:
            errors.append('%s: no header' % p); continue
        if not m.get('name', '').startswith('Showdown Plus'):
            errors.append('%s: name should start "Showdown Plus" (%r)' % (p, m.get('name')))
        if not m.get('namespace'):
            errors.append('%s: no namespace' % p)
        if not re.fullmatch(r'\d+\.\d+\.\d+', m.get('version', '')):
            errors.append('%s: version should look like 1.2.3 (%r)' % (p, m.get('version'))); continue
        if p == SETTINGS:
            if 'updateURL' in m:
                errors.append('%s: must not have an update link (it would overwrite people\'s settings)' % p)
        elif m.get('updateURL') != RAW + p:
            errors.append('%s: update link should be %s%s (%r)' % (p, RAW, p, m.get('updateURL')))
        if js and m.get('downloadURL') != RAW + p:
            errors.append('%s: download link should be %s%s' % (p, RAW, p))
        if not js:
            if not braces(text):
                errors.append('%s: the { } braces don\'t balance' % p)
            for kind, data in re.findall(r'url\("data:image/(\w+);base64,([A-Za-z0-9+/=]+)"\)', text):
                try:
                    raw = base64.b64decode(data, validate=True)
                except binascii.Error:
                    errors.append('%s: an embedded %s picture is not valid base64' % (p, kind)); continue
                if not raw.startswith(MAGIC.get(kind, b'')) or (kind == 'webp' and raw[8:12] != b'WEBP'):
                    errors.append('%s: an embedded picture says %s but is not' % (p, kind))
            if len(text.encode()) > 2.5e6:
                warnings.append('%s: %.1f MB (large: every page with it on loads all of it)' % (p, len(text.encode()) / 1e6))
        if base and p != SETTINGS:
            old = subprocess.run(['git', 'show', '%s:%s' % (base, p)], capture_output=True, text=True, encoding='utf-8')
            if old.returncode == 0 and old.stdout != text:
                om = meta(old.stdout, js) or {}
                try:
                    if ver(m['version']) <= ver(om.get('version', '0.0.0')):
                        errors.append('%s: changed but its version (%s) is not higher than before (%s)' % (p, m['version'], om.get('version')))
                except ValueError:
                    pass
    for w in warnings:
        print('warning:', w)
    for e in errors:
        print('ERROR:', e)
    print('%d files checked, %d errors, %d warnings' % (len(files()), len(errors), len(warnings)))
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
