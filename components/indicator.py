from qt.core import (  # type: ignore
    Qt, QPen, QWidget, QPainter, QColor, QHBoxLayout, QLabel)


load_translations()  # type: ignore


class StatusColor:
    _color_meanings = {
        'green': _('Translated'),
        'yellow': _('Non-aligned'),
        'gray': _('Untranslated'),
        'red': _('Failed translation'),
        'transparent': _('Not selected'),
    }

    def __init__(self, color_str):
        if color_str in self._color_meanings:
            self._value = color_str
        else:
            self._value = 'transparent'

    def __str__(self):
        return self._value

    @property
    def meaning(self):
        return self._color_meanings[self._value]


class CircularStatusWidget(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.color = StatusColor('transparent')
        self.set_color(self.color)
        self._init_ui()

    def set_color(self, color):
        self.color = color
        self.update()

    def _init_ui(self):
        diameter = 16
        self.setFixedSize(diameter, diameter)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(str(self.color)))
        pen = QPen(QColor(127, 127, 127))
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class TranslationStatus(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.shape = CircularStatusWidget(self)
        self.message = QLabel(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.shape)
        layout.addWidget(self.message)

    def set_color(self, color, tip=None):
        self.shape.set_color(color)
        self.message.setText(color.meaning)
        self.setToolTip(tip or color.meaning)
