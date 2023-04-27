try:
    from qt.core import QMessageBox
except ImportError:
    from PyQt5.Qt import QMessageBox

icons = {
    'info': QMessageBox.Information,
    'warning': QMessageBox.Warning,
    'ask': QMessageBox.Question,
    'error': QMessageBox.Critical,
}

actions = {
    QMessageBox.Yes: 'yes',
    QMessageBox.No: 'no',
}


def pop_alert(parent, text, level='info'):
    alert = QMessageBox(parent)
    alert.setIcon(icons.get(level))
    alert.setText(text)
    return alert.exec_()


def ask_action(parent, text, level='info'):
    alert = QMessageBox(parent)
    alert.setIcon(icons.get(level))
    alert.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    alert.setDefaultButton(QMessageBox.No)
    alert.setText(text)
    return actions.get(alert.exec_())
