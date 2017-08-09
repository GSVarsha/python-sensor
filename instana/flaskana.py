from __future__ import print_function
from instana import wsgi
import wrapt
import os


def wrapper(wrapped, instance, args, kwargs):
    rv = wrapped(*args, **kwargs)
    instance.wsgi_app = wsgi.iWSGIMiddleware(instance.wsgi_app)
    return rv


def hook(module):
    """ Hook method to install the Instana middleware into Flask """
    if "INSTANA_DEV" in os.environ:
        print("==============================================================")
        print("Running flask hook")
        print("==============================================================")
    wrapt.wrap_function_wrapper('flask', 'Flask.__init__', wrapper)
