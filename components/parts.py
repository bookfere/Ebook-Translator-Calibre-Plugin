try:
    from qt.core import QMessageBox, QFrame
except ImportError:
    from PyQt5.Qt import QMessageBox, QFrame


def pop_alert(parent, text, level='info'):
    icons = {
        'info': QMessageBox.Information,
        'warning': QMessageBox.Warning,
        'ask': QMessageBox.Question,
        'error': QMessageBox.Critical,
    }
    alert = QMessageBox(parent)
    alert.setIcon(icons[level])
    alert.setText(text)
    alert.exec_()


def get_divider():
    divider = QFrame()
    divider.setFrameShape(QFrame.HLine)
    divider.setFrameShadow(QFrame.Sunken)
    return divider
