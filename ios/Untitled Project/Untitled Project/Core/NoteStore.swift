import Foundation

/// Local note storage: one JSON file per note, no database. Mirrors the Mac app.
///
///     <root>/recordings/<id>.<ext>   the audio
///     <root>/notes/<id>.json         transcript + summary + metadata
///
/// The note id is the timestamp-based stem of the audio file, e.g. "20261124-171258".
nonisolated struct NoteStore: Sendable {
    static let audioExtensions: Set<String> = [
        "wav", "mp3", "m4a", "aac", "flac", "ogg", "opus", "aiff", "aif", "caf", "mp4", "webm",
    ]

    let root: URL

    var notesDirectory: URL { root.appending(path: "notes", directoryHint: .isDirectory) }
    var recordingsDirectory: URL { root.appending(path: "recordings", directoryHint: .isDirectory) }

    /// The app's Documents folder.
    static var `default`: NoteStore { NoteStore(root: .documentsDirectory) }

    // MARK: ids

    /// Also blocks path traversal like "../x".
    static func isValidID(_ id: String) -> Bool {
        id.range(of: #"^\d{8}-\d{6}(-\d+)?$"#, options: .regularExpression) != nil
    }

    private func noteURL(_ id: String) -> URL { notesDirectory.appending(path: "\(id).json") }

    // MARK: notes

    /// Atomically writes the note (temp file + rename) so a crash never leaves a half-written file.
    @discardableResult
    func save(_ note: Note) throws -> Note {
        guard Self.isValidID(note.id) else { throw StoreError.invalidID(note.id) }
        var note = note
        note.refreshTitle()
        try FileManager.default.createDirectory(at: notesDirectory, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try encoder.encode(note).write(to: noteURL(note.id), options: .atomic)
        return note
    }

    func get(_ id: String) -> Note? {
        guard Self.isValidID(id) else { return nil }
        return read(noteURL(id))
    }

    /// All readable notes, newest first. Unreadable files are skipped.
    func list() -> [Note] {
        let files = (try? FileManager.default.contentsOfDirectory(at: notesDirectory, includingPropertiesForKeys: nil)) ?? []
        return files
            .filter { $0.pathExtension == "json" }
            .compactMap(read)
            .sorted { $0.id > $1.id }
    }

    /// Deletes a note and its audio file.
    func delete(_ id: String) throws {
        guard Self.isValidID(id) else { throw StoreError.invalidID(id) }
        let note = get(id)
        try? FileManager.default.removeItem(at: noteURL(id))
        if let file = note?.audioFile {
            // lastPathComponent: a hand-edited note must never be able to delete outside the folder.
            try? FileManager.default.removeItem(at: recordingsDirectory.appending(path: URL(fileURLWithPath: file).lastPathComponent))
        }
    }

    private func read(_ url: URL) -> Note? {
        let id = url.deletingPathExtension().lastPathComponent
        guard Self.isValidID(id), let data = try? Data(contentsOf: url) else { return nil }
        guard var note = try? JSONDecoder().decode(Note.self, from: data) else { return nil }
        note.id = id  // the file name is the source of truth
        return note
    }

    // MARK: audio

    func audioURL(for note: Note) -> URL? {
        guard let file = note.audioFile else { return nil }
        let url = recordingsDirectory.appending(path: URL(fileURLWithPath: file).lastPathComponent)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    /// A fresh, unused audio path. Two recordings in the same second get "-1", "-2", ... suffixes.
    func newAudioURL(fileExtension: String, date: Date = Date()) throws -> URL {
        try FileManager.default.createDirectory(at: recordingsDirectory, withIntermediateDirectories: true)
        let stamp = NoteDates.idString(from: date)
        let existingStems = Set(
            ((try? FileManager.default.contentsOfDirectory(at: recordingsDirectory, includingPropertiesForKeys: nil)) ?? [])
                .map { $0.deletingPathExtension().lastPathComponent }
        )
        var n = 0
        while true {
            let id = n == 0 ? stamp : "\(stamp)-\(n)"
            // A note id is the audio file's stem, so it must be free regardless of extension.
            if !existingStems.contains(id) && !FileManager.default.fileExists(atPath: noteURL(id).path) {
                return recordingsDirectory.appending(path: "\(id).\(fileExtension)")
            }
            n += 1
        }
    }

    /// Copies (or moves) an audio file into the recordings folder and returns its new location.
    /// Handles security-scoped URLs from the Files picker.
    func ingestAudio(from source: URL, move: Bool, date: Date = Date()) throws -> URL {
        let ext = source.pathExtension.lowercased()
        guard Self.audioExtensions.contains(ext) else {
            throw StoreError.unsupportedAudio(ext.isEmpty ? "no extension" : ".\(ext)")
        }
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        guard FileManager.default.fileExists(atPath: source.path) else {
            throw StoreError.missingFile(source.lastPathComponent)
        }
        let destination = try newAudioURL(fileExtension: ext, date: date)
        if move {
            try FileManager.default.moveItem(at: source, to: destination)
        } else {
            try FileManager.default.copyItem(at: source, to: destination)
        }
        return destination
    }
}

nonisolated enum StoreError: LocalizedError {
    case invalidID(String)
    case unsupportedAudio(String)
    case missingFile(String)

    var errorDescription: String? {
        switch self {
        case .invalidID(let id): "Invalid note id: \(id)"
        case .unsupportedAudio(let ext): "This audio type (\(ext)) isn't supported."
        case .missingFile(let name): "Couldn't find the audio file \(name)."
        }
    }
}
