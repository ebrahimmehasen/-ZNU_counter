"""Phase 1 main window.

Everything the employee needs is on one screen: current/next number,
today's count, printer + sync status, the print button, and a plain
log so problems are visible without opening a file. See module
docstrings in core/ticket_service.py and printing/printer_service.py
for the reliability logic this window drives.
"""
from __future__ import annotations

import logging
from datetime import date

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig
from app.core.database import Database
from app.core.models import TicketStatus
from app.core.session_service import SessionService
from app.core.ticket_service import TicketService
from app.logging_config import get_logger
from app.printing import printer_service, ticket_image
from app.printing.printer_service import PrintError
from app.printing.ticket_image import TicketImageError
from app.sync.supabase_client import SupabaseSyncClient
from app.sync.sync_manager import SyncManager
from app.ui.styles import STYLESHEET

logger = get_logger("ui")


class _QtLogBridge(QObject):
    message = Signal(str)


class _QtLogHandler(logging.Handler):
    """Mirrors the standard logger into the on-screen log panel."""

    def __init__(self, bridge: _QtLogBridge):
        super().__init__()
        self.bridge = bridge
        self.setFormatter(logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.bridge.message.emit(self.format(record))
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle("University Admission Queue — Ticket Printer")
        self.resize(560, 780)
        self.setStyleSheet(STYLESHEET)

        # Build the UI first: log messages emitted below must have a
        # log_panel to land in, and status labels to update.
        self._build_ui()

        self._log_bridge = _QtLogBridge()
        self._log_bridge.message.connect(self._append_log)
        logging.getLogger("queue_system").addHandler(_QtLogHandler(self._log_bridge))

        db_path = config.resolve_path(config.database.path)
        self.db = Database(db_path)
        self.session_service = SessionService(self.db)
        self.ticket_service = TicketService(self.db)
        self.supabase_client = SupabaseSyncClient(config.supabase)

        self.session = self.session_service.get_or_create_today()
        logger.info("Business session ready: %s (id=%s)", self.session.business_date, self.session.id)

        self.sync_manager = None
        if config.sync.enabled:
            self.sync_manager = SyncManager(
                self.ticket_service,
                self.session_service,
                self.supabase_client,
                interval_seconds=config.sync.interval_seconds,
                batch_size=config.sync.batch_size,
            )
            self.sync_manager.status_changed.connect(self._on_sync_status)
            self.sync_manager.start()
        else:
            self.sync_status_label.setText("SYNC DISABLED")
            self.sync_status_label.setObjectName("statusPending")

        self._date_check_timer = QTimer(self)
        self._date_check_timer.timeout.connect(self._check_day_rollover)
        self._date_check_timer.start(30_000)

        self._refresh_all()

    # ---- UI construction ------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("UNIVERSITY QUEUE")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.date_label)

        # Warning banner for an unresolved (failed/crashed) ticket
        self.warning_frame = QFrame()
        self.warning_frame.setObjectName("warningBanner")
        wl = QVBoxLayout(self.warning_frame)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        wl.addWidget(self.warning_label)
        wrow = QHBoxLayout()
        self.retry_button = QPushButton("RETRY PRINT")
        self.retry_button.setObjectName("retryButton")
        self.retry_button.clicked.connect(self._on_retry_clicked)
        self.cancel_button = QPushButton("Cancel this number")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        wrow.addWidget(self.retry_button)
        wrow.addWidget(self.cancel_button)
        wl.addLayout(wrow)
        layout.addWidget(self.warning_frame)
        self.warning_frame.hide()

        # Current number card
        current_card = self._card()
        cc_layout = QVBoxLayout(current_card)
        cc_label = QLabel("CURRENT NUMBER")
        cc_label.setObjectName("sectionLabel")
        cc_label.setAlignment(Qt.AlignCenter)
        self.current_number_label = QLabel("—")
        self.current_number_label.setObjectName("bigNumber")
        self.current_number_label.setAlignment(Qt.AlignCenter)
        cc_layout.addWidget(cc_label)
        cc_layout.addWidget(self.current_number_label)
        layout.addWidget(current_card)

        # Next number card
        next_card = self._card()
        nc_layout = QVBoxLayout(next_card)
        nc_label = QLabel("NEXT NUMBER")
        nc_label.setObjectName("sectionLabel")
        nc_label.setAlignment(Qt.AlignCenter)
        self.next_number_label = QLabel("—")
        self.next_number_label.setObjectName("nextNumber")
        self.next_number_label.setAlignment(Qt.AlignCenter)
        nc_layout.addWidget(nc_label)
        nc_layout.addWidget(self.next_number_label)
        layout.addWidget(next_card)

        # Stats row: today's count / last printed
        stats_row = QHBoxLayout()
        stats_row.addWidget(self._stat_block("TODAY'S COUNT", "today_count_label"))
        stats_row.addWidget(self._stat_block("LAST PRINTED", "last_printed_label"))
        layout.addLayout(stats_row)

        # Printer + sync status row
        status_card = self._card()
        sc_layout = QVBoxLayout(status_card)
        self.printer_name_label = QLabel()
        sc_layout.addWidget(self.printer_name_label)
        self.printer_status_label = QLabel()
        sc_layout.addWidget(self.printer_status_label)
        self.sync_status_label = QLabel("SYNC: —")
        sc_layout.addWidget(self.sync_status_label)
        layout.addWidget(status_card)

        # Print button
        self.print_button = QPushButton("PRINT NEXT TICKET")
        self.print_button.setObjectName("printButton")
        self.print_button.clicked.connect(self._on_print_clicked)
        layout.addWidget(self.print_button)

        # Error banner
        self.error_label = QLabel("")
        self.error_label.setObjectName("statusError")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # Log panel
        log_label = QLabel("ACTIVITY LOG")
        log_label.setObjectName("sectionLabel")
        layout.addWidget(log_label)
        self.log_panel = QTextEdit()
        self.log_panel.setObjectName("logPanel")
        self.log_panel.setReadOnly(True)
        self.log_panel.setFixedHeight(140)
        layout.addWidget(self.log_panel)

        self.setCentralWidget(root)

    def _card(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        return f

    def _stat_block(self, title: str, attr_name: str) -> QFrame:
        card = self._card()
        v = QVBoxLayout(card)
        t = QLabel(title)
        t.setObjectName("sectionLabel")
        t.setAlignment(Qt.AlignCenter)
        val = QLabel("—")
        val.setObjectName("statValue")
        val.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        v.addWidget(val)
        setattr(self, attr_name, val)
        return card

    # ---- refresh / state -------------------------------------------------

    def _refresh_all(self) -> None:
        self.date_label.setText(f"Business date: {self.session.business_date}")

        stats = self.ticket_service.get_today_stats(self.session.id)
        self.current_number_label.setText(
            str(stats["current_number"]) if stats["current_number"] else "—"
        )
        self.next_number_label.setText(str(stats["next_number"]))
        self.today_count_label.setText(str(stats["today_count"]))
        self.last_printed_label.setText(
            str(stats["current_number"]) if stats["current_number"] else "—"
        )

        printer_name = self.config.printer.name or (printer_service.get_default_printer() or "")
        self.printer_name_label.setText(f"Printer: {printer_name or 'Not configured'}")
        available = printer_service.printer_is_available(self.config.printer.name)
        if available:
            self.printer_status_label.setText("PRINTER STATUS: READY")
            self.printer_status_label.setObjectName("statusReady")
        else:
            self.printer_status_label.setText("PRINTER STATUS: NOT FOUND")
            self.printer_status_label.setObjectName("statusError")
        self.printer_status_label.setStyleSheet("")  # force re-polish
        self.printer_status_label.style().unpolish(self.printer_status_label)
        self.printer_status_label.style().polish(self.printer_status_label)

        unresolved = self.ticket_service.get_unresolved_ticket(self.session.id)
        if unresolved:
            self.warning_frame.show()
            if unresolved.status == TicketStatus.RESERVED:
                self.warning_label.setText(
                    f"Ticket #{unresolved.ticket_number} was reserved but never confirmed "
                    "printed (likely an app/computer restart mid-print). Retry it before "
                    "printing a new number."
                )
            else:
                self.warning_label.setText(
                    f"Ticket #{unresolved.ticket_number} failed to print: "
                    f"{unresolved.error_message or 'unknown error'}"
                )
            self.retry_button.setText(f"RETRY PRINT #{unresolved.ticket_number}")
            self.print_button.setEnabled(False)
        else:
            self.warning_frame.hide()
            self.print_button.setEnabled(True)

    def _append_log(self, line: str) -> None:
        self.log_panel.append(line)

    def _check_day_rollover(self) -> None:
        if self.session.business_date != date.today().isoformat():
            self.session = self.session_service.get_or_create_today()
            logger.info("New business day started: %s", self.session.business_date)
            self._refresh_all()

    # ---- printing workflow -------------------------------------------------

    def _on_print_clicked(self) -> None:
        self.error_label.setText("")
        self.print_button.setEnabled(False)
        try:
            ticket = self.ticket_service.reserve_next_ticket(self.session.id)
            logger.info("Reserved ticket #%s", ticket.ticket_number)
            self._refresh_all()
            self._do_print(ticket)
        finally:
            self._refresh_all()

    def _on_retry_clicked(self) -> None:
        unresolved = self.ticket_service.get_unresolved_ticket(self.session.id)
        if not unresolved:
            self._refresh_all()
            return
        self.error_label.setText("")
        self._do_print(unresolved)
        self._refresh_all()

    def _on_cancel_clicked(self) -> None:
        unresolved = self.ticket_service.get_unresolved_ticket(self.session.id)
        if not unresolved:
            return
        confirm = QMessageBox.question(
            self,
            "Cancel ticket number",
            f"Cancel ticket #{unresolved.ticket_number}? Its number will NOT be reused — "
            "the next print will skip ahead. This should only be used when the ticket "
            "truly cannot be printed.",
        )
        if confirm == QMessageBox.Yes:
            self.ticket_service.cancel_ticket(unresolved.id, "Cancelled by employee")
            logger.warning("Ticket #%s cancelled by employee", unresolved.ticket_number)
            self._refresh_all()

    def _do_print(self, ticket) -> None:
        temp_dir = self.config.resolve_path("data/temp")
        template_path = self.config.resolve_path(self.config.template.path)
        composited_path = None
        try:
            composited_path = ticket_image.render_ticket_image(
                template_path,
                ticket.ticket_number,
                temp_dir,
                self.config.template.number_padding,
            )
            printer_service.print_image(
                composited_path,
                self.config.printer.name,
                self.config.printer.copies,
            )
            self.ticket_service.mark_printed(ticket.id, self.config.printer.name or "default")
            logger.info("Ticket #%s printed successfully", ticket.ticket_number)
        except (TicketImageError, PrintError) as e:
            self.ticket_service.mark_print_failed(ticket.id, str(e))
            logger.error("Ticket #%s failed to print: %s", ticket.ticket_number, e)
            self.error_label.setText(f"Print failed: {e}")
        except Exception as e:  # unexpected — still must not silently claim success
            self.ticket_service.mark_print_failed(ticket.id, f"Unexpected error: {e}")
            logger.exception("Unexpected error printing ticket #%s", ticket.ticket_number)
            self.error_label.setText(f"Unexpected error: {e}")
        finally:
            if composited_path is not None:
                ticket_image.cleanup(composited_path)

    # ---- sync status ------------------------------------------------------

    def _on_sync_status(self, status: dict) -> None:
        pending = status["pending"]
        if status["online"] and pending == 0:
            self.sync_status_label.setText("SYNC: All tickets synced")
            self.sync_status_label.setObjectName("statusReady")
        elif status["online"]:
            self.sync_status_label.setText(f"SYNC: {pending} pending")
            self.sync_status_label.setObjectName("statusPending")
        else:
            self.sync_status_label.setText(
                f"SYNC: OFFLINE — {pending} pending ({status.get('last_error') or 'no connection'})"
            )
            self.sync_status_label.setObjectName("statusError")
        self.sync_status_label.style().unpolish(self.sync_status_label)
        self.sync_status_label.style().polish(self.sync_status_label)

    # ---- lifecycle ----------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self.sync_manager is not None:
            self.sync_manager.stop()
            self.sync_manager.wait(3000)
        self.db.close()
        super().closeEvent(event)
