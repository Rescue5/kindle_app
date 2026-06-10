from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from kindle_vocab_app.kindle_db import export_entries, fetch_entries, list_books, validate_vocab_db


DARK_STYLESHEET = """
QWidget {
    background: #111318;
    color: #e7e9ee;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMainWindow, QStatusBar { background: #111318; }
QToolBar {
    background: #171a21;
    border: 0;
    border-bottom: 1px solid #2a2f3a;
    spacing: 6px;
    padding: 8px 12px;
}
QToolButton, QPushButton {
    background: #252a35;
    border: 1px solid #353c49;
    border-radius: 6px;
    padding: 8px 12px;
}
QToolButton:hover, QPushButton:hover { background: #303744; }
QPushButton#primaryButton {
    background: #3976e8;
    border-color: #3976e8;
    color: white;
    font-weight: 600;
}
QPushButton#primaryButton:hover { background: #4a84ef; }
QComboBox {
    background: #1b1f27;
    border: 1px solid #353c49;
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 20px;
}
QComboBox QAbstractItemView {
    background: #1b1f27;
    border: 1px solid #353c49;
    selection-background-color: #3976e8;
}
QTableWidget {
    background: #171a21;
    alternate-background-color: #1b1f27;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    gridline-color: #2a2f3a;
    selection-background-color: #294f91;
}
QHeaderView::section {
    background: #20242d;
    color: #bfc5d0;
    border: 0;
    border-right: 1px solid #2a2f3a;
    border-bottom: 1px solid #2a2f3a;
    padding: 9px;
    font-weight: 600;
}
QFrame#controlBar {
    background: #171a21;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
}
QLabel#titleLabel { font-size: 20px; font-weight: 700; }
QLabel#mutedLabel { color: #929aa8; }
QCheckBox { spacing: 8px; }
QStatusBar { color: #929aa8; border-top: 1px solid #2a2f3a; }
QScrollBar:vertical { background: #171a21; width: 12px; }
QScrollBar::handle:vertical { background: #3a414f; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db_path: Path | None = None
        self.entries: list[dict[str, object]] = []

        self.setWindowTitle("Kindle Vocabulary Export")
        self.resize(1180, 760)
        self.setMinimumSize(840, 560)
        self._build_toolbar()
        self._build_content()
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Откройте vocab.db с подключенного Kindle")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Основные действия")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        open_action = QAction(
            self.style().standardIcon(self.style().StandardPixmap.SP_DialogOpenButton),
            "Открыть vocab.db",
            self,
        )
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_database)
        toolbar.addAction(open_action)

        toolbar.addSeparator()

        export_anki = QAction("Экспорт в Anki", self)
        export_anki.setShortcut("Ctrl+E")
        export_anki.triggered.connect(lambda: self.export_current("anki"))
        toolbar.addAction(export_anki)

        export_quizlet = QAction("Экспорт в Quizlet", self)
        export_quizlet.triggered.connect(lambda: self.export_current("quizlet"))
        toolbar.addAction(export_quizlet)

    def _build_content(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title = QLabel("Kindle Vocabulary Export")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Просмотр и экспорт слов из Vocabulary Builder")
        subtitle.setObjectName("mutedLabel")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        controls = QFrame()
        controls.setObjectName("controlBar")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        self.book_combo = QComboBox()
        self.book_combo.setEnabled(False)
        self.book_combo.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(QLabel("Книга"))
        controls_layout.addWidget(self.book_combo)

        self.count_label = QLabel("Записей: 0")
        self.count_label.setObjectName("mutedLabel")
        self.html_checkbox = QCheckBox("Подготовить HTML-поля для Anki")
        self.html_checkbox.setChecked(True)
        controls_layout.addWidget(self.count_label)
        controls_layout.addWidget(self.html_checkbox)
        layout.addWidget(controls)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Word", "Stem", "Context", "Book", "Looked up"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        self.export_button = QPushButton("Экспортировать выбранную книгу в Anki")
        self.export_button.setObjectName("primaryButton")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(lambda: self.export_current("anki"))
        layout.addWidget(self.export_button)

        self.setCentralWidget(root)

    def open_database(self) -> None:
        initial_dir = str(self.db_path.parent if self.db_path else Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть Kindle vocab.db",
            initial_dir,
            "Kindle Vocabulary Database (vocab.db *.db);;SQLite databases (*.db);;Все файлы (*)",
        )
        if not filename:
            return

        self.load_database(Path(filename))

    def load_database(self, path: Path) -> None:
        """Load a Kindle vocabulary database into the current window."""

        try:
            validate_vocab_db(path)
            books = list_books(path)
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось открыть базу", str(exc))
            return

        self.db_path = path
        self.book_combo.blockSignals(True)
        self.book_combo.clear()
        self.book_combo.addItem("Все книги", None)
        for book in books:
            label = book.title
            if book.authors:
                label += f" — {book.authors}"
            label += f" ({book.lookup_count})"
            self.book_combo.addItem(label, book.key)
        self.book_combo.blockSignals(False)
        self.book_combo.setEnabled(True)
        self.export_button.setEnabled(True)
        self.refresh_entries()
        self.statusBar().showMessage(f"Открыта база: {path}")

    def refresh_entries(self) -> None:
        if not self.db_path:
            return
        book_key = self.book_combo.currentData()
        self.entries = fetch_entries(self.db_path, book_key)
        self.count_label.setText(f"Записей: {len(self.entries)}")
        self.export_button.setText(
            "Экспортировать все записи в Anki"
            if book_key is None
            else "Экспортировать выбранную книгу в Anki"
        )
        self._fill_table()

    def _fill_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.entries))
        fields = ("word", "stem", "context", "book_title", "looked_up_at")
        for row_index, entry in enumerate(self.entries):
            for column_index, field in enumerate(fields):
                value = "" if entry.get(field) is None else str(entry[field])
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row_index, column_index, item)
        self.table.setSortingEnabled(True)

    def export_current(self, export_format: str) -> None:
        if not self.entries:
            QMessageBox.information(self, "Нет данных", "Сначала откройте vocab.db.")
            return

        default_name = f"kindle-{export_format}.tsv"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить экспорт",
            str(Path.home() / default_name),
            "TSV (*.tsv);;Все файлы (*)",
        )
        if not filename:
            return

        try:
            output = export_entries(
                self.entries,
                Path(filename),
                export_format,
                html_mode=self.html_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", str(exc))
            return

        self.statusBar().showMessage(f"Экспортировано {len(self.entries)} записей: {output}")
        QMessageBox.information(
            self,
            "Экспорт завершен",
            f"Сохранено записей: {len(self.entries)}\n{output}",
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Kindle Vocabulary Export")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
