try:
    from qt.core import Qt, QShortcut, QKeySequence
except ImportError:
    from PyQt5.Qt import Qt, QShortcut, QKeySequence


def get_standard_key(key):
    return getattr(QKeySequence, key, None) or getattr(
        QKeySequence.StandardKey, key)


shortcuts = {
    'save': get_standard_key('Save'),
    'search': get_standard_key('Find'),
}


def set_shortcut(widget, action, callback, tip=None):
    if isinstance(action, str) and action in shortcuts.keys():
        action = shortcuts.get(action.lower())
    if isinstance(action, (QKeySequence, QKeySequence.StandardKey, str, int)):
        action = QKeySequence(action)
        shortcut = QShortcut(action, widget)
        shortcut.activated.connect(callback)
        if tip is not None:
            widget.setToolTip('%s [%s]' % (tip, action.toString()))
