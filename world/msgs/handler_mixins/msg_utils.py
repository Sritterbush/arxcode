"""
Utility functions to help with our message handlers.
"""

_cached_lazy_imports = {}


def lazy_import_from_str(clsname):
    """
    Stores imports
    Args:
        clsname:

    Returns:

    """
    from evennia.utils.utils import class_from_module
    if clsname in _cached_lazy_imports:
        return _cached_lazy_imports[clsname]
    cls = class_from_module("world.msgs.models." + clsname)
    _cached_lazy_imports[clsname] = cls
    return cls


def get_initial_queryset(clsname):
    """
    Gets an initial queryset for initializing our attributes.

        Args:
            clsname (str): Name of class from .models to import
    """
    cls = lazy_import_from_str(clsname)
    return cls.objects.all().order_by('-db_date_created')