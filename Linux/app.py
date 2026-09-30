import sys
import threading
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.audio_processor_v4 import AudioProcessorV4


class ProcessingWorker(QObject):
    progress = Signal(int)
    finished = Signal(str)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, input_file, output_file):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    @Slot()
    def run(self):
        try:
            processor = AudioProcessorV4(self.input_file)
            processor.process(
                self.output_file,
                progress_callback=self.progress.emit,
                cancel_event=self.cancel_event,
            )

            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.finished.emit(self.output_file)

        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error.emit(str(exc))


class NoiseFreeWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NoiseFree")
        self.setMinimumSize(680, 620)
        self.resize(760, 680)

        self.selected_file = None
        self.cleaned_file = None
        self.thread = None
        self.worker = None

        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #101216;
            }

            QWidget {
                color: #E8EAED;
                font-family: "Noto Sans", "Ubuntu", sans-serif;
                font-size: 14px;
            }

            QFrame#card {
                background: #191C22;
                border: 1px solid #2B3038;
                border-radius: 14px;
            }

            QLabel#title {
                font-size: 32px;
                font-weight: 700;
                color: #FFFFFF;
            }

            QLabel#subtitle {
                font-size: 14px;
                color: #9AA3AF;
            }

            QLabel#section {
                font-size: 16px;
                font-weight: 600;
                color: #FFFFFF;
            }

            QLabel#fileName {
                font-size: 16px;
                font-weight: 600;
                color: #FFFFFF;
            }

            QLabel#fileInfo {
                color: #9AA3AF;
                line-height: 1.4;
            }

            QLabel#status {
                color: #B8C0CC;
            }

            QPushButton {
                min-height: 42px;
                padding: 0 18px;
                border-radius: 9px;
                border: 1px solid #353B45;
                background: #242932;
                color: #FFFFFF;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #2D333D;
            }

            QPushButton:pressed {
                background: #1D2128;
            }

            QPushButton:disabled {
                background: #1A1D22;
                color: #606874;
                border-color: #272B32;
            }

            QPushButton#primary {
                background: #FF8C00;
                border-color: #FF8C00;
            }

            QPushButton#primary:hover {
                background: #FFA333;
            }

            QPushButton#cancel {
                background: #2A2022;
                border-color: #5A3035;
                color: #FF9A9A;
            }

            QPushButton#cancel:hover {
                background: #382529;
            }

            QProgressBar {
                min-height: 16px;
                max-height: 16px;
                border: none;
                border-radius: 8px;
                background: #292E36;
                text-align: center;
            }

            QProgressBar::chunk {
                border-radius: 8px;
                background: #FF8C00;
            }
        """)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(34, 28, 34, 30)
        root.setSpacing(18)

        # Header
        title = QLabel("🎙 NoiseFree")
        title.setObjectName("title")

        subtitle = QLabel(
            "AI-powered noise removal for lectures, recordings and voice audio."
        )
        subtitle.setObjectName("subtitle")

        root.addWidget(title)
        root.addWidget(subtitle)

        # File card
        file_card = QFrame()
        file_card.setObjectName("card")
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(22, 20, 22, 20)
        file_layout.setSpacing(12)

        section = QLabel("Recording")
        section.setObjectName("section")

        self.select_button = QPushButton("📁  Select Recording")
        self.select_button.setObjectName("primary")
        self.select_button.clicked.connect(self.select_file)

        self.file_name = QLabel("No recording selected")
        self.file_name.setObjectName("fileName")

        self.file_info = QLabel(
            "Choose a WAV, MP3, M4A, AAC, FLAC, OGG or OPUS recording."
        )
        self.file_info.setObjectName("fileInfo")
        self.file_info.setWordWrap(True)

        file_layout.addWidget(section)
        file_layout.addWidget(self.select_button)
        file_layout.addWidget(self.file_name)
        file_layout.addWidget(self.file_info)

        root.addWidget(file_card)

        # Processing card
        process_card = QFrame()
        process_card.setObjectName("card")
        process_layout = QVBoxLayout(process_card)
        process_layout.setContentsMargins(22, 20, 22, 20)
        process_layout.setSpacing(14)

        process_section = QLabel("Noise Removal")
        process_section.setObjectName("section")

        self.remove_button = QPushButton("🔇  Remove Noise")
        self.remove_button.setObjectName("primary")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self.start_processing)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        self.progress_text = QLabel("0%")
        self.progress_text.setAlignment(Qt.AlignRight)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        progress_row.addWidget(self.progress_bar, 1)
        progress_row.addWidget(self.progress_text)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)

        self.cancel_button = QPushButton("⏹  Cancel Processing")
        self.cancel_button.setObjectName("cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)

        process_layout.addWidget(process_section)
        process_layout.addWidget(self.remove_button)
        process_layout.addLayout(progress_row)
        process_layout.addWidget(self.status_label)
        process_layout.addWidget(self.cancel_button)

        root.addWidget(process_card)

        # Output actions
        output_card = QFrame()
        output_card.setObjectName("card")
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(22, 20, 22, 20)
        output_layout.setSpacing(12)

        output_section = QLabel("Clean Recording")
        output_section.setObjectName("section")

        self.output_label = QLabel("No cleaned recording yet.")
        self.output_label.setObjectName("fileInfo")
        self.output_label.setWordWrap(True)

        actions = QHBoxLayout()
        actions.setSpacing(12)

        self.play_button = QPushButton("▶  Play")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_clean_recording)

        self.save_button = QPushButton("💾  Save As")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_clean_recording)

        actions.addWidget(self.play_button)
        actions.addWidget(self.save_button)

        output_layout.addWidget(output_section)
        output_layout.addWidget(self.output_label)
        output_layout.addLayout(actions)

        root.addWidget(output_card)
        root.addStretch()

        footer = QLabel("NoiseFree • DeepFilterNet3 • MP3 192 kbps")
        footer.setStyleSheet("color: #68717E; font-size: 12px;")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)

        self.setCentralWidget(central)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Recording",
            str(Path.home()),
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.opus)",
        )

        if not file_path:
            return

        self.selected_file = Path(file_path)
        self.cleaned_file = None

        size_mb = self.selected_file.stat().st_size / (1024 * 1024)

        self.file_name.setText(self.selected_file.name)
        self.file_info.setText(
            f"{size_mb:.2f} MB\n{self.selected_file.parent}"
        )

        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.status_label.setText("Ready to remove noise.")
        self.output_label.setText("No cleaned recording yet.")

        self.remove_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.save_button.setEnabled(False)

    def start_processing(self):
        if not self.selected_file:
            return

        default_output = (
            self.selected_file.parent
            / f"{self.selected_file.stem}_cleaned.mp3"
        )

        output_file, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Clean Recording Location",
            str(default_output),
            "MP3 Audio (*.mp3)",
        )

        if not output_file:
            return

        output_path = Path(output_file)

        if output_path.resolve() == self.selected_file.resolve():
            QMessageBox.warning(
                self,
                "Invalid Output",
                "The output file must be different from the input file.",
            )
            return

        self.remove_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.select_button.setEnabled(False)
        self.play_button.setEnabled(False)
        self.save_button.setEnabled(False)

        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.status_label.setText("Loading DeepFilterNet model...")

        self.thread = QThread()
        self.worker = ProcessingWorker(
            str(self.selected_file),
            str(output_path),
        )

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.processing_finished)
        self.worker.cancelled.connect(self.processing_cancelled)
        self.worker.error.connect(self.processing_error)

        self.worker.finished.connect(self.thread.quit)
        self.worker.cancelled.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.thread_finished)

        self.thread.start()

    def cancel_processing(self):
        if not self.worker:
            return

        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            "Cancelling... finishing the current audio operation."
        )
        self.worker.cancel()

    @Slot(int)
    def update_progress(self, value):
        self.progress_bar.setValue(value)
        self.progress_text.setText(f"{value}%")
        self.status_label.setText("Removing background noise...")

    @Slot(str)
    def processing_finished(self, output_file):
        self.cleaned_file = Path(output_file)

        self.progress_bar.setValue(100)
        self.progress_text.setText("100%")
        self.status_label.setText("Noise removal completed successfully.")
        self.output_label.setText(str(self.cleaned_file))

        self.play_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        QMessageBox.information(
            self,
            "Complete",
            "Noise removal completed successfully.",
        )

    @Slot()
    def processing_cancelled(self):
        self.cleaned_file = None
        self.cancel_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_text.setText("0%")
        self.status_label.setText(
            "Processing cancelled. No incomplete output was kept."
        )
        self.output_label.setText("No cleaned recording yet.")

    @Slot(str)
    def processing_error(self, message):
        self.status_label.setText("Processing failed.")
        self.cancel_button.setEnabled(False)

        QMessageBox.critical(
            self,
            "Processing Error",
            f"Noise removal failed:\n\n{message}",
        )

    def play_clean_recording(self):
        if not self.cleaned_file or not self.cleaned_file.exists():
            QMessageBox.warning(
                self,
                "No Clean Recording",
                "Please remove the noise first.",
            )
            return

        if not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.cleaned_file))
        ):
            QMessageBox.warning(
                self,
                "Playback Error",
                "Could not open the clean recording with the system audio player.",
            )

    def save_clean_recording(self):
        if not self.cleaned_file or not self.cleaned_file.exists():
            QMessageBox.warning(
                self,
                "No Clean Recording",
                "Please remove the noise first.",
            )
            return

        default_path = Path.home() / "Desktop" / self.cleaned_file.name

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Clean Recording",
            str(default_path),
            "MP3 Audio (*.mp3)",
        )

        if not save_path:
            return

        destination = Path(save_path)

        try:
            if destination.resolve() == self.cleaned_file.resolve():
                QMessageBox.information(
                    self,
                    "Already Saved",
                    f"The clean recording is already here:\n\n{destination}",
                )
                return

            shutil.copy2(self.cleaned_file, destination)

            QMessageBox.information(
                self,
                "Saved",
                f"Clean recording saved to:\n\n{destination}",
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Could not save the clean recording:\n\n{exc}",
            )

    def thread_finished(self):
        self.thread = None
        self.worker = None
        self.select_button.setEnabled(True)

        if self.selected_file and not self.cleaned_file:
            self.remove_button.setEnabled(True)

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            QMessageBox.warning(
                self,
                "Processing in Progress",
                "Cancel processing first, then close NoiseFree.",
            )
            event.ignore()
            return

        event.accept()


def main():
    app = QApplication(sys.argv)
    window = NoiseFreeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
