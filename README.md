# PDF code extraction

This starter implements the first three requested pipeline areas:

0. **Frontend:** React submission workspace with PDF upload and extracted-content review.
1. **Input ingestion:** FastAPI endpoint using PyMuPDF to read PDF text and page count.
2. **Answer/code extraction:** Label-based section detection, fenced/labelled and whole-document code detection, repeated watermark cleanup, and conservative text normalization.

The current extraction is local and rule-based; it does not call an LLM and does not yet perform OCR. Uploaded files are processed in memory and are not persisted. Scanned PDFs without selectable text return a warning.

## Run locally

Start the API in one terminal:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8011
```

Start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal (usually `http://localhost:5173`). The development server proxies `/api` requests to FastAPI on port 8011.

Run the backend tests from `backend`:

```powershell
python -m pytest
```

## Extraction behavior

The API accepts PDF files at `POST /api/extract` (maximum 20 MB). It returns the page count, extracted text, detected question/rubric/answer-key/student-answer sections, and code blocks. Section detection recognizes common headings such as `Question:`, `Rubric:`, `Answer Key:`, and `Student Answer:`, including headings split across lines. Repeated, visually watermark-like registration numbers are filtered from extracted text. Code fences and labelled code are preferred; un-fenced code is also detected in the answer section or, when no answer section is found, across the document.
