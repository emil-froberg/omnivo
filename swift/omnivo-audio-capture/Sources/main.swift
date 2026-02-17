import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia

// Configuration
let sampleRate: Double = 48000

// ScreenCaptureKit delegate — system audio only
class AudioCaptureDelegate: NSObject, SCStreamOutput, SCStreamDelegate {
    let outputHandle = FileHandle.standardOutput

    var loggedFormat = false

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }

        // Log the actual audio format on first buffer
        if !loggedFormat {
            loggedFormat = true
            if let desc = CMSampleBufferGetFormatDescription(sampleBuffer),
               let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc) {
                let a = asbd.pointee
                FileHandle.standardError.write(
                    "Audio format: \(a.mSampleRate)Hz, \(a.mChannelsPerFrame)ch, \(a.mBitsPerChannel)bit, interleaved=\(a.mFormatFlags & kAudioFormatFlagIsNonInterleaved == 0)\n"
                        .data(using: .utf8)!)
            }
        }

        guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

        var length = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)

        guard let dataPointer = dataPointer, length > 0 else { return }

        let floatCount = length / MemoryLayout<Float>.size
        let floatPointer = UnsafeRawPointer(dataPointer).bindMemory(to: Float.self, capacity: floatCount)

        // Convert 32-bit float to 16-bit signed PCM (mono — we request mono from SCStream)
        var samples = [Int16](repeating: 0, count: floatCount)
        for i in 0..<floatCount {
            let clamped = max(-1.0, min(1.0, floatPointer[i]))
            samples[i] = Int16(clamped * Float(Int16.max))
        }

        samples.withUnsafeBytes { buffer in
            outputHandle.write(Data(buffer))
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("Stream stopped with error: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
}

// Main
func run() async throws {
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)

    guard let display = content.displays.first else {
        FileHandle.standardError.write("No display found\n".data(using: .utf8)!)
        exit(1)
    }

    let filter = SCContentFilter(display: display, excludingWindows: [])

    let config = SCStreamConfiguration()
    config.capturesAudio = true
    config.sampleRate = Int(sampleRate)
    config.channelCount = 1  // Request mono directly from ScreenCaptureKit
    config.excludesCurrentProcessAudio = true

    // Minimize video overhead
    config.width = 2
    config.height = 2
    config.minimumFrameInterval = CMTime(value: 1, timescale: 1)

    let delegate = AudioCaptureDelegate()
    let stream = SCStream(filter: filter, configuration: config, delegate: delegate)

    try stream.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: DispatchQueue(label: "audio"))
    try stream.addStreamOutput(delegate, type: .screen, sampleHandlerQueue: DispatchQueue(label: "screen"))

    FileHandle.standardError.write("Starting system audio capture...\n".data(using: .utf8)!)
    try await stream.startCapture()
    FileHandle.standardError.write("Capture started. Outputting PCM to stdout. Kill process to stop.\n".data(using: .utf8)!)

    // Handle SIGTERM/SIGINT gracefully
    let sigSources = [
        DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main),
        DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    ]
    signal(SIGTERM, SIG_IGN)
    signal(SIGINT, SIG_IGN)

    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        for source in sigSources {
            source.setEventHandler {
                FileHandle.standardError.write("Signal received, stopping capture...\n".data(using: .utf8)!)
                Task {
                    try? await stream.stopCapture()
                    continuation.resume()
                }
            }
            source.resume()
        }
    }
}

Task {
    do {
        try await run()
    } catch {
        FileHandle.standardError.write("Error: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
    exit(0)
}

RunLoop.main.run()
