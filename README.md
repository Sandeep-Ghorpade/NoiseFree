# NoiseFree 🎧

NoiseFree is a cross-platform desktop application for removing unwanted background noise from audio recordings using AI-based audio enhancement.

It is designed especially for speech and lecture recordings where background noise such as fan noise, hissing, and people talking can reduce speech clarity.


## Features

-  AI-based audio noise reduction
-  Designed for speech and lecture recordings
-  Reduces background fan noise and hissing
-  Helps reduce unwanted background speech
-  Supports large audio recordings
-  Processes recordings internally in smaller chunks
-  Powered by DeepFilterNet3
-  Windows standalone application
-  Linux AppImage
-  Simple desktop graphical interface
-  Built-in playback of processed audio
-  Save processed audio using Save As
-  No separate Python installation required for packaged applications
-  Users do not need to manually split large recordings into chunks

---


## Supported Platforms

### Windows

- Windows 10 / 11
- 64-bit
- CPU-based processing
- Standalone `.exe` application

### Linux

- 64-bit Linux
- Tested on Ubuntu 24.04 LTS
- CPU-based processing
- AppImage distribution

---


## How It Works

NoiseFree uses **DeepFilterNet3** for AI-based speech enhancement.

The user selects the complete audio recording once. NoiseFree internally divides the recording into smaller processing chunks, processes each chunk, and combines the processed audio into the final output.

The user does **not** need to manually split the recording.


### Processing Flow

```text
Select Recording
       ↓
NoiseFree loads the recording
       ↓
Audio is processed internally in chunks
       ↓
DeepFilterNet3 performs noise reduction
       ↓
Processed audio is combined
       ↓
Cleaned audio is generated
       ↓
Play or Save the result


## Download

Pre-built applications will be available in the **GitHub Releases** section.


### Windows
Download:

```text
NoiseFree-Windows.exe


### Linux
Download:

```text
NoiseFree-Linux.AppImage


## User Interface

NoiseFree provides a simple desktop interface with the following options.

### 1. Select Recording

**Select Recording** allows you to choose the audio file that you want to process.

Click this button and select your recording from your computer.

After selecting the file, NoiseFree displays the selected recording in the application.

> You only need to select the complete recording. You do not need to split a large recording manually.

---

### 2. Remove Noise

**Remove Noise** starts the AI-based noise reduction process.

When you click this button:

1. NoiseFree loads the selected recording.
2. The recording is internally divided into smaller chunks.
3. Each chunk is processed using DeepFilterNet3.
4. The processed chunks are combined.
5. The final cleaned audio is generated.

A progress indicator shows the processing progress.

> Processing time depends on the length of the recording and your computer's CPU performance.

---

### 3. Progress Indicator

The **progress indicator** shows the current processing status.

For example:

```text
Processing: 45%

### 4. Cancel

The Cancel button allows you to stop an ongoing noise-removal operation.

Use this if you want to stop processing before it finishes.
