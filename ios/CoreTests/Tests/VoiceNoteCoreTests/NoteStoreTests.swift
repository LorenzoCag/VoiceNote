import Foundation
import Testing

@testable import VoiceNoteCore

/// Each test gets its own temporary folder, removed afterwards.
final class TempStore {
    let root: URL
    let store: NoteStore

    init() {
        root = FileManager.default.temporaryDirectory.appending(path: "VoiceNoteTests-\(UUID().uuidString)")
        try! FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        store = NoteStore(root: root)
    }

    deinit { try? FileManager.default.removeItem(at: root) }

    func note(_ id: String = "20261124-170000", text: String = "Call the dentist tomorrow.", audio: String? = nil) -> Note {
        Note.create(id: id, audioFile: audio, transcript: TranscriptData(text: text))
    }

    /// A small fake audio file outside the store (like one picked from Files).
    func outsideAudio(named name: String = "memo.m4a") throws -> URL {
        let url = root.appending(path: "outside-\(name)")
        try Data("fake audio".utf8).write(to: url)
        return url
    }
}

@Suite struct NoteStoreTests {
    @Test func saveAndGetRoundTrip() throws {
        let t = TempStore()
        let saved = try t.store.save(t.note())
        let loaded = try #require(t.store.get(saved.id))
        #expect(loaded.transcriptText == "Call the dentist tomorrow.")
        #expect(loaded.title == "Call the dentist tomorrow.")
    }

    @Test func listIsNewestFirst() throws {
        let t = TempStore()
        try t.store.save(t.note("20261124-100000"))
        try t.store.save(t.note("20261124-120000"))
        try t.store.save(t.note("20261123-230000"))
        #expect(t.store.list().map(\.id) == ["20261124-120000", "20261124-100000", "20261123-230000"])
    }

    @Test func listSkipsCorruptAndForeignFiles() throws {
        let t = TempStore()
        try t.store.save(t.note("20261124-100000"))
        let dir = t.store.notesDirectory
        try "{not json".write(to: dir.appending(path: "20261124-110000.json"), atomically: true, encoding: .utf8)
        try #""a string, not an object""#.write(to: dir.appending(path: "20261124-130000.json"), atomically: true, encoding: .utf8)
        try "{}".write(to: dir.appending(path: "not-a-note-id.json"), atomically: true, encoding: .utf8)
        try "hello".write(to: dir.appending(path: "notes.txt"), atomically: true, encoding: .utf8)
        #expect(t.store.list().map(\.id) == ["20261124-100000"])
    }

    @Test func listIsEmptyWhenNothingSavedYet() {
        #expect(TempStore().store.list().isEmpty)
    }

    @Test func fileNameIsTheSourceOfTruthForTheId() throws {
        let t = TempStore()
        try t.store.save(t.note("20261124-100000"))
        let path = t.store.notesDirectory.appending(path: "20261124-100000.json")
        let tampered = try String(contentsOf: path, encoding: .utf8).replacingOccurrences(of: "\"id\" : \"20261124-100000\"", with: "\"id\" : \"20990101-000000\"")
        try tampered.write(to: path, atomically: true, encoding: .utf8)
        #expect(t.store.get("20261124-100000")?.id == "20261124-100000")
    }

    @Test func savingLeavesNoTemporaryFiles() throws {
        let t = TempStore()
        try t.store.save(t.note())
        let names = try FileManager.default.contentsOfDirectory(atPath: t.store.notesDirectory.path)
        #expect(names == ["20261124-170000.json"])
    }

    @Test func rejectsInvalidAndTraversalIds() {
        let t = TempStore()
        for bad in ["../secret", "a/b", "", "20261124-17000", "20261124-170000.json"] {
            #expect(NoteStore.isValidID(bad) == false, "\(bad) should be invalid")
            #expect(t.store.get(bad) == nil)
            #expect(throws: StoreError.self) { try t.store.delete(bad) }
        }
        #expect(throws: StoreError.self) { try t.store.save(Note(id: "../x", createdAt: "2026-11-24T10:00:00")) }
        #expect(NoteStore.isValidID("20261124-170000-2"))
    }

    // MARK: delete

    @Test func deleteRemovesNoteAndAudio() throws {
        let t = TempStore()
        let audio = try t.store.ingestAudio(from: t.outsideAudio(), move: false)
        let note = try t.store.save(t.note(audio.deletingPathExtension().lastPathComponent, audio: audio.lastPathComponent))
        #expect(t.store.audioURL(for: note) != nil)
        try t.store.delete(note.id)
        #expect(t.store.get(note.id) == nil)
        #expect(!FileManager.default.fileExists(atPath: audio.path))
    }

    @Test func aTamperedAudioPathCannotDeleteOutsideTheRecordingsFolder() throws {
        let t = TempStore()
        let victim = t.root.appending(path: "victim.txt")
        try "keep me".write(to: victim, atomically: true, encoding: .utf8)
        let note = try t.store.save(t.note(audio: "../victim.txt"))
        try t.store.delete(note.id)
        #expect(FileManager.default.fileExists(atPath: victim.path))
    }

    @Test func deletingAMissingNoteIsHarmless() throws {
        try TempStore().store.delete("20261124-170000")
    }

    // MARK: audio

    @Test func ingestCopiesAndKeepsTheOriginal() throws {
        let t = TempStore()
        let source = try t.outsideAudio()
        let dest = try t.store.ingestAudio(from: source, move: false)
        #expect(FileManager.default.fileExists(atPath: source.path))
        #expect(FileManager.default.fileExists(atPath: dest.path))
        #expect(dest.deletingLastPathComponent().lastPathComponent == "recordings")
        #expect(dest.pathExtension == "m4a")
    }

    @Test func ingestWithMoveRemovesTheOriginal() throws {
        let t = TempStore()
        let source = try t.outsideAudio()
        let dest = try t.store.ingestAudio(from: source, move: true)
        #expect(!FileManager.default.fileExists(atPath: source.path))
        #expect(FileManager.default.fileExists(atPath: dest.path))
    }

    @Test func ingestRejectsUnsupportedAndMissingFiles() throws {
        let t = TempStore()
        let exe = t.root.appending(path: "program.exe")
        try Data("x".utf8).write(to: exe)
        #expect(throws: StoreError.self) { try t.store.ingestAudio(from: exe, move: false) }
        #expect(throws: StoreError.self) { try t.store.ingestAudio(from: t.root.appending(path: "missing.m4a"), move: false) }
    }

    @Test func recordingsInTheSameSecondNeverOverwrite() throws {
        let t = TempStore()
        let date = Date()
        var urls: Set<URL> = []
        for _ in 0..<4 {
            let url = try t.store.newAudioURL(fileExtension: "m4a", date: date)
            try Data("x".utf8).write(to: url)
            urls.insert(url)
        }
        #expect(urls.count == 4)
        for url in urls { #expect(NoteStore.isValidID(url.deletingPathExtension().lastPathComponent)) }
    }

    @Test func sameSecondDifferentExtensionStillGetsADistinctId() throws {
        let t = TempStore()
        let date = Date()
        let first = try t.store.newAudioURL(fileExtension: "m4a", date: date)
        try Data("x".utf8).write(to: first)
        let second = try t.store.newAudioURL(fileExtension: "wav", date: date)
        #expect(first.deletingPathExtension().lastPathComponent != second.deletingPathExtension().lastPathComponent)
    }
}
