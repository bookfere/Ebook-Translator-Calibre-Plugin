try:
    from qt.core import QFrame
except ImportError:
    from PyQt5.Qt import QFrame


def get_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.HLine)
    divider.setFrameShadow(QFrame.Sunken)
    return divider
