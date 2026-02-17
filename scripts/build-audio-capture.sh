#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SWIFT_DIR="$PROJECT_DIR/swift/omnivo-audio-capture"
OUTPUT_DIR="$PROJECT_DIR/resources/bin"

echo "Building omnivo-audio-capture..."
cd "$SWIFT_DIR"
swift build -c release

mkdir -p "$OUTPUT_DIR"
cp ".build/release/omnivo-audio-capture" "$OUTPUT_DIR/omnivo-audio-capture"
echo "Binary copied to $OUTPUT_DIR/omnivo-audio-capture"
