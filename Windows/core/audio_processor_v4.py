import subprocess
import tempfile
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

from df.enhance import init_df, enhance
from df.io import load_audio
import df.utils
import df.logger


class AudioProcessorV4:
    CHUNK_SECONDS = 30
    MP3_BITRATE = "192k"

    def __init__(self, input_file):
        self.input_file = Path(input_file)

        if not self.input_file.exists():
            raise FileNotFoundError(
                f"Input file not found: {self.input_file}"
            )

        # =========================================================
        # Locate FFmpeg / FFprobe
        # =========================================================

        if getattr(sys, "frozen", False):
            # PyInstaller
            base_dir = Path(sys._MEIPASS)
        else:
            # Normal Python execution
            base_dir = Path(__file__).resolve().parent.parent

        self.ffmpeg = (
            base_dir
            / "tools"
            / "bin"
            / "ffmpeg.exe"
        )

        self.ffprobe = (
            base_dir
            / "tools"
            / "bin"
            / "ffprobe.exe"
        )

        if not self.ffmpeg.exists():
            raise FileNotFoundError(
                f"FFmpeg not found:\n{self.ffmpeg}"
            )

        if not self.ffprobe.exists():
            raise FileNotFoundError(
                f"FFprobe not found:\n{self.ffprobe}"
            )

        print(
            f"Using FFmpeg: {self.ffmpeg}"
        )

        print(
            f"Using FFprobe: {self.ffprobe}"
        )

        # =========================================================
        # Load DeepFilterNet
        # =========================================================

        print(
            "Loading DeepFilterNet model..."
        )

        if getattr(sys, "frozen", False):
            model_dir = (
                Path(sys._MEIPASS)
                / "models"
                / "DeepFilterNet3"
            )
        else:
            # Development version uses normal DeepFilterNet cache
            model_dir = None

        if (
            model_dir is not None
            and not model_dir.exists()
        ):
            raise FileNotFoundError(
                "Bundled DeepFilterNet3 model "
                f"not found:\n{model_dir}"
            )

        # =========================================================
        # Prevent DeepFilterNet from requiring Git
        # =========================================================

        def no_git_hash():
            return "unknown"

        try:
            df.utils.get_commit_hash = no_git_hash
        except Exception:
            pass

        try:
            df.logger.get_commit_hash = no_git_hash
        except Exception:
            pass

        try:
            df.utils.get_git_root = (
                lambda: None
            )
        except Exception:
            pass

        try:
            df.logger.get_git_root = (
                lambda: None
            )
        except Exception:
            pass

        # =========================================================
        # Initialize DeepFilterNet
        # =========================================================

        self.model, self.df_state, _ = init_df(
            model_base_dir=(
                str(model_dir)
                if model_dir
                else None
            ),
            log_level="ERROR",
            log_file=None,
        )

        print(
            "DeepFilterNet model loaded."
        )

    # =============================================================
    # Get audio duration
    # =============================================================

    def _get_duration(self):

        result = subprocess.run(
            [
                str(self.ffprobe),

                "-v",
                "error",

                "-show_entries",
                "format=duration",

                "-of",
                "default=noprint_wrappers=1:nokey=1",

                str(self.input_file),
            ],
            capture_output=True,
            text=True,
            check=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0
            ),
        )

        output = result.stdout.strip()

        if not output:
            raise RuntimeError(
                "FFprobe could not determine "
                "the audio duration."
            )

        return float(output)

    # =============================================================
    # Extract one audio chunk
    # =============================================================

    def _extract_chunk(
        self,
        start,
        duration,
        output_file,
    ):

        result = subprocess.run(
            [
                str(self.ffmpeg),

                "-hide_banner",
                "-loglevel",
                "error",

                # Ignore damaged MP3 frames
                "-fflags",
                "+discardcorrupt",

                "-err_detect",
                "ignore_err",

                "-max_error_rate",
                "1.0",

                "-ss",
                str(start),

                "-i",
                str(self.input_file),

                "-t",
                str(duration),

                "-map",
                "0:a:0",

                # Mono
                "-ac",
                "1",

                # DeepFilterNet sample rate
                "-ar",
                str(self.df_state.sr()),

                # PCM WAV for processing
                "-c:a",
                "pcm_s16le",

                "-y",
                str(output_file),
            ],
            capture_output=True,
            text=True,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if sys.platform == "win32"
                else 0
            ),
        )

        if result.returncode != 0:

            error = result.stderr.strip()

            if not error:
                error = (
                    "FFmpeg returned an error "
                    "without additional details."
                )

            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=error,
            )

    # =============================================================
    # Main processing
    # =============================================================

    def process(
        self,
        output_file,
        progress_callback=None,
        cancel_event=None,
    ):

        output_file = Path(output_file)

        # ---------------------------------------------------------
        # Prevent input/output collision
        # ---------------------------------------------------------

        if (
            output_file.resolve()
            == self.input_file.resolve()
        ):
            raise ValueError(
                "Output file must be different "
                "from the input file."
            )

        # ---------------------------------------------------------
        # Create output directory if necessary
        # ---------------------------------------------------------

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ---------------------------------------------------------
        # Get duration
        # ---------------------------------------------------------

        duration = self._get_duration()

        total_chunks = int(
            (
                duration
                + self.CHUNK_SECONDS
                - 1
            )
            // self.CHUNK_SECONDS
        )

        print(
            f"Input duration: "
            f"{duration / 60:.2f} minutes"
        )

        print(
            f"Chunk size: "
            f"{self.CHUNK_SECONDS} seconds"
        )

        print(
            f"Total chunks: "
            f"{total_chunks}"
        )

        # ---------------------------------------------------------
        # Temporary directory
        # ---------------------------------------------------------

        temp_root = Path(
            tempfile.mkdtemp(
                prefix="noisefree_v4_"
            )
        )

        chunk_file = (
            temp_root / "chunk.wav"
        )

        ffmpeg_process = None
        cancelled = False
        skipped_chunks = []
        return_code = 0
        ffmpeg_error = ""

        try:

            # =====================================================
            # Start FFmpeg MP3 encoder
            # =====================================================

            ffmpeg_command = [
                str(self.ffmpeg),

                "-hide_banner",
                "-loglevel",
                "error",

                # Raw PCM input
                "-f",
                "s16le",

                "-ar",
                str(self.df_state.sr()),

                "-ac",
                "1",

                "-i",
                "pipe:0",

                # MP3 encoder
                "-codec:a",
                "libmp3lame",

                "-b:a",
                self.MP3_BITRATE,

                "-y",
                str(output_file),
            ]

            print(
                "Starting FFmpeg MP3 encoder..."
            )

            popen_kwargs = {
                "stdin": subprocess.PIPE,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.PIPE,
            }

            # Hide FFmpeg console window on Windows
            if sys.platform == "win32":
                popen_kwargs[
                    "creationflags"
                ] = subprocess.CREATE_NO_WINDOW

            ffmpeg_process = subprocess.Popen(
                ffmpeg_command,
                **popen_kwargs,
            )

            # =====================================================
            # Process chunks
            # =====================================================

            for index in range(
                total_chunks
            ):

                # -------------------------------------------------
                # Cancellation check
                # -------------------------------------------------

                if (
                    cancel_event
                    and cancel_event.is_set()
                ):
                    cancelled = True
                    break

                start = (
                    index
                    * self.CHUNK_SECONDS
                )

                remaining = (
                    duration - start
                )

                chunk_duration = min(
                    self.CHUNK_SECONDS,
                    remaining,
                )

                print(
                    f"Processing chunk "
                    f"{index + 1}/"
                    f"{total_chunks}..."
                )

                # -------------------------------------------------
                # Remove previous temporary chunk
                # -------------------------------------------------

                if chunk_file.exists():
                    try:
                        chunk_file.unlink()
                    except OSError:
                        pass

                # -------------------------------------------------
                # Extract chunk
                # -------------------------------------------------

                try:

                    self._extract_chunk(
                        start,
                        chunk_duration,
                        chunk_file,
                    )

                except (
                    subprocess.CalledProcessError,
                    OSError,
                ) as exc:

                    skipped_chunks.append(
                        index + 1
                    )

                    print(
                        f"Warning: chunk "
                        f"{index + 1}/"
                        f"{total_chunks} "
                        "could not be decoded; "
                        "skipping this chunk."
                    )

                    if isinstance(
                        exc,
                        subprocess.CalledProcessError,
                    ):
                        if exc.stderr:
                            print(
                                "FFmpeg error:"
                            )
                            print(
                                exc.stderr
                            )
                    else:
                        print(
                            f"FFmpeg error: {exc}"
                        )

                    progress = int(
                        (
                            (index + 1)
                            / total_chunks
                        )
                        * 100
                    )

                    if progress_callback:
                        progress_callback(
                            progress
                        )

                    continue

                # -------------------------------------------------
                # Cancellation check
                # -------------------------------------------------

                if (
                    cancel_event
                    and cancel_event.is_set()
                ):
                    cancelled = True
                    break

                # -------------------------------------------------
                # Load audio
                # -------------------------------------------------

                audio, _ = load_audio(
                    str(chunk_file),
                    sr=self.df_state.sr(),
                )

                # -------------------------------------------------
                # DeepFilterNet
                # -------------------------------------------------

                with torch.no_grad():

                    enhanced = enhance(
                        self.model,
                        self.df_state,
                        audio,
                    )

                # -------------------------------------------------
                # Cancellation check
                # -------------------------------------------------

                if (
                    cancel_event
                    and cancel_event.is_set()
                ):

                    cancelled = True

                    del audio
                    del enhanced

                    break

                # -------------------------------------------------
                # Convert Torch tensor to NumPy
                # -------------------------------------------------

                enhanced = (
                    enhanced
                    .detach()
                    .cpu()
                    .numpy()
                )

                # -------------------------------------------------
                # Remove channel dimension
                # -------------------------------------------------

                if enhanced.ndim == 2:
                    enhanced = enhanced[0]

                # -------------------------------------------------
                # Keep samples in valid range
                # -------------------------------------------------

                enhanced = np.clip(
                    enhanced,
                    -1.0,
                    1.0,
                )

                # -------------------------------------------------
                # Float32 -> PCM16
                # -------------------------------------------------

                pcm16 = (
                    enhanced
                    * 32767.0
                ).astype(
                    np.int16
                )

                # -------------------------------------------------
                # Send audio to FFmpeg
                # -------------------------------------------------

                try:

                    ffmpeg_process.stdin.write(
                        pcm16.tobytes()
                    )

                except (
                    BrokenPipeError,
                    OSError,
                ) as exc:

                    # FFmpeg has stopped.
                    # Capture its real error.

                    try:
                        return_code = (
                            ffmpeg_process.poll()
                        )
                    except Exception:
                        return_code = None

                    try:

                        if (
                            ffmpeg_process.stderr
                        ):
                            stderr_data = (
                                ffmpeg_process.stderr.read()
                            )

                            if isinstance(
                                stderr_data,
                                bytes,
                            ):
                                ffmpeg_error = (
                                    stderr_data
                                    .decode(
                                        "utf-8",
                                        errors="replace",
                                    )
                                )
                            else:
                                ffmpeg_error = (
                                    stderr_data
                                )

                            ffmpeg_error = (
                                ffmpeg_error.strip()
                            )

                    except Exception:
                        ffmpeg_error = ""

                    if not ffmpeg_error:
                        ffmpeg_error = (
                            "No FFmpeg error output "
                            "was available."
                        )

                    raise RuntimeError(
                        "FFmpeg MP3 encoder "
                        "stopped unexpectedly.\n\n"
                        f"FFmpeg exit code: "
                        f"{return_code}\n\n"
                        "FFmpeg error:\n"
                        f"{ffmpeg_error}"
                    ) from exc

                # -------------------------------------------------
                # Progress
                # -------------------------------------------------

                progress = int(
                    (
                        (index + 1)
                        / total_chunks
                    )
                    * 100
                )

                if progress_callback:
                    progress_callback(
                        progress
                    )

                # -------------------------------------------------
                # Free memory
                # -------------------------------------------------

                del audio
                del enhanced
                del pcm16

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        finally:

            # =====================================================
            # Close FFmpeg
            # =====================================================

            if ffmpeg_process is not None:

                try:

                    if (
                        ffmpeg_process.stdin
                        and not ffmpeg_process.stdin.closed
                    ):
                        ffmpeg_process.stdin.close()

                except (
                    BrokenPipeError,
                    OSError,
                ):
                    pass

                # -------------------------------------------------
                # Cancel FFmpeg
                # -------------------------------------------------

                if cancelled:

                    try:
                        ffmpeg_process.terminate()
                    except OSError:
                        pass

                # -------------------------------------------------
                # Wait for FFmpeg
                # -------------------------------------------------

                try:

                    return_code = (
                        ffmpeg_process.wait()
                    )

                except Exception:

                    return_code = -1

                # -------------------------------------------------
                # Read remaining FFmpeg stderr
                # -------------------------------------------------

                try:

                    if (
                        ffmpeg_process.stderr
                    ):

                        stderr_data = (
                            ffmpeg_process.stderr.read()
                        )

                        if isinstance(
                            stderr_data,
                            bytes,
                        ):
                            stderr_data = (
                                stderr_data
                                .decode(
                                    "utf-8",
                                    errors="replace",
                                )
                            )

                        if stderr_data:
                            ffmpeg_error = (
                                stderr_data.strip()
                            )

                except Exception:
                    pass

            # -----------------------------------------------------
            # Remove temporary files
            # -----------------------------------------------------

            shutil.rmtree(
                temp_root,
                ignore_errors=True,
            )

        # =========================================================
        # Cancelled
        # =========================================================

        if cancelled:

            try:

                if output_file.exists():
                    output_file.unlink()

            except OSError:
                pass

            raise InterruptedError(
                "Noise removal was cancelled."
            )

        # =========================================================
        # FFmpeg failed
        # =========================================================

        if return_code != 0:

            try:

                if output_file.exists():
                    output_file.unlink()

            except OSError:
                pass

            message = (
                "FFmpeg failed while "
                "creating the MP3 output."
            )

            if ffmpeg_error:
                message += (
                    "\n\nFFmpeg error:\n"
                    + ffmpeg_error
                )

            raise RuntimeError(
                message
            )

        # =========================================================
        # Success
        # =========================================================

        print()
        print(
            "Noise removal completed!"
        )

        print(
            f"Output: {output_file}"
        )

        # =========================================================
        # Damaged chunks
        # =========================================================

        if skipped_chunks:

            print(
                "Warning: skipped "
                "undecodable chunks: "
                + ", ".join(
                    map(
                        str,
                        skipped_chunks,
                    )
                )
            )