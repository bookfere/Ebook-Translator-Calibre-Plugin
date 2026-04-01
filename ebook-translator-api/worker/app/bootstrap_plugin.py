import importlib.util
import os
import sys
import types
import builtins
from pathlib import Path


def ensure_calibre_runtime() -> None:
    calibre_root = Path("/usr/lib/calibre")
    calibre_plugins = calibre_root / "calibre" / "plugins"
    calibre_resources = Path("/usr/share/calibre")
    dist_packages = Path("/usr/lib/python3/dist-packages")

    if calibre_root.exists():
        calibre_root_str = str(calibre_root)
        if calibre_root_str not in sys.path:
            sys.path.insert(0, calibre_root_str)
    if dist_packages.exists():
        dist_packages_str = str(dist_packages)
        if dist_packages_str not in sys.path:
            sys.path.insert(0, dist_packages_str)

    # Debian's calibre package expects these attrs to exist when imported
    # outside the calibre launcher process.
    if not hasattr(sys, "extensions_location"):
        sys.extensions_location = str(calibre_plugins)
    if not hasattr(sys, "resources_location"):
        sys.resources_location = str(calibre_resources)
    if not hasattr(sys, "executables_location"):
        sys.executables_location = os.path.dirname(sys.executable)


def ensure_plugin_importable(source_path: str) -> None:
    ensure_calibre_runtime()
    if not hasattr(builtins, "load_translations"):
        builtins.load_translations = lambda: None  # type: ignore[attr-defined]

    package_name = "calibre_plugins.ebook_translator"
    if package_name in sys.modules:
        return

    root = Path(source_path).resolve()
    init_path = root / "__init__.py"
    if not init_path.exists():
        raise RuntimeError(f"Plugin source not found: {init_path}")

    parent_name = "calibre_plugins"
    if parent_name not in sys.modules:
        parent_module = types.ModuleType(parent_name)
        parent_module.__path__ = [str(root.parent)]
        sys.modules[parent_name] = parent_module

    spec = importlib.util.spec_from_file_location(
        package_name,
        str(init_path),
        submodule_search_locations=[str(root)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to build import spec for plugin package")

    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
