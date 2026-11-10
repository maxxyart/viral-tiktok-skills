// Apple Vision OCR for slide images (fast_slides.py compiles it on first use).
//
//   ocr_vision [--lang en-US,ru-RU | --lang auto] [--correct] IMG...
//   ocr_vision --spell [--lang en] < words.txt
//
// One JSON line per image: {"file", "w", "h", "lines": [{"t", "c", "x", "y", "w", "h"}]}
// or {"file", "error"}. Boxes are normalized 0..1 with the origin top-left, "c" is
// Vision's confidence. Language correction is off by default so author typos survive
// (the skill keeps them: a repeated typo reveals a reused template). Images are opened
// with ImageIO by content, not extension: TikTok serves HEIC under a .webp name.
//
// --spell: one word per stdin line -> {"w", "ok", "g": [guesses]} per line from the macOS
// spell checker; fast_slides.py keeps only guesses shaped like OCR errors.
import AppKit
import Foundation
import ImageIO
import Vision

var langs = ["en-US"]
var correct = false
var spell = false
var files: [String] = []
var it = CommandLine.arguments.dropFirst().makeIterator()
while let a = it.next() {
    switch a {
    case "--lang": if let v = it.next() { langs = v.split(separator: ",").map(String.init) }
    case "--correct": correct = true
    case "--spell": spell = true
    default: files.append(a)
    }
}

func r4(_ v: CGFloat) -> Double { (Double(v) * 10000).rounded() / 10000 }

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
}

if spell {
    let checker = NSSpellChecker.shared
    let lang = String((langs.first ?? "en").prefix(2))
    while let w = readLine() {
        let range = checker.checkSpelling(of: w, startingAt: 0, language: lang, wrap: false,
                                          inSpellDocumentWithTag: 0, wordCount: nil)
        let ok = range.location == NSNotFound
        let g = ok ? [] : (checker.guesses(forWordRange: NSRange(location: 0, length: (w as NSString).length),
                                           in: w, language: lang, inSpellDocumentWithTag: 0) ?? [])
        emit(["w": w, "ok": ok, "g": g])
    }
    exit(0)
}

for path in files {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let cg = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        emit(["file": path, "error": "unreadable image"])
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = correct
    if langs == ["auto"] {
        req.automaticallyDetectsLanguage = true
    } else {
        req.recognitionLanguages = langs
    }
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    } catch {
        emit(["file": path, "error": "\(error)"])
        continue
    }
    let lines: [[String: Any]] = (req.results ?? []).compactMap { o in
        guard let c = o.topCandidates(1).first else { return nil }
        let b = o.boundingBox
        return ["t": c.string, "c": (Double(c.confidence) * 100).rounded() / 100,
                "x": r4(b.minX), "y": r4(1 - b.maxY), "w": r4(b.width), "h": r4(b.height)]
    }
    emit(["file": path, "w": cg.width, "h": cg.height, "lines": lines])
}
