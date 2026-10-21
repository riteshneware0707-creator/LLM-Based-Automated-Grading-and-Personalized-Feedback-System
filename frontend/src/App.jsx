import { useRef, useState } from "react";
import {
  Check,
  Code2,
  FileText,
  LoaderCircle,
  Upload,
  X,
} from "lucide-react";

function App() {
  const inputRef = useRef(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function processFile(file) {
    if (!file) return;
    setError("");
    setResult(null);
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file.");
      return;
    }

    setIsLoading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/api/extract", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to extract this PDF.");
      }
      setResult(payload);
    } catch (requestError) {
      setError(
        requestError.message === "Failed to fetch"
          ? "The extraction service is unavailable. Start the backend and try again."
          : requestError.message,
      );
    } finally {
      setIsLoading(false);
    }
  }

  function clearFile() {
    setResult(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-content">
          <div className="page-context">
            <span className="context-icon"><FileText size={17} /></span>
            <span>Submission review</span>
          </div>
          <div className="instructor">
            <span className="instructor-avatar">SK</span>
            <span>Sanjay Kumar</span>
          </div>
        </div>
      </header>

      <main className="main-content">
        <section className="intro">
          <p className="eyebrow">PDF CODE EXTRACTION</p>
          <h1>Extract code from a PDF</h1>
          <p className="intro-copy">
            Upload a submission to extract its code and check the result.
          </p>
        </section>

        <section
          className={`upload-card${dragging ? " is-dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            processFile(event.dataTransfer.files[0]);
          }}
        >
          <div className="card-heading">
            <div>
              <h2>Submission PDF</h2>
              <p>PDF only · Maximum file size 20 MB</p>
            </div>
            {result && (
              <span className="processed-status"><Check size={14} /> Processed</span>
            )}
          </div>

          <button
            className="drop-zone"
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={isLoading}
          >
            <span className="upload-icon">
              {isLoading ? (
                <LoaderCircle className="spin" size={20} />
              ) : (
                <Upload size={20} />
              )}
            </span>
            <span className="drop-title">
              {isLoading ? "Extracting text and code…" : "Choose a PDF or drag it here"}
            </span>
            <span className="drop-hint">Your file is processed in memory, not stored.</span>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(event) => processFile(event.target.files?.[0])}
            />
          </button>

          {error && <div className="error-message" role="alert">{error}</div>}

          {result && (
            <div className="file-row">
              <span className="file-icon"><FileText size={17} /></span>
              <span className="file-details">
                <strong>{result.filename}</strong>
                <span>{result.page_count} {result.page_count === 1 ? "page" : "pages"}</span>
              </span>
              <button
                className="remove-file"
                type="button"
                aria-label="Remove PDF"
                onClick={clearFile}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {result?.warnings?.map((warning) => (
            <p className="warning-message" key={warning}>{warning}</p>
          ))}
        </section>

        <section className="result-card">
          <div className="result-heading">
            <div>
              <h2><Code2 size={17} /> Extracted code</h2>
              <p>{result ? "Review the code found in the document." : "Code found in the uploaded PDF will appear here."}</p>
            </div>
            {result && (
              <span className="block-count">
                {result.code_blocks.length} {result.code_blocks.length === 1 ? "block" : "blocks"}
              </span>
            )}
          </div>

          {result ? (
            result.code_blocks.length ? (
              <div className="code-list">
                {result.code_blocks.map((block, index) => (
                  <article className="code-block" key={`${index}-${block.code.slice(0, 20)}`}>
                    <div className="code-language">{block.language}</div>
                    <pre>
                      <code>
                        {block.code.split("\n").map((line, lineIndex) => (
                          <span className="code-line" key={lineIndex}>
                            <span className="line-number">{lineIndex + 1}</span>
                            <span>{line || " "}</span>
                          </span>
                        ))}
                      </code>
                    </pre>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-result">
                <strong>No code block was detected.</strong>
                <span>Try a PDF with selectable text. Scanned documents need OCR.</span>
              </div>
            )
          ) : (
            <div className="empty-result">
              <span>Upload a PDF to view extracted code.</span>
            </div>
          )}

          {result?.extracted_text && (
            <details className="source-text">
              <summary>View extracted document text</summary>
              <pre>{result.extracted_text}</pre>
            </details>
          )}
        </section>

        <footer className="page-footer">
          <span>PDF code extraction</span>
          <span>Files are not stored</span>
        </footer>
      </main>
    </div>
  );
}

export default App;
