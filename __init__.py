# -*- coding: utf-8 -*-


def classFactory(iface):  # pylint: disable=invalid-name
    """Load the koji MapBundle plugin."""
    from .koji_MapBundle import KojiMapBundle

    return KojiMapBundle(iface)
