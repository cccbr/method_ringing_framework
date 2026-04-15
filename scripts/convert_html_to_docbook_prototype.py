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


def clean_text(s):
    if s is None:
        return ''
    # replace NBSP and normalize to preserve internal spacing but trim ends
    return s.replace('\xa0',' ').strip()


def append_text(elem, txt):
    """Append cleaned txt to elem.text or last child's tail, ensuring single-space separation."""
    txt = clean_text(txt)
    if not txt:
        return
    children = list(elem)
    if not children:
        if elem.text is None or elem.text.strip() == '':
            elem.text = txt
        else:
            # ensure single space separation
            elem.text = elem.text.rstrip() + ' ' + txt
    else:
        last = children[-1]
        if last.tail is None or last.tail.strip() == '':
            last.tail = txt
        else:
            last.tail = last.tail.rstrip() + ' ' + txt


def render_inline(bsnode, para, assets_dir, base_uri, file_rel_path, version_id, status):
    """Render inline HTML children into a DocBook <para>, mapping common inline tags."""
    from bs4 import NavigableString, Tag
    for child in bsnode.children:
        if isinstance(child, NavigableString):
            txt = clean_text(str(child))
            append_text(para, txt)
            continue
        if not isinstance(child, Tag):
            continue
        tag = child.name
        text = clean_text(child.get_text())
        if tag in ('b','strong'):
            e = etree.SubElement(para, 'emphasis')
            e.set('role', 'bold')
            append_text(e, text)
            continue
        if tag in ('i','em'):
            e = etree.SubElement(para, 'emphasis')
            e.set('role', 'italic')
            append_text(e, text)
            continue
        if tag in ('code','tt'):
            e = etree.SubElement(para, 'literal')
            append_text(e, text)
            continue
        if tag == 'a':
            e = etree.SubElement(para, 'ulink')
            href = child.get('href','')
            if href:
                e.set('url', href)
            append_text(e, text)
            continue
        if tag == 'dfn':
            # inline definition: emit glossentry inline with termmeta
            gloss = etree.SubElement(para, 'glossentry')
            term = etree.SubElement(gloss, 'glossterm')
            append_text(term, text)
            termmeta = etree.SubElement(gloss, 'termmeta')
            tid = child.get('id') or (os.path.splitext(os.path.basename(file_rel_path))[0] + '-' + re.sub(r'\s+','-', term.text or ''))
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
            continue
        # fallback: render the inner text
        if text:
            append_text(para, text)


def element_to_docbook(el, parent, assets_dir, base_uri, file_rel_path, version_id, status):
    from bs4 import NavigableString
    name = el.name
    # text nodes
    if isinstance(el, NavigableString):
        text = clean_text(str(el))
        if text:
            p = etree.SubElement(parent, 'para')
            append_text(p, text)
        return
    # headings anywhere in the tree
    if name and re.match(r'h([1-6])', name):
        level = int(name[1])
        if level == 1:
            chap = etree.SubElement(parent, 'chapter')
            title = etree.SubElement(chap, 'title')
            title.text = el.get_text().strip()
            return
        elif level == 2:
            sect = etree.SubElement(parent, 'sect1')
            title = etree.SubElement(sect, 'title')
            title.text = el.get_text().strip()
            return
        else:
            # h3 -> sect2, h4 -> sect3 etc.
            sect_tag = 'sect' + str(level-1)
            sect = etree.SubElement(parent, sect_tag)
            title = etree.SubElement(sect, 'title')
            title.text = el.get_text().strip()
            return
    # paragraphs
    if name == 'p':
        p = etree.SubElement(parent, 'para')
        render_inline(el, p, assets_dir, base_uri, file_rel_path, version_id, status)
        return
    # container-like tags: recurse into children rather than flattening
    if name in ('div', 'section', 'main', 'article', 'row', 'container', 'container-fluid', 'col', 'col-sm-12', 'col-sm-11', 'col-xl-9'):
        for child in el.children:
            # skip purely navigational or script/style children
            if getattr(child, 'name', None) and child.name.lower() in ('script','style'):
                continue
            # recurse
            element_to_docbook(child, parent, assets_dir, base_uri, file_rel_path, version_id, status)
        return
    # lists
    if name == 'ul':
        lst = etree.SubElement(parent, 'itemizedlist')
        for li in el.find_all('li', recursive=False):
            item = etree.SubElement(lst, 'listitem')
            para = etree.SubElement(item, 'para')
            render_inline(li, para, assets_dir, base_uri, file_rel_path, version_id, status)
        return
    if name == 'ol':
        lst = etree.SubElement(parent, 'orderedlist')
        for li in el.find_all('li', recursive=False):
            item = etree.SubElement(lst, 'listitem')
            para = etree.SubElement(item, 'para')
            render_inline(li, para, assets_dir, base_uri, file_rel_path, version_id, status)
        return
    # code blocks
    if name in ['pre','code']:
        code = etree.SubElement(parent, 'programlisting')
        code.text = el.get_text()
        return
    # images
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
    # explicit definition tag
    if name == 'dfn':
        gloss = etree.SubElement(parent, 'glossentry')
        term = etree.SubElement(gloss, 'glossterm')
        term.text = el.get_text().strip()
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
    # example blocks (by class)
    if name == 'div' and ('example' in (el.get('class') or [])):
        ex = etree.SubElement(parent, 'example')
        # optional title
        if el.find(True):
            # render children inside example
            for child in el.children:
                if getattr(child, 'name', None) == 'h3':
                    t = etree.SubElement(ex, 'title')
                    t.text = child.get_text().strip()
                else:
                    if getattr(child, 'name', None):
                        element_to_docbook(child, ex, assets_dir, base_uri, file_rel_path, version_id, status)
                    else:
                        if child.strip():
                            p = etree.SubElement(ex, 'para')
                            p.text = child.strip()
        return
    # note/explanatory blocks (by class)
    if name == 'div' and ('explanation' in (el.get('class') or []) or 'explanatory' in (el.get('class') or [])):
        note = etree.SubElement(parent, 'note')
        render_inline(el, note, assets_dir, base_uri, file_rel_path, version_id, status)
        return
    # fallback: render inline text into a para
    text = el.get_text().strip()
    if text:
        p = etree.SubElement(parent, 'para')
        render_inline(el, p, assets_dir, base_uri, file_rel_path, version_id, status)


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
    # simple post-processing: move common inline tags onto the same line
    for tag in INLINE_TAGS:
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
    body = soup.body or soup

    # heuristics to find the main content container
    main = soup.find('main') or soup.find(id='content') or soup.find('article') or soup.find('div', class_='content') or body

    root = etree.Element('article', nsmap=NSMAP)
    info = etree.SubElement(root, 'info')
    if title_text:
        t = etree.SubElement(info, 'title')
        t.text = title_text
    meta = etree.SubElement(info, 'othermeta')
    meta.text = 'source=' + in_path

    # heading stack: level -> element
    stack = {1: None, 2: None, 3: None, 4: None}
    # default top-level container if no h1 present
    default_section = etree.SubElement(root, 'section')
    stack[1] = default_section

    def is_navigational(el):
        if not getattr(el, 'name', None):
            return False
        tag = el.name.lower()
        if tag in ('header', 'nav', 'footer', 'aside', 'script', 'style'):
            return True
        cls = ' '.join(el.get('class') or []).lower()
        idv = (el.get('id') or '').lower()
        for token in ('nav', 'menu', 'breadcrumb', 'toc', 'sidebar', 'version-switch', 'search', 'masthead', 'skip'):
            if token in cls or token in idv:
                return True
        return False

    for child in main.find_all(recursive=False):
        if is_navigational(child):
            continue
        if getattr(child, 'name', None) and re.match(r'h([1-6])', child.name):
            level = int(child.name[1])
            if level == 1:
                chap = etree.SubElement(root, 'chapter')
                title = etree.SubElement(chap, 'title')
                title.text = child.get_text().strip()
                stack[1] = chap
                stack[2] = stack[3] = stack[4] = None
            elif level == 2:
                parent = stack[1] if stack.get(1) is not None else root
                sect = etree.SubElement(parent, 'sect1')
                title = etree.SubElement(sect, 'title')
                title.text = child.get_text().strip()
                stack[2] = sect
                stack[3] = stack[4] = None
            elif level == 3:
                parent = stack[2] if stack.get(2) is not None else (stack[1] if stack.get(1) is not None else root)
                sect = etree.SubElement(parent, 'sect2')
                title = etree.SubElement(sect, 'title')
                title.text = child.get_text().strip()
                stack[3] = sect
                stack[4] = None
            else:
                parent = stack.get(level-1) if stack.get(level-1) is not None else (stack[1] if stack.get(1) is not None else root)
                sect_tag = 'sect' + str(level-1)
                sect = etree.SubElement(parent, sect_tag)
                title = etree.SubElement(sect, 'title')
                title.text = child.get_text().strip()
                stack[level] = sect
            continue
        # not a heading: attach to deepest stack level available
        parent = None
        for lvl in (4, 3, 2, 1):
            if stack.get(lvl) is not None:
                parent = stack[lvl]
                break
        if parent is None:
            parent = root
        element_to_docbook(child, parent, assets_dir, base_uri, os.path.relpath(in_path, start=os.getcwd()), version_id, status)

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
