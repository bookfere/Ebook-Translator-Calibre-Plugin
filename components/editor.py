from qt.core import (  # type: ignore
    Qt, QWidget, QSize, QPlainTextEdit, QPaintEvent, QPainter, QTextEdit,
    QColor, QTextFormat)


class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.lineNumberArea = LineNumberArea(self)

        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)

        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

    def lineNumberAreaWidth(self):
        digits = 1
        count = self.blockCount()
        while count >= 10:
            count //= 10
            digits += 1
        return self.fontMetrics().horizontalAdvance('9') * digits + 5

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.lineNumberArea.setGeometry(
            rect.left(), rect.top(), self.lineNumberAreaWidth(), rect.height())

    def lineNumberAreaPaintEvent(self, event: QPaintEvent):
        painter = QPainter(self.lineNumberArea)
        try:
            painter.fillRect(event.rect(), QColor(127, 127, 127, 100))
            block = self.firstVisibleBlock()
            blockNumber = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(
                self.contentOffset()).top()
            bottom = top + self.blockBoundingGeometry(block).height()

            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(blockNumber + 1)
                    painter.drawText(
                        0, int(top), self.lineNumberArea.width() - 2,
                        self.fontMetrics().height(),
                        Qt.AlignRight, number)

                block = block.next()
                top = bottom
                bottom += self.blockBoundingGeometry(block).height()
                blockNumber += 1
        finally:
            painter.end()

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(
                0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly() and self.toPlainText() != '':
            selection = QTextEdit.ExtraSelection()

            lineColor = QColor(Qt.yellow)
            lineColor.setAlpha(127)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(
                QTextFormat.Property.FullWidthSelection, True)

            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()

            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)


class LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)
