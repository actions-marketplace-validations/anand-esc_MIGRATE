# Demo slice: 13 functions extracted verbatim (module-level helpers included
# only where a function depends on them) from CPython 2.7's Lib/urllib.py.
#
# Source:  https://github.com/python/cpython/blob/2.7/Lib/urllib.py
# License: PSF License (CPython). Used here as a bounded, real-world sample
#          for a hackathon demo of Py2->Py3 conversion + behavioral diffing.
#          Not redistributed as part of any shipped product.
#
# This file is intentionally left running under Python 2 syntax/semantics.
# It is the "before" input to the pipeline (Om's classifier reads it,
# Suryansh's converter/critic produces a Python 3 version of each function,
# Pritam's verifier runs both versions in sandboxes and diffs behavior).
#
# See manifest.json in this directory for the function list, why each one
# was picked, and its expected classifier tag.

import re
import os
import sys


# ---------------------------------------------------------------------------
# _is_unicode: py2-only helper several functions below depend on.
# ---------------------------------------------------------------------------
try:
    unicode
except NameError:
    def _is_unicode(x):
        return 0
else:
    def _is_unicode(x):
        return isinstance(x, unicode)


# ---------------------------------------------------------------------------
# 1. unwrap -- simple string slicing, no regex. Mechanical, no py2/py3
#    surface-syntax issues at all. Good template_match baseline.
# ---------------------------------------------------------------------------
def unwrap(url):
    """unwrap('<URL:type://host/path>') --> 'type://host/path'."""
    url = url.strip()
    if url[:1] == '<' and url[-1:] == '>':
        url = url[1:-1].strip()
    if url[:4] == 'URL:': url = url[4:].strip()
    return url


# ---------------------------------------------------------------------------
# 2. splittype -- module-level regex cache via `global`. Mechanical.
# ---------------------------------------------------------------------------
_typeprog = None
def splittype(url):
    """splittype('type:opaquestring') --> 'type', 'opaquestring'."""
    global _typeprog
    if _typeprog is None:
        _typeprog = re.compile('^([^/:]+):')

    match = _typeprog.match(url)
    if match:
        scheme = match.group(1)
        return scheme.lower(), url[len(scheme) + 1:]
    return None, url


# ---------------------------------------------------------------------------
# 3. splithost -- same shape as splittype. Mechanical.
# ---------------------------------------------------------------------------
_hostprog = None
def splithost(url):
    """splithost('//host[:port]/path') --> 'host[:port]', '/path'."""
    global _hostprog
    if _hostprog is None:
        _hostprog = re.compile('//([^/#?]*)(.*)', re.DOTALL)

    match = _hostprog.match(url)
    if match:
        host_port = match.group(1)
        path = match.group(2)
        if path and not path.startswith('/'):
            path = '/' + path
        return host_port, path
    return None, url


# ---------------------------------------------------------------------------
# 4. splitport -- regex-based split with an inline literal char class.
#    Mechanical.
# ---------------------------------------------------------------------------
_portprog = None
def splitport(host):
    """splitport('host:port') --> 'host', 'port'."""
    global _portprog
    if _portprog is None:
        _portprog = re.compile('^(.*):([0-9]*)$')

    match = _portprog.match(host)
    if match:
        host, port = match.groups()
        if port:
            return host, port
    return host, None


# ---------------------------------------------------------------------------
# 5. splitquery -- mechanical.
# ---------------------------------------------------------------------------
_queryprog = None
def splitquery(url):
    """splitquery('/path?query') --> '/path', 'query'."""
    global _queryprog
    if _queryprog is None:
        _queryprog = re.compile('^(.*)\?([^?]*)$')

    match = _queryprog.match(url)
    if match: return match.group(1, 2)
    return url, None


# ---------------------------------------------------------------------------
# 6. splittag -- mechanical.
# ---------------------------------------------------------------------------
_tagprog = None
def splittag(url):
    """splittag('/path#tag') --> '/path', 'tag'."""
    global _tagprog
    if _tagprog is None:
        _tagprog = re.compile('^(.*)#([^#]*)$')

    match = _tagprog.match(url)
    if match: return match.group(1, 2)
    return url, None


# ---------------------------------------------------------------------------
# 7. splitattr -- no regex at all, pure list slicing. Trivial template_match.
# ---------------------------------------------------------------------------
def splitattr(url):
    """splitattr('/path;attr1=value1;attr2=value2;...') ->
        '/path', ['attr1=value1', 'attr2=value2', ...]."""
    words = url.split(';')
    return words[0], words[1:]


# ---------------------------------------------------------------------------
# 8. splitvalue -- mechanical.
# ---------------------------------------------------------------------------
_valueprog = None
def splitvalue(attr):
    """splitvalue('attr=value') --> 'attr', 'value'."""
    global _valueprog
    if _valueprog is None:
        _valueprog = re.compile('^([^=]*)=(.*)$')

    match = _valueprog.match(attr)
    if match: return match.group(1, 2)
    return attr, None


# ---------------------------------------------------------------------------
# 9. unquote -- branches on _is_unicode(s) vs plain str/bytes. This is the
#    py2 str/unicode split collapsing into py3's single str type; a naive
#    syntax-only conversion changes behavior for byte-string input.
#    llm_needed: requires understanding py2 str-vs-unicode semantics, not
#    just syntax substitution.
# ---------------------------------------------------------------------------
_hexdig = '0123456789ABCDEFabcdef'
_hextochr = dict((a + b, chr(int(a + b, 16)))
                 for a in _hexdig for b in _hexdig)
_asciire = re.compile('([\x00-\x7f]+)')

def unquote(s):
    """unquote('abc%20def') -> 'abc def'."""
    if _is_unicode(s):
        if '%' not in s:
            return s
        bits = _asciire.split(s)
        res = [bits[0]]
        append = res.append
        for i in range(1, len(bits), 2):
            append(unquote(str(bits[i])).decode('latin1'))
            append(bits[i + 1])
        return ''.join(res)

    bits = s.split('%')
    # fastpath
    if len(bits) == 1:
        return s
    res = [bits[0]]
    append = res.append
    for item in bits[1:]:
        try:
            append(_hextochr[item[:2]])
            append(item[2:])
        except KeyError:
            append('%')
            append(item)
    return ''.join(res)


# ---------------------------------------------------------------------------
# 10. quote -- the flagship "why sandboxed diffing, not just syntax fixing"
#     example. `str(bytearray(xrange(256)))` builds a latin1-style byte->str
#     table that depends on py2's str/bytes being the same type. A
#     mechanical xrange->range substitution produces code that still RUNS
#     under Python 3 but silently builds a WRONG escaping table
#     (str(bytearray(...)) means something different in py3). This is
#     exactly the class of bug a diff-based verifier catches and a
#     "does it parse / does it run" check does not.
# ---------------------------------------------------------------------------
always_safe = ('ABCDEFGHIJKLMNOPQRSTUVWXYZ'
               'abcdefghijklmnopqrstuvwxyz'
               '0123456789' '_.-')
_safe_map = {}
for _i, _c in zip(xrange(256), str(bytearray(xrange(256)))):
    _safe_map[_c] = _c if (_i < 128 and _c in always_safe) else '%{:02X}'.format(_i)
_safe_quoters = {}

def quote(s, safe='/'):
    """quote('abc def') -> 'abc%20def'

    Each part of a URL, e.g. the path info, the query, etc., has a
    different set of reserved characters that must be quoted.

    By default, the quote function is intended for quoting the path
    section of a URL. Thus, it will not encode '/'.
    """
    # fastpath
    if not s:
        if s is None:
            raise TypeError('None object cannot be quoted')
        return s
    cachekey = (safe, always_safe)
    try:
        (quoter, safe) = _safe_quoters[cachekey]
    except KeyError:
        safe_map = _safe_map.copy()
        safe_map.update([(c, c) for c in safe])
        quoter = safe_map.__getitem__
        safe = always_safe + safe
        _safe_quoters[cachekey] = (quoter, safe)
    if not s.rstrip(safe):
        return s
    return ''.join(map(quoter, s))


def quote_plus(s, safe=''):
    """Quote the query fragment of a URL; replacing ' ' with '+'"""
    if ' ' in s:
        s = quote(s, safe + ' ')
        return s.replace(' ', '+')
    return quote(s, safe)


# ---------------------------------------------------------------------------
# 11. urlencode -- uses the old-style three-argument `raise Type, msg, tb`
#     syntax, which no longer parses at all under Python 3 (SyntaxError, not
#     a runtime behavior change). Also branches on isinstance(v, str) vs
#     _is_unicode(v), another py2 str/unicode split. llm_needed.
# ---------------------------------------------------------------------------
def urlencode(query, doseq=0):
    """Encode a sequence of two-element tuples or dictionary into a URL
    query string.

    If any values in the query arg are sequences and doseq is true, each
    sequence element is converted to a separate parameter.
    """
    if hasattr(query, "items"):
        query = query.items()
    else:
        try:
            if len(query) and not isinstance(query[0], tuple):
                raise TypeError
        except TypeError:
            ty, va, tb = sys.exc_info()
            raise TypeError, "not a valid non-string sequence or mapping object", tb

    l = []
    if not doseq:
        for k, v in query:
            k = quote_plus(str(k))
            v = quote_plus(str(v))
            l.append(k + '=' + v)
    else:
        for k, v in query:
            k = quote_plus(str(k))
            if isinstance(v, str):
                v = quote_plus(v)
                l.append(k + '=' + v)
            elif _is_unicode(v):
                v = quote_plus(v.encode("ASCII", "replace"))
                l.append(k + '=' + v)
            else:
                try:
                    len(v)
                except TypeError:
                    v = quote_plus(str(v))
                    l.append(k + '=' + v)
                else:
                    for elt in v:
                        l.append(k + '=' + quote_plus(str(elt)))
    return '&'.join(l)


# ---------------------------------------------------------------------------
# 12. getproxies_environment -- iterates os.environ.items() and does string
#     slicing/lowercasing. No py2-only syntax, but the two-pass "prefer
#     lowercase" logic is easy to get subtly wrong in translation. Good
#     template_match candidate that still deserves a real diff run.
# ---------------------------------------------------------------------------
def getproxies_environment():
    """Return a dictionary of scheme -> proxy server URL mappings.

    Scan the environment for variables named <scheme>_proxy; this seems to
    be the standard convention. In order to prefer lowercase variables, we
    process the environment in two passes, first matches any and second
    matches only lower case proxies.
    """
    proxies = {}
    for name, value in os.environ.items():
        name = name.lower()
        if value and name[-6:] == '_proxy':
            proxies[name[:-6]] = value

    if 'REQUEST_METHOD' in os.environ:
        proxies.pop('http', None)

    for name, value in os.environ.items():
        if name[-6:] == '_proxy':
            name = name.lower()
            if value:
                proxies[name[:-6]] = value
            else:
                proxies.pop(name[:-6], None)

    return proxies


# ---------------------------------------------------------------------------
# 13. proxy_bypass_environment -- calls splitport (function #4 above), so
#     the demo slice exercises intra-slice function dependencies, not just
#     isolated leaf functions.
# ---------------------------------------------------------------------------
def proxy_bypass_environment(host, proxies=None):
    """Test if proxies should not be used for a particular host.

    Checks the proxies dict for the value of no_proxy, which should be a
    list of comma separated DNS suffixes, or '*' for all hosts.
    """
    if proxies is None:
        proxies = getproxies_environment()
    try:
        no_proxy = proxies['no']
    except KeyError:
        return 0
    if no_proxy == '*':
        return 1
    hostonly, port = splitport(host)
    no_proxy_list = [proxy.strip() for proxy in no_proxy.split(',')]
    for name in no_proxy_list:
        if name:
            name = name.lstrip('.')
            name = re.escape(name)
            pattern = r'(.+\.)?%s$' % name
            if re.match(pattern, hostonly, re.I):
                return 1
    return 0
