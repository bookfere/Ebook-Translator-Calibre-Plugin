from qt.core import QMessageBox  # type: ignore


class AlertMessage:
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

    def __init__(self, parent=None):
        self.parent = parent

    def pop(self, text, level='info'):
        alert = QMessageBox(self.parent)
        alert.setIcon(self.icons.get(level))
        alert.setText(text)
        return alert.exec_()

    def ask(self, text, level='ask'):
        alert = QMessageBox(self.parent)
        alert.setIcon(self.icons.get(level))
        alert.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        alert.setDefaultButton(QMessageBox.No)
        alert.setText(text)
        return self.actions.get(alert.exec_())
