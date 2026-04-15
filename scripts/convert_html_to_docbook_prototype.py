#!/usr/bin/env python3
"""Prototype HTML -> DocBook converter

Usage:
  convert_html_to_docbook_prototype.py -i <input_dir> -o <output_dir> --base-uri <base_uri> --version-id <version>

This prototype maps titles, headings, paragraphs, lists, code blocks and images.
It detects <dfn> elements and emits a <termmeta> block for them.
Output is formatted with 4-space indentation. Inline tags (b, i, em, strong, code, a, etc.) are kept on the same line where possible.
"""

import os
import sys
import argparse
import shutil
from bs4 import BeautifulSoup
from lxml import etree
from xml.dom import minidom
import re

NSMAP = None
INLINE_TAGS = {'b','i','em','strong','code','tt','a','span','small','sub','sup','dfn','glossterm'}


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def copy_asset(src, dst_dir):
    ensure_dir(dst_dir)
    dst = os.path.join(dst_dir, os.path.basename(src))
    try:
        shutil.copy2(src, dst)
        return os.path.relpath(dst, start=os.path.dirname(dst_dir))
    except Exception:
        return src


def element_to_docbook(el, parent, assets_dir, base_uri, file_rel_path, version_id, status):
    name = el.name
    if name is None:
        text = el.strip()
        if text:
            parent.append(etree.Element('para'))
            parent[-1].text = text
        return
    if name in ['h1','h2','h3','h4','h5','h6']:
        sec = etree.SubElement(parent, 'section')
        title = etree.SubElement(sec, 'title')
        title.text = el.get_text().strip()
        return sec
    if name == 'p':
        p = etree.SubElement(parent, 'para')
        p.text = el.get_text().strip()
        return
    if name == 'ul':
        lst = etree.SubElement(parent, 'itemizedlist')
        for li in el.find_all('li', recursive=False):
            item = etree.SubElement(lst, 'listitem')
            para = etree.SubElement(item, 'para')
            para.text = li.get_text().strip()
        return
    if name == 'ol':
        lst = etree.SubElement(parent, 'orderedlist')
        for li in el.find_all('li', recursive=False):
            item = etree.SubElement(lst, 'listitem')
            para = etree.SubElement(item, 'para')
            para.text = li.get_text().strip()
        return
    if name in ['pre','code']:
        code = etree.SubElement(parent, 'programlisting')
        code.text = el.get_text()
        return
    if name == 'img':
        media = etree.SubElement(parent, 'mediaobject')
        imageobject = etree.SubElement(media, 'imageobject')
        imagedata = etree.SubElement(imageobject, 'imagedata')
        src = el.get('src','')
        # copy asset if local
        if not src.startswith('http'):
            src_path = os.path.join(os.getcwd(), src.replace('/', os.sep))
            copied = copy_asset(src_path, assets_dir)
            imagedata.set('fileref', os.path.join(os.path.basename(assets_dir), os.path.basename(copied)))
        else:
            imagedata.set('fileref', src)
        return
    if name == 'dfn':
        # treat as definition term
        gloss = etree.SubElement(parent, 'glossentry')
        term = etree.SubElement(gloss, 'glossterm')
        term.text = el.get_text().strip()
        # add termmeta
        termmeta = etree.SubElement(gloss, 'termmeta')
        tid = el.get('id') or (os.path.splitext(os.path.basename(file_rel_path))[0] + '-' + re.sub(r'\s+','-', term.text))
        termmeta.set('{http://www.w3.org/XML/1998/namespace}id', tid)
        authority = etree.SubElement(termmeta, 'authority')
        authority.text = 'CCCBR'
        status_el = etree.SubElement(termmeta, 'status')
        status_el.text = status
        version_el = etree.SubElement(termmeta, 'version-id')
        version_el.text = version_id
        uri_el = etree.SubElement(termmeta, 'canonical-uri')
        uri_el.text = base_uri.rstrip('/') + '/' + file_rel_path.replace('\\','/')
        prov = etree.SubElement(termmeta, 'provenance')
        prov.text = file_rel_path
        return
    # fallback: render text
    text = el.get_text().strip()
    if text:
        p = etree.SubElement(parent, 'para')
        p.text = text


def pretty_print_xml_string(xml_bytes, indent_spaces=4):
    # parse with minidom for initial pretty print
    try:
        parsed = minidom.parseString(xml_bytes)
    except Exception:
        # fallback: decode and return raw
        return xml_bytes.decode('utf-8')
    s = parsed.toprettyxml(indent=' ' * indent_spaces, encoding='utf-8')
    if isinstance(s, bytes):
        s = s.decode('utf-8')
    # collapse inline tags so <b>..</b> stays on one line
    inline_tags_pattern = r"\\n(\\s*)<(?:" + '|'.join(INLINE_TAGS) + r")( [^>]*)?>\\n(\\s*)([^<]+)\\n(\\s*)</(?:" + '|'.join(INLINE_TAGS) + r")( [^>]*)?>"
    # simple post-processing: replace patterns like \n    for tag in INLINE_TAGS:
        open_re = re.compile(r"\\n(\\s*)<%s([^>]*)>\\n(\\s*)" % re.escape(tag))
        close_re = re.compile(r"\\n(\\s*)</%s>\\n" % re.escape(tag))
        s = open_re.sub(r"<%s\2>" % tag, s)
        s = close_re.sub(r"</%s>\n" % tag, s)
    # remove empty lines
    s = re.sub(r"\n\s*\n+", '\n', s)
    return s


def convert_file(in_path, out_path, assets_dir, base_uri, version_id, status, indent_spaces=4):
    with open(in_path, 'r', encoding='utf-8') as fh:
        soup = BeautifulSoup(fh, 'html.parser')
    title_text = None
    if soup.title:
        title_text = soup.title.string
    body = soup.body
    root = etree.Element('article', nsmap=NSMAP)
    info = etree.SubElement(root, 'info')
    if title_text:
        t = etree.SubElement(info, 'title')
        t.text = title_text
    meta = etree.SubElement(info, 'othermeta')
    meta.text = 'source=' + in_path
    content = etree.SubElement(root, 'section')
    for child in body.find_all(recursive=False):
        element_to_docbook(child, content, assets_dir, base_uri, os.path.relpath(in_path, start=os.getcwd()), version_id, status)
    ensure_dir(os.path.dirname(out_path))
    # serialize to bytes then pretty print with control over indentation
    xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
    pretty = pretty_print_xml_string(xml_bytes, indent_spaces=indent_spaces)
    with open(out_path, 'w', encoding='utf-8') as out:
        out.write(pretty)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('-i','--input', required=True, help='Input directory containing HTML files')
    p.add_argument('-o','--output', required=True, help='Output directory for DocBook XML')
    p.add_argument('--base-uri', required=True, help='Base URI for canonical links')
    p.add_argument('--version-id', default='v2', help='Version identifier')
    p.add_argument('--status', default='definitive', help='Version status')
    p.add_argument('--indent', type=int, default=4, help='Number of spaces to indent')
    args = p.parse_args(argv)

    input_dir = args.input
    output_dir = args.output
    assets_dir = os.path.join(output_dir, 'assets')
    ensure_dir(output_dir)
    ensure_dir(assets_dir)

    for fname in os.listdir(input_dir):
        if not fname.lower().endswith('.html'):
            continue
        in_path = os.path.join(input_dir, fname)
        out_fname = os.path.splitext(fname)[0] + '.xml'
        out_path = os.path.join(output_dir, out_fname)
        print('Converting', in_path, '->', out_path)
        convert_file(in_path, out_path, assets_dir, args.base_uri, args.version_id, args.status, indent_spaces=args.indent)

if __name__ == '__main__':
    main()
