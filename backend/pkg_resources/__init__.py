"""
Shim pkg_resources — fournit l'API minimale via importlib.metadata (Python 3.8+).
Placé dans le backend/ pour être trouvé en premier dans sys.path quand manage.py
est exécuté, sans dépendre de setuptools installé.
"""
try:
    from importlib.metadata import version as _version, PackageNotFoundError as _NF
except ImportError:
    _NF = Exception

    def _version(name):
        raise _NF(name)


class DistributionNotFound(Exception):
    pass


class Distribution:
    def __init__(self, name, ver):
        self.project_name = name
        self.version = ver
        self.key = name.lower()

    def __str__(self):
        return f"{self.project_name} {self.version}"


def get_distribution(name):
    for _n in (name, name.replace("-", "_"), name.replace("_", "-")):
        try:
            return Distribution(name, _version(_n))
        except (_NF, Exception):
            pass
    raise DistributionNotFound(name)


def require(requirements):
    return []


class WorkingSet:
    def require(self, requirements):
        return []

    def __iter__(self):
        return iter([])


working_set = WorkingSet()
