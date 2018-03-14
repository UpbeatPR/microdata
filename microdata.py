#!/usr/bin/env python

import sys
from lxml import etree, html

from collections import defaultdict
from w3lib.encoding import html_body_declared_encoding


try:
    import json
except ImportError:
    import simplejson as json


def root_node(text, encoding=None, base_url=None):
    try:
        text = text.read()
    except AttributeError:
        pass

    if isinstance(text, str):
        parser = html.HTMLParser(recover=True)
    else:
        parser = html.HTMLParser(encoding=encoding)

    try:
        return etree.fromstring(
            text,
            parser=parser,
            base_url=base_url
        )
    except ValueError as e:
        if 'Unicode strings with encoding declaration are not supported' in str(e):
            # html_body_declared_encoding may return None
            encoding = html_body_declared_encoding(text) or 'utf-8'

            return etree.fromstring(
                text.encode(encoding),
                parser=parser,
                base_url=base_url
            )
        raise


def get_items(value, encoding=None):
    """
    Pass in a string or file-like object and get a list of Items present in the
    HTML document.
    """
    if isinstance(value, etree.ElementBase):
        node = value
    else:
        node = root_node(value, encoding=encoding)

    return _find_items(node)


class Item(object):
    """
    A class for representing a microdata Item. Item properties are accessible
    as standard Python properties, which return either a unicode string
    or another Item.
    """

    def __init__(self, itemtype=None, itemid=None):
        """Create an Item, with an optional itemptype and/or itemid.
        """
        # itemtype can be a space delimited list
        if itemtype:
            self.itemtype = [URI(i) for i in itemtype.split(" ")]

        if itemid:
            self.itemid = URI(itemid)

        self.props = {}

    def __getattr__(self, name):
        return self.get(name)

    def set(self, name, value):
        """Set an item's property
        """
        if name in self.props:
            self.props[name].append(value)
        else:
            self.props[name] = [value]

    def get(self, name):
        """Get an item's property. In cases where there are multiple values for
        a given property this returns only the first. If the property is
        not set None is returned.
        """
        values = self.get_all(name)
        if len(values) > 0:
            return values[0]
        return None

    def get_all(self, name):
        """Get all the values for a given property. If the property is not
        set for the Item an empty list is returned.
        """
        if name in self.props:
            return self.props[name]
        else:
            return []

    def json(self):
        """Returns the Item expressed as JSON. If there's a better JSON
        representation please let me know :-)
        """
        return json.dumps(self.json_dict(), indent=2)

    def json_dict(self):
        """Returns the item, and its nested items as a python dictionary.
        """

        item = {}

        if self.itemtype:
            item['type'] = [i.string for i in self.itemtype]
        if self.itemid:
            item['id'] = self.itemid.string

        item['properties'] = props = defaultdict(list)

        for name, values in self.props.items():
            for v in values:
                if isinstance(v, Item):
                    props[name].append(v.json_dict())
                elif isinstance(v, URI):
                    props[name].append(v.string)
                else:
                    props[name].append(v)

        return item


class URI(object):

    def __init__(self, string):
        self.string = string

    def __eq__(self, other):
        if isinstance(other, URI):
            return self.string == other.string
        return False

    def __repr__(self):
        return self.string


# what follows are the guts of extracting the Items from a DOM

property_values = {
    'meta':     'content',
    'audio':    'src',
    'embed':    'src',
    'iframe':   'src',
    'img':      'src',
    'source':   'src',
    'video':    'src',
    'a':        'href',
    'area':     'href',
    'link':     'href',
    'object':   'data',
    'time':     'datetime',
}


def _find_items(e):
    items = []
    unlinked = []
    if _is_element(e) and _is_itemscope(e):
        item = _make_item(e)
        unlinked = _extract(e, item)
        items.append(item)
        for unlinked_element in unlinked:
            items.extend(_find_items(unlinked_element))
    else:
        for child in e.iterchildren():
            items.extend(_find_items(child))

    return items


def _extract(e, item):
    # looks in a DOM element for microdata to assign to an Item
    # _extract returns a list of elements which appeared to have microdata
    # but which were not directly related to the Item that was passed in
    unlinked = []

    for child in e.iterchildren():
        itemprop = _attr(child, "itemprop")
        itemscope = _is_itemscope(child)
        if itemprop and itemscope:
            nested_item = _make_item(child)
            unlinked.extend(_extract(child, nested_item))
            item.set(itemprop, nested_item)
        elif itemprop:
            value = _property_value(child)
            # itemprops may also be in a space delimited list
            for i in itemprop.split(" "):
                item.set(i, value)
            unlinked.extend(_extract(child, item))
        elif itemscope:
            unlinked.append(child)
        else:
            unlinked.extend(_extract(child, item))

    return unlinked

# helper functions around python's minidom


def _attr(e, name):
    return e.get(name, None)


def _is_element(e):
    return etree.iselement(e)


def _is_itemscope(e):
    return _attr(e, "itemscope") is not None


def _property_value(e):
    value = None
    attrib = property_values.get(e.tag, None)
    if attrib in ["href", "src"]:
        value = URI(e.get(attrib))
    elif attrib:
        value = e.get(attrib)
    else:
        value = e.get("content") or _text(e)
    return value


# Follows https://github.com/lxml/lxml/blob/4fd86ebeb11d859827cc7eae419488020a29bbc0/src/lxml/etree.pyx#L2930-L2963
def _textiter(node, predicate=None):
    ctx = etree.iterwalk(node, events=('start', 'end'))
    result = None
    while True:
        result = None
        while result is None:
            try:
                event, element = next(ctx)
            except StopIteration:
                return

            if predicate and not predicate(element):
                continue

            # For information on how .text and .tail differ
            # and are both needed, see
            # http://lxml.de/tutorial.html#elements-contain-text
            if event == 'start':
                result = element.text
            elif element is not node:
                result = element.tail
        yield result


def _text(e):
    return ''.join(_textiter(e, predicate=lambda el: el.tag != 'script'))


def _make_item(e):
    if not _is_itemscope(e):
        raise ValueError("element is not an Item")
    itemtype = _attr(e, "itemtype")
    itemid = _attr(e, "itemid")
    return Item(itemtype, itemid)


if __name__ == "__main__":
    try:
        from urllib.request import urlopen
    except ImportError:
        from urllib import urlopen

    if len(sys.argv) < 2:
        print("Usage: %s URL [...]" % sys.argv[0])
        sys.exit(1)

    for url in sys.argv[1:]:
        sys.stderr.write(url + "\n")

        microdata = {}
        microdata['items'] = items = []

        for item in get_items(urlopen(url)):
            items.append(item.json_dict())

        print(json.dumps(microdata, indent=2))
