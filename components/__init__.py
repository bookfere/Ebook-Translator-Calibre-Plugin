from .engine import EngineList, EngineTester, ManageCustomEngine
from .info import layout_info
from .lang import SourceLang, TargetLang
from .format import InputFormat, OutputFormat
from .alert import AlertMessage
from .table import AdvancedTranslationTable
from .mode import ModeSelection
from .cache import CacheManager


try:
    from qt.core import Qt, QFrame
except ImportError:
    from PyQt5.Qt import Qt, QFrame


def get_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.HLine)
    divider.setFrameShadow(QFrame.Sunken)
    return divider


def qt_version():
    return vars(Qt).get('QT_VERSION_STR')
