import subprocess
import tempfile
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

from df.enhance import init_df, enhance
from df.io import load_audio


class AudioProcessorV4:
    CHUNK_SECONDS = 30
    MP3_BITRATE = "192k"

    def __init__(self, input_file):
        self.input_file = Path(input_file)

        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")

        print("Loading DeepFilterNet model...")

        # In a PyInstaller build, the bundled model lives under _MEIPASS.
        # During normal development, continue using the user's DeepFilterNet cache.
        if getattr(sys, "frozen", False):
            model_dir = Path(sys._MEIPASS) / "models" / "DeepFilterNet3"
        else:
            model_dir = None

        if model_dir is not None and not model_dir.exists():
            raise FileNotFoundError(
                f"Bundled DeepFilterNet3 model not found: {model_dir}"
            )

        self.model, self.df_state, _ = init_df(
            model_base_dir=str(model_dir) if model_dir else None,
            log_level="ERROR",
            log_file=None
        )

        print("DeepFilterNet model loaded.")

    def _get_duration(self):
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(self.input_file),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())

    def _extract_chunk(self, start, duration, output_file):
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-fflags", "+discardcorrupt",
                "-err_detect", "ignore_err",
                "-max_error_rate", "1.0",
                "-ss", str(start),
                "-i", str(self.input_file),
                "-t", str(duration),
                "-map", "0:a:0",
                "-ac", "1",
                "-ar", str(self.df_state.sr()),
                "-c:a", "pcm_s16le",
                "-y", str(output_file),
            ],
            check=True,
        )

    def process(self, output_file, progress_callback=None, cancel_event=None):
        output_file = Path(output_file)

        if output_file.resolve() == self.input_file.resolve():
            raise ValueError("Output file must be different from the input file.")

        duration = self._get_duration()

        total_chunks = int(
            (duration + self.CHUNK_SECONDS - 1) // self.CHUNK_SECONDS
        )

        print(f"Input duration: {duration / 60:.2f} minutes")
        print(f"Chunk size: {self.CHUNK_SECONDS} seconds")
        print(f"Total chunks: {total_chunks}")

        temp_root = Path(tempfile.mkdtemp(prefix="noisefree_v4_"))
        chunk_file = temp_root / "chunk.wav"

        ffmpeg_process = None
        cancelled = False
        skipped_chunks = []

        try:
            ffmpeg_process = subprocess.Popen(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "s16le",
                    "-ar", str(self.df_state.sr()),
                    "-ac", "1",
                    "-i", "pipe:0",
                    "-codec:a", "libmp3lame",
                    "-b:a", self.MP3_BITRATE,
                    "-y", str(output_file),
                ],
                stdin=subprocess.PIPE,
            )

            for index in range(total_chunks):
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break

                start = index * self.CHUNK_SECONDS
                remaining = duration - start
                chunk_duration = min(self.CHUNK_SECONDS, remaining)

                print(f"Processing chunk {index + 1}/{total_chunks}...")

                if chunk_file.exists():
                    chunk_file.unlink()

                try:
                    self._extract_chunk(start, chunk_duration, chunk_file)
                except (subprocess.CalledProcessError, OSError) as exc:
                    # Some MP3 files contain damaged frames, especially near the end.
                    # Do not abort the entire recording because one chunk is undecodable.
                    skipped_chunks.append(index + 1)
                    print(
                        f"Warning: chunk {index + 1}/{total_chunks} could not be decoded; "
                        f"skipping this chunk."
                    )
                    print(f"FFmpeg error: {exc}")
                    progress = int(((index + 1) / total_chunks) * 100)
                    if progress_callback:
                        progress_callback(progress)
                    continue

                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break

                audio, _ = load_audio(
                    str(chunk_file),
                    sr=self.df_state.sr()
                )

                with torch.no_grad():
                    enhanced = enhance(
                        self.model,
                        self.df_state,
                        audio
                    )

                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    del audio
                    del enhanced
                    break

                enhanced = enhanced.detach().cpu().numpy()

                if enhanced.ndim == 2:
                    enhanced = enhanced[0]

                enhanced = np.clip(enhanced, -1.0, 1.0)
                pcm16 = (enhanced * 32767.0).astype(np.int16)

                ffmpeg_process.stdin.write(pcm16.tobytes())

                progress = int(((index + 1) / total_chunks) * 100)

                if progress_callback:
                    progress_callback(progress)

                del audio
                del enhanced
                del pcm16

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        except BrokenPipeError as exc:
            if cancel_event and cancel_event.is_set():
                cancelled = True
            else:
                raise RuntimeError(
                    "FFmpeg MP3 encoder stopped unexpectedly."
                ) from exc

        finally:
            if ffmpeg_process is not None:
                try:
                    if ffmpeg_process.stdin:
                        ffmpeg_process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

                if cancelled:
                    ffmpeg_process.terminate()
                return_code = ffmpeg_process.wait()

            shutil.rmtree(temp_root, ignore_errors=True)

        if cancelled:
            try:
                if output_file.exists():
                    output_file.unlink()
            except OSError:
                pass
            raise InterruptedError("Noise removal was cancelled.")

        if return_code != 0:
            raise RuntimeError("FFmpeg failed while creating the MP3 output.")

        print()
        print("Noise removal completed!")
        print(f"Output: {output_file}")

        if skipped_chunks:
            print(
                "Warning: skipped undecodable chunks: "
                + ", ".join(map(str, skipped_chunks))
            )
