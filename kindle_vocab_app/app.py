from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QSize,
    QStandardPaths,
    QThread,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kindle_vocab_app.kindle_db import export_entries, fetch_entries, list_books, validate_vocab_db
from kindle_vocab_app.kindle_device import find_kindle_source
from kindle_vocab_app.llm_enricher import (
    enrich_optimized_tsv,
    has_dslab_api_key,
)
from kindle_vocab_app.vocab_optimizer import optimize_entries


COLORS = {
    "window": "#0d0f14",
    "sidebar": "#12151c",
    "surface": "#171c24",
    "surface_hover": "#202735",
    "surface_active": "#263044",
    "border": "#2b3444",
    "border_strong": "#3c4658",
    "text": "#f3f5f8",
    "muted": "#a2abb9",
    "subtle": "#707b8c",
    "primary": "#76a2ff",
    "primary_hover": "#8db2ff",
    "primary_pressed": "#5f8ff0",
    "amber": "#f0bf5f",
    "mint": "#65d0aa",
    "success": "#55c59a",
}

ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def lucide_icon(name: str, color: str, size: int = 24) -> QIcon:
    svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


DARK_STYLESHEET = f"""
QWidget {{
    background: {COLORS['window']};
    color: {COLORS['text']};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow {{ background: {COLORS['window']}; }}
QFrame#sidebar {{
    background: #10141d;
    border-right: 1px solid {COLORS['border']};
}}
QFrame#sourcePanel, QFrame#metricPanel, QFrame#thoughtPanel {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
QFrame#thoughtBubble {{
    background: #202838;
    border: 1px solid #334057;
    border-radius: 8px;
}}
QFrame#thoughtBubble[phase="thinking"] {{
    background: #1d2739;
    border-color: #3b5276;
}}
QFrame#thoughtBubble[phase="answered"] {{
    background: #1c2b2a;
    border-color: #2f6a5a;
}}
QFrame#thoughtBubble[phase="failed"] {{
    background: #302128;
    border-color: #713f4e;
}}
QLabel#brandTitle {{ font-size: 18px; font-weight: 750; }}
QLabel#pageTitle {{ font-size: 28px; font-weight: 750; }}
QLabel#sectionLabel {{
    color: {COLORS['muted']};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0px;
}}
QLabel#mutedLabel {{ color: {COLORS['muted']}; }}
QLabel#subtleLabel {{ color: {COLORS['subtle']}; font-size: 12px; }}
QLabel#fileName {{ font-weight: 600; }}
QLabel#statusReady {{ color: {COLORS['success']}; font-size: 12px; }}
QLabel#metricValue {{ font-size: 18px; font-weight: 700; }}
QLabel#thoughtTitle {{ color: {COLORS['text']}; font-size: 13px; font-weight: 700; }}
QLabel#thoughtBody {{ color: #c6cfdd; font-size: 12px; line-height: 150%; }}
QLabel#thoughtMeta {{ color: {COLORS['subtle']}; font-size: 11px; }}
QLabel#pulseDot {{
    background: {COLORS['primary']};
    border-radius: 4px;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
}}
QLabel#countBadge {{
    background: #21314d;
    color: #c1d2ff;
    border: 1px solid #3b557f;
    border-radius: 8px;
    padding: 5px 10px;
    font-weight: 600;
}}
QPushButton {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 8px;
    min-height: 22px;
    padding: 10px 13px;
    text-align: left;
    font-weight: 600;
}}
QPushButton:hover {{ background: {COLORS['surface_hover']}; }}
QPushButton:pressed {{ background: {COLORS['surface_active']}; }}
QPushButton:disabled {{ color: #596272; border-color: #252b35; background: #141820; }}
QPushButton#primaryButton {{
    background: {COLORS['primary']};
    color: white;
    border-color: {COLORS['primary']};
}}
QPushButton#primaryButton:hover {{
    background: {COLORS['primary_hover']};
    border-color: {COLORS['primary_hover']};
}}
QPushButton#primaryButton:pressed {{ background: {COLORS['primary_pressed']}; }}
QLineEdit, QComboBox {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 10px 12px;
    min-height: 22px;
    selection-background-color: {COLORS['primary']};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: {COLORS['border_strong']}; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {COLORS['primary']}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: #596272; background: #141820; }}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border_strong']};
    selection-background-color: #294b89;
    padding: 4px;
    outline: 0;
}}
QTableWidget {{
    background: {COLORS['surface']};
    alternate-background-color: #151a22;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: #263f6d;
    selection-color: white;
    outline: 0;
}}
QTableWidget::item {{
    border-bottom: 1px solid #222b38;
    padding: 7px 9px;
}}
QHeaderView::section {{
    background: #1d2430;
    color: #aeb6c3;
    border: 0;
    border-bottom: 1px solid {COLORS['border']};
    padding: 11px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QCheckBox {{ color: {COLORS['muted']}; spacing: 9px; }}
QScrollArea#thoughtScroll {{
    background: transparent;
    border: 0;
}}
QScrollArea#thoughtScroll QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: #414c60; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: #556178; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: #3a4352; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def add_soft_shadow(widget: QWidget, blur: int = 26, y_offset: int = 10) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y_offset)
    shadow.setColor(QColor(0, 0, 0, 85))
    widget.setGraphicsEffect(shadow)


class ThinkingPulse(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.animations: list[QPropertyAnimation] = []

        for index in range(3):
            dot = QLabel()
            dot.setObjectName("pulseDot")
            effect = QGraphicsOpacityEffect(dot)
            effect.setOpacity(0.28)
            dot.setGraphicsEffect(effect)
            layout.addWidget(dot)

            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setStartValue(0.22)
            animation.setKeyValueAt(0.5, 1.0)
            animation.setEndValue(0.22)
            animation.setDuration(1050)
            animation.setLoopCount(-1)
            animation.setEasingCurve(QEasingCurve.Type.InOutSine)
            QTimer.singleShot(index * 160, animation.start)
            self.animations.append(animation)


class ThoughtStream(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("thoughtPanel")
        self.setMinimumHeight(164)
        self.setMaximumHeight(220)
        add_soft_shadow(self, blur=24, y_offset=8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("AI-процесс")
        title.setObjectName("thoughtTitle")
        self.status_label = QLabel("Готов к обработке")
        self.status_label.setObjectName("thoughtMeta")
        self.pulse = ThinkingPulse()
        self.pulse.setVisible(False)
        header.addWidget(title)
        header.addWidget(self.status_label)
        header.addStretch()
        header.addWidget(self.pulse)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("thoughtScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_body = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_body)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_body)
        layout.addWidget(self.scroll, 1)

        self.add_system_message("Локальная статистика готовит кандидатов, AI заполнит смысл и контекст.")

    def start(self) -> None:
        self.pulse.setVisible(True)
        self.status_label.setText("Думает")
        self.clear()
        self.add_system_message("Запускаю анализ слов и подготовку карточек.")

    def finish(self, text: str) -> None:
        self.pulse.setVisible(False)
        self.status_label.setText("Готово")
        self.add_system_message(text)

    def fail(self, text: str) -> None:
        self.pulse.setVisible(False)
        self.status_label.setText("Нужна проверка")
        self.add_event({"phase": "failed", "word": "Ошибка", "message": text})

    def clear(self) -> None:
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def add_system_message(self, text: str) -> None:
        self.add_event({"phase": "thinking", "word": "Kindle Cards", "message": text})

    def add_event(self, event: dict[str, object]) -> None:
        phase = str(event.get("phase") or "thinking")
        word = str(event.get("word") or event.get("base_form") or "AI")
        score = event.get("score")
        if phase == "thinking":
            body = str(event.get("message") or "Подбираю смысл по статистике и контексту.")
            meta = "ожидание ответа модели"
        elif phase == "answered":
            reasoning = str(event.get("reasoning") or "").strip()
            answer = str(event.get("answer") or "").strip()
            body = reasoning or answer or "Карточка заполнена."
            meta = f"важность {score}/10" if score != "" else "ответ модели"
        else:
            body = str(event.get("message") or "Не удалось заполнить это слово.")
            meta = "ошибка обработки"

        bubble = self._bubble(word=word, body=_shorten(body, 360), meta=meta, phase=phase)
        self.scroll_layout.insertWidget(max(0, self.scroll_layout.count() - 1), bubble)
        self._fade_in(bubble)
        QTimer.singleShot(30, self._scroll_to_bottom)

    def _bubble(self, *, word: str, body: str, meta: str, phase: str) -> QFrame:
        bubble = QFrame()
        bubble.setObjectName("thoughtBubble")
        bubble.setProperty("phase", phase)
        bubble.style().unpolish(bubble)
        bubble.style().polish(bubble)
        layout = QVBoxLayout(bubble)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(4)

        title = QLabel(word)
        title.setObjectName("thoughtTitle")
        title.setWordWrap(True)
        text = QLabel(body)
        text.setObjectName("thoughtBody")
        text.setWordWrap(True)
        caption = QLabel(meta)
        caption.setObjectName("thoughtMeta")
        caption.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(text)
        layout.addWidget(caption)
        return bubble

    def _fade_in(self, widget: QWidget) -> None:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setDuration(280)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())


class OptimizationWorker(QObject):
    progress = Signal(object)
    finished = Signal(object, str)
    failed = Signal(str)

    def __init__(self, entries: list[dict[str, object]], output_dir: Path, snapshot_path: Path) -> None:
        super().__init__()
        self.entries = entries
        self.output_dir = output_dir
        self.snapshot_path = snapshot_path

    def run(self) -> None:
        try:
            result = optimize_entries(self.entries, self.output_dir, self.snapshot_path)
            llm_summary = ""
            if has_dslab_api_key():
                try:
                    enrichment = enrich_optimized_tsv(
                        result.tsv_path,
                        analysis_dir=result.analysis_dir,
                        progress_callback=self.progress.emit,
                    )
                    llm_summary = (
                        f"\nAI заполнено: {enrichment.processed}, "
                        f"пропущено: {enrichment.skipped}, ошибок: {enrichment.failed}"
                    )
                except Exception as exc:
                    llm_summary = f"\nAI заполнение пропущено: {exc}"
                    self.progress.emit(
                        {
                            "phase": "failed",
                            "word": "AI",
                            "message": str(exc),
                        }
                    )
            else:
                self.progress.emit(
                    {
                        "phase": "thinking",
                        "word": "AI",
                        "message": "Ключ DS Lab не найден, поэтому заполнение моделью пропущено.",
                    }
                )
            self.finished.emit(result, llm_summary)
        except Exception as exc:
            self.failed.emit(str(exc))


def _shorten(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.db_path: Path | None = None
        self.entries: list[dict[str, object]] = []
        self.filtered_entries: list[dict[str, object]] = []
        self.book_count = 0
        self.device_signature: tuple[str, ...] | None = None
        self.optimization_thread: QThread | None = None
        self.optimization_worker: OptimizationWorker | None = None

        self.setWindowTitle("Kindle Cards")
        self.setWindowIcon(lucide_icon("book-open", COLORS["primary"], 32))
        self.resize(1280, 800)
        self.setMinimumSize(960, 620)
        self._build_shortcuts()
        self._build_content()
        self.device_timer = QTimer(self)
        self.device_timer.setInterval(3000)
        self.device_timer.timeout.connect(self.scan_for_kindle)
        self.device_timer.start()
        QTimer.singleShot(150, self.scan_for_kindle)

    def _build_shortcuts(self) -> None:
        open_action = QAction(self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_database)
        self.addAction(open_action)

        export_action = QAction(self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(lambda: self.export_current("anki"))
        self.addAction(export_action)

        search_action = QAction(self)
        search_action.setShortcut("Ctrl+F")
        search_action.triggered.connect(lambda: self.search_input.setFocus())
        self.addAction(search_action)

    def _build_content(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())
        root_layout.addWidget(self._build_main_area(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(284)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(16)

        brand_row = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(lucide_icon("book-open", COLORS["primary"], 26).pixmap(26, 26))
        brand_title = QLabel("Kindle Cards")
        brand_title.setObjectName("brandTitle")
        brand_row.addWidget(brand_icon)
        brand_row.addSpacing(4)
        brand_row.addWidget(brand_title)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        tagline = QLabel("Слова из Vocabulary Builder\nв удобном формате")
        tagline.setObjectName("mutedLabel")
        tagline.setWordWrap(True)
        layout.addWidget(tagline)
        layout.addSpacing(8)

        layout.addWidget(self._section_label("ИСТОЧНИК"))
        source_panel = QFrame()
        source_panel.setObjectName("sourcePanel")
        add_soft_shadow(source_panel, blur=18, y_offset=6)
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(13, 12, 13, 12)
        source_layout.setSpacing(5)
        self.file_name_label = QLabel("Ищем Kindle")
        self.file_name_label.setObjectName("fileName")
        self.file_name_label.setWordWrap(True)
        self.file_status_label = QLabel("Подключите устройство по USB")
        self.file_status_label.setObjectName("subtleLabel")
        self.file_status_label.setWordWrap(True)
        source_layout.addWidget(self.file_name_label)
        source_layout.addWidget(self.file_status_label)
        layout.addWidget(source_panel)

        self.open_button = QPushButton("  Проверить подключение")
        self.open_button.setObjectName("primaryButton")
        self.open_button.setIcon(lucide_icon("refresh-cw", "#ffffff", 18))
        self.open_button.setIconSize(QSize(17, 17))
        self.open_button.setToolTip("Найти подключенный Kindle и обновить базу")
        self.open_button.clicked.connect(lambda: self.scan_for_kindle(force=True))
        layout.addWidget(self.open_button)

        self.manual_button = QPushButton("  Выбрать файл вручную")
        self.manual_button.setIcon(lucide_icon("folder-open", COLORS["muted"], 17))
        self.manual_button.setIconSize(QSize(16, 16))
        self.manual_button.setToolTip("Открыть vocab.db вручную (Ctrl+O)")
        self.manual_button.clicked.connect(self.open_database)
        layout.addWidget(self.manual_button)

        layout.addSpacing(10)
        layout.addWidget(self._section_label("ЭКСПОРТ"))

        self.anki_button = QPushButton("  Anki TSV")
        self.anki_button.setIcon(lucide_icon("layers", "#a9c2ff", 18))
        self.anki_button.setIconSize(QSize(17, 17))
        self.anki_button.setEnabled(False)
        self.anki_button.setToolTip("Экспортировать текущую выборку в Anki (Ctrl+E)")
        self.anki_button.clicked.connect(lambda: self.export_current("anki"))
        layout.addWidget(self.anki_button)

        self.quizlet_button = QPushButton("  Quizlet TSV")
        self.quizlet_button.setIcon(lucide_icon("file-down", "#8ddbbd", 18))
        self.quizlet_button.setIconSize(QSize(17, 17))
        self.quizlet_button.setEnabled(False)
        self.quizlet_button.clicked.connect(lambda: self.export_current("quizlet"))
        layout.addWidget(self.quizlet_button)

        self.html_checkbox = QCheckBox("HTML-поля для Anki")
        self.html_checkbox.setChecked(True)
        self.html_checkbox.setToolTip("Экранировать HTML в текстовых полях Anki")
        layout.addWidget(self.html_checkbox)

        self.export_hint = QLabel("Экспортируется текущая выборка")
        self.export_hint.setObjectName("subtleLabel")
        self.export_hint.setWordWrap(True)
        layout.addWidget(self.export_hint)

        layout.addSpacing(10)
        layout.addWidget(self._section_label("ОБРАБОТКА"))

        self.optimize_button = QPushButton("  Обработать новые")
        self.optimize_button.setIcon(lucide_icon("sparkles", "#f4c86a", 18))
        self.optimize_button.setIconSize(QSize(17, 17))
        self.optimize_button.setEnabled(False)
        self.optimize_button.setToolTip("Создать optimized.tsv и JSON-аудит только для новых слов")
        self.optimize_button.clicked.connect(self.optimize_current)
        layout.addWidget(self.optimize_button)

        self.optimize_hint = QLabel("Слепок обработанных слов хранится локально")
        self.optimize_hint.setObjectName("subtleLabel")
        self.optimize_hint.setWordWrap(True)
        layout.addWidget(self.optimize_hint)
        layout.addStretch()

        location_hint = QLabel("Kindle/system/vocabulary/vocab.db")
        location_hint.setObjectName("subtleLabel")
        location_hint.setWordWrap(True)
        layout.addWidget(location_hint)
        return sidebar

    def _build_main_area(self) -> QWidget:
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        heading_row = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Словарь")
        title.setObjectName("pageTitle")
        self.scope_label = QLabel("Откройте базу Kindle, чтобы увидеть сохраненные слова")
        self.scope_label.setObjectName("mutedLabel")
        heading.addWidget(title)
        heading.addWidget(self.scope_label)
        heading_row.addLayout(heading)
        heading_row.addStretch()
        self.count_badge = QLabel("0 слов")
        self.count_badge.setObjectName("countBadge")
        heading_row.addWidget(self.count_badge, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(heading_row)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(10)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по слову, контексту или книге")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setEnabled(False)
        self.search_input.addAction(
            lucide_icon("search", COLORS["subtle"], 17),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search_input.textChanged.connect(self.apply_search)
        filters_row.addWidget(self.search_input, 3)

        self.book_combo = QComboBox()
        self.book_combo.setMinimumWidth(300)
        self.book_combo.setEnabled(False)
        self.book_combo.currentIndexChanged.connect(self.refresh_entries)
        filters_row.addWidget(self.book_combo, 2)
        layout.addLayout(filters_row)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(10)
        self.words_metric = self._metric_panel("СЛОВ В ВЫБОРКЕ", "0", "languages")
        self.books_metric = self._metric_panel("КНИГ В БАЗЕ", "0", "book")
        metrics_row.addWidget(self.words_metric[0])
        metrics_row.addWidget(self.books_metric[0])
        metrics_row.addStretch(2)
        layout.addLayout(metrics_row)

        self.thought_stream = ThoughtStream()
        layout.addWidget(self.thought_stream)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_empty_state())
        self.content_stack.addWidget(self._build_table())
        layout.addWidget(self.content_stack, 1)
        return main

    def _build_empty_state(self) -> QWidget:
        empty = QFrame()
        empty.setObjectName("sourcePanel")
        layout = QVBoxLayout(empty)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setPixmap(lucide_icon("book-marked", "#485365", 56).pixmap(56, 56))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Здесь появятся сохраненные слова")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel("Откройте vocab.db через кнопку слева.\nФайл обычно находится в скрытой папке system на Kindle.")
        text.setObjectName("mutedLabel")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addWidget(text)
        return empty

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["WORD", "STEM", "CONTEXT", "BOOK", "LOOKED UP"])
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSortingEnabled(True)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(0, 150)
        table.setColumnWidth(1, 130)
        table.setColumnWidth(3, 210)
        table.setColumnWidth(4, 100)
        self.table = table
        return table

    def _metric_panel(self, caption: str, value: str, icon_name: str) -> tuple[QFrame, QLabel]:
        panel = QFrame()
        panel.setObjectName("metricPanel")
        panel.setMinimumWidth(180)
        add_soft_shadow(panel, blur=18, y_offset=6)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(13, 10, 13, 10)
        icon = QLabel()
        icon.setPixmap(lucide_icon(icon_name, COLORS["primary"], 20).pixmap(20, 20))
        labels = QVBoxLayout()
        labels.setSpacing(1)
        caption_label = QLabel(caption)
        caption_label.setObjectName("sectionLabel")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        labels.addWidget(caption_label)
        labels.addWidget(value_label)
        layout.addWidget(icon)
        layout.addLayout(labels)
        layout.addStretch()
        return panel, value_label

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def open_database(self) -> None:
        initial_dir = str(self.db_path.parent if self.db_path else Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Открыть Kindle vocab.db",
            initial_dir,
            "Kindle Vocabulary Database (vocab.db *.db);;SQLite databases (*.db);;Все файлы (*)",
        )
        if filename:
            self.load_database(Path(filename), source_label="Локальный файл", automatic=False)

    def scan_for_kindle(self, force: bool = False) -> None:
        source = find_kindle_source()
        if source is None:
            if self.db_path is None:
                self.file_name_label.setText("Kindle не найден")
                self.file_status_label.setText("Подключите устройство по USB")
            elif force:
                self.file_status_label.setText("Kindle не найден · используется локальная копия")
            return

        if not force and source.signature == self.device_signature:
            return

        self.file_name_label.setText("Kindle обнаружен")
        self.file_status_label.setText("Загружаем Vocabulary Builder…")
        QApplication.processEvents()

        try:
            cached_path = source.copy_to_cache(self._cache_dir())
            validate_vocab_db(cached_path)
        except Exception as exc:
            self.file_name_label.setText("Не удалось прочитать Kindle")
            self.file_status_label.setText(str(exc))
            return

        self.device_signature = source.signature
        self.load_database(
            cached_path,
            source_label=source.label,
            automatic=True,
        )

    @staticmethod
    def _cache_dir() -> Path:
        return MainWindow._app_data_dir() / "cache"

    @staticmethod
    def _processing_dir() -> Path:
        return MainWindow._app_data_dir() / "optimized"

    @staticmethod
    def _snapshot_path() -> Path:
        return MainWindow._app_data_dir() / "processed_snapshot.json"

    @staticmethod
    def _app_data_dir() -> Path:
        app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        return Path(app_data)

    def load_database(
        self,
        path: Path,
        source_label: str | None = None,
        *,
        automatic: bool = False,
    ) -> None:
        try:
            validate_vocab_db(path)
            books = list_books(path)
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось открыть базу", str(exc))
            return

        self.db_path = path
        self.book_count = len(books)
        self.book_combo.blockSignals(True)
        self.book_combo.clear()
        self.book_combo.addItem("Все книги", None)
        for book in books:
            label = book.title
            if book.authors:
                label += f" — {book.authors}"
            label += f"  ·  {book.lookup_count}"
            self.book_combo.addItem(label, book.key)
        self.book_combo.blockSignals(False)

        self.file_name_label.setText(source_label or path.name)
        self.file_name_label.setToolTip(str(path))
        self.file_status_label.setText(
            "Словарь загружен автоматически" if automatic else "База готова к работе"
        )
        self.file_status_label.setObjectName("statusReady")
        self.file_status_label.style().unpolish(self.file_status_label)
        self.file_status_label.style().polish(self.file_status_label)
        self.book_combo.setEnabled(True)
        self.search_input.setEnabled(True)
        self.anki_button.setEnabled(True)
        self.quizlet_button.setEnabled(True)
        self.optimize_button.setEnabled(True)
        self.books_metric[1].setText(str(self.book_count))
        self.search_input.clear()
        self.refresh_entries()

    def refresh_entries(self) -> None:
        if not self.db_path:
            return
        book_key = self.book_combo.currentData()
        self.entries = fetch_entries(self.db_path, book_key)
        self.scope_label.setText(self.book_combo.currentText())
        self.apply_search()

    def apply_search(self) -> None:
        query = self.search_input.text().strip().casefold()
        if not query:
            self.filtered_entries = list(self.entries)
        else:
            fields = ("word", "stem", "context", "book_title", "authors")
            self.filtered_entries = [
                entry
                for entry in self.entries
                if any(query in str(entry.get(field) or "").casefold() for field in fields)
            ]

        count = len(self.filtered_entries)
        self.count_badge.setText(f"{count} слов")
        self.words_metric[1].setText(str(count))
        self.export_hint.setText(f"Будет экспортировано: {count}")
        self.anki_button.setEnabled(count > 0)
        self.quizlet_button.setEnabled(count > 0)
        self.optimize_button.setEnabled(count > 0)
        self._fill_table()

    def _fill_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.filtered_entries))
        fields = ("word", "stem", "context", "book_title", "looked_up_at")
        for row_index, entry in enumerate(self.filtered_entries):
            for column_index, field in enumerate(fields):
                value = "" if entry.get(field) is None else str(entry[field])
                if field == "looked_up_at" and "T" in value:
                    value = value.split("T", maxsplit=1)[0]
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if field in {"stem", "book_title", "looked_up_at"}:
                    item.setForeground(QColor(COLORS["muted"]))
                self.table.setItem(row_index, column_index, item)
        self.table.setSortingEnabled(True)
        self.content_stack.setCurrentIndex(1 if self.db_path else 0)

    def export_current(self, export_format: str) -> None:
        if not self.filtered_entries:
            QMessageBox.information(self, "Нет данных", "В текущей выборке нет записей.")
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
                self.filtered_entries,
                Path(filename),
                export_format,
                html_mode=self.html_checkbox.isChecked(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", str(exc))
            return

        self.file_status_label.setText(f"Сохранено {len(self.filtered_entries)} записей")
        self.file_status_label.setToolTip(str(output))

    def optimize_current(self) -> None:
        if not self.filtered_entries:
            QMessageBox.information(self, "Нет данных", "В текущей выборке нет записей.")
            return

        if self.optimization_thread is not None:
            return

        self.thought_stream.start()
        self.file_status_label.setText("Обработка слов...")
        self.optimize_hint.setText("Локальная статистика и AI готовят карточки")
        self._set_processing_enabled(False)

        self.optimization_thread = QThread(self)
        self.optimization_worker = OptimizationWorker(
            list(self.filtered_entries),
            self._processing_dir(),
            self._snapshot_path(),
        )
        self.optimization_worker.moveToThread(self.optimization_thread)
        self.optimization_thread.started.connect(self.optimization_worker.run)
        self.optimization_worker.progress.connect(self._on_optimization_progress)
        self.optimization_worker.finished.connect(self._on_optimization_finished)
        self.optimization_worker.failed.connect(self._on_optimization_failed)
        self.optimization_worker.finished.connect(self.optimization_thread.quit)
        self.optimization_worker.failed.connect(self.optimization_thread.quit)
        self.optimization_thread.finished.connect(self.optimization_worker.deleteLater)
        self.optimization_thread.finished.connect(self.optimization_thread.deleteLater)
        self.optimization_thread.finished.connect(self._clear_optimization_worker)
        self.optimization_thread.start()

    def _on_optimization_progress(self, event: object) -> None:
        if isinstance(event, dict):
            self.thought_stream.add_event(event)

    def _on_optimization_finished(self, result: object, llm_summary: str) -> None:
        processed_new = getattr(result, "processed_new", 0)
        accepted_new = getattr(result, "accepted_new", 0)
        rejected_new = getattr(result, "rejected_new", 0)
        skipped_existing = getattr(result, "skipped_existing", 0)
        tsv_path = getattr(result, "tsv_path", "")
        analysis_dir = getattr(result, "analysis_dir", "")

        summary_text = str(llm_summary or "")

        self.optimize_hint.setText(
            f"Новых: {processed_new}, в TSV: {accepted_new}, "
            f"пропущено: {skipped_existing}{summary_text}"
        )
        self.file_status_label.setText(f"Оптимизировано новых слов: {accepted_new}")
        self.file_status_label.setToolTip(str(tsv_path))
        self.thought_stream.finish(f"Готово: {accepted_new} слов добавлено в TSV.")
        self._set_processing_enabled(True)
        QMessageBox.information(
            self,
            "Обработка завершена",
            "\n".join(
                line
                for line in [
                    f"Новых слов обработано: {processed_new}",
                    f"Добавлено в TSV: {accepted_new}",
                    f"Отклонено фильтрами: {rejected_new}",
                    f"Уже были в слепке: {skipped_existing}",
                    summary_text.strip(),
                    f"TSV: {tsv_path}",
                    f"JSON: {analysis_dir}",
                ]
                if line
            ),
        )

    def _on_optimization_failed(self, message: str) -> None:
        self._set_processing_enabled(True)
        self.thought_stream.fail(message)
        QMessageBox.critical(self, "Ошибка обработки", message)

    def _set_processing_enabled(self, enabled: bool) -> None:
        has_entries = bool(self.filtered_entries)
        self.open_button.setEnabled(enabled)
        self.manual_button.setEnabled(enabled)
        self.anki_button.setEnabled(enabled and has_entries)
        self.quizlet_button.setEnabled(enabled and has_entries)
        self.optimize_button.setEnabled(enabled and has_entries)
        self.search_input.setEnabled(enabled and bool(self.db_path))
        self.book_combo.setEnabled(enabled and bool(self.db_path))

    def _clear_optimization_worker(self) -> None:
        self.optimization_thread = None
        self.optimization_worker = None


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLORS["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#151920"))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLORS["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return palette


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Kindle Cards")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable Text", 10))
    app.setPalette(_dark_palette())
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
