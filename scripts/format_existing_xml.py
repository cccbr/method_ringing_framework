#!/usr/bin/env python3
"""Reformat existing XML files to consistent indentation and inline-tag handling.
Usage: format_existing_xml.py <root_xml_dir> --indent 4
"""
import os
import sys
import argparse
from xml.dom import minidom
import re

INLINE_TAGS = {'b','i','em','strong','code','tt','a','span','small','sub','sup','dfn','glossterm'}


def pretty_bytes(xml_bytes, indent_spaces=4):
    try:
        parsed = minidom.parseString(xml_bytes)
    except Exception:
        return xml_bytes.decode('utf-8')
    s = parsed.toprettyxml(indent=' ' * indent_spaces, encoding='utf-8')
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    for tag in INLINE_TAGS:
        open_re = re.compile(r"\\n(\\s*)<%s([^>]*)>\\n(\\s*)" % re.escape(tag))
        close_re = re.compile(r"\\n(\\s*)</%s>\\n" % re.escape(tag))
        s = open_re.sub(r"<%s\2>" % tag, s)
        s = close_re.sub(r"</%s>\n" % tag, s)
    s = re.sub(r"\n\s*\n+", '\n', s)
    return s


def process_file(path, indent):
    with open(path, 'rb') as f:
        data = f.read()
    out = pretty_bytes(data, indent)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root')
    p.add_argument('--indent', type=int, default=4)
    args = p.parse_args()
    for dirpath, dirnames, filenames in os.walk(args.root):
        for fn in filenames:
            if fn.lower().endswith('.xml'):
                path = os.path.join(dirpath, fn)
                print('Formatting', path)
                try:
                    process_file(path, args.indent)
                except Exception as e:
                    print('Failed', path, e)

if __name__ == '__main__':
    main()
