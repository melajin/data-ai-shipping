"""Process-local numerical policies for reviewing the existing round63 design.

The vendored generator groups normalization methods with ``list(set(...))``.
This context changes only the order of the three returned mappings. Shuffle
configurations and their values remain those produced by the original method.
Use it around one experiment in a process;the class patch is not thread-local.
"""
from collections import OrderedDict
from contextlib import contextmanager

# experiment adds this workspace's vendored TabICL to sys.path. Importing it
# creates neither a classifier instance nor a CUDA context/model fit.
import experiment as _experiment
from tabicl._sklearn.preprocessing import EnsembleGenerator


@contextmanager
def deterministic_native_order():
    """Order native normalization groups by ``self.norm_methods_`` and restore.

    For round63 the requested order is ``none``,then ``power``. Other callers
    retain their own requested order,including when only a subset is used.
    Nesting and exceptions restore exactly the method present upon entry.
    """
    original = EnsembleGenerator._generate_ensemble

    def generate_in_requested_order(self):
        mappings = original(self)
        if len(mappings) != 3:
            raise RuntimeError("Expected three native ensemble configuration mappings")
        keys = set(mappings[0])
        if any(set(mapping) != keys for mapping in mappings[1:]):
            raise RuntimeError("Native ensemble mappings have inconsistent method keys")
        requested = list(dict.fromkeys(self.norm_methods_))
        methods = [method for method in requested if method in keys]
        if set(methods) != keys:
            raise RuntimeError("Native ensemble returned an unrequested normalization method")
        return tuple(
            OrderedDict((method, mapping[method]) for method in methods)
            for mapping in mappings
        )

    EnsembleGenerator._generate_ensemble = generate_in_requested_order
    try:
        yield
    finally:
        EnsembleGenerator._generate_ensemble = original
