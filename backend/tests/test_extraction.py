import pymupdf as fitz

from main import extract_code_blocks, extract_sections, normalize_text, parse_pdf


def test_normalize_text_preserves_indentation_and_cleans_pdf_artifacts():
    assert normalize_text("  def main():\r\n\u200b    print('ok')\u00a0") == (
        "  def main():\n    print('ok')"
    )


def test_extract_sections_reads_expected_submission_labels():
    sections = extract_sections(
        "Question:\nWrite a function.\n\nRubric:\nCorrectness: 5\n\n"
        "Student Answer:\ndef add(a, b):\n    return a + b"
    )
    assert sections["question"] == "Write a function."
    assert sections["rubric"] == "Correctness: 5"
    assert sections["student_answer"] == "def add(a, b):\n    return a + b"


def test_extract_sections_handles_wrapped_and_inline_headings():
    sections = extract_sections(
        "Question: Add two numbers.\nStudent\nAnswer:\ndef add(a, b):\n    return a + b"
    )

    assert sections["question"] == "Add two numbers."
    assert sections["student_answer"] == "def add(a, b):\n    return a + b"


def test_extract_code_from_fenced_answer_and_remove_common_indent():
    blocks = extract_code_blocks(
        "Student Answer:\n```python\n    def add(a, b):\n        return a + b\n```",
        "```python\n    def add(a, b):\n        return a + b\n```",
    )
    assert blocks == [{"language": "python", "code": "def add(a, b):\n    return a + b"}]


def test_extract_code_prefers_student_answer_over_reference_code():
    text = (
        "Answer Key:\n```python\nreference_solution()\n```\n"
        "Student Answer:\n```python\nstudent_solution()\n```"
    )
    sections = extract_sections(text)

    assert extract_code_blocks(text, sections["student_answer"]) == [
        {"language": "python", "code": "student_solution()"}
    ]


def test_parse_pdf_returns_structured_sections_and_code():
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(
        fitz.Rect(40, 40, 560, 780),
        "Question:\nWrite a function.\n\nStudent Answer:\n"
        "```python\n\ndef add(a, b):\n    return a + b\n```",
    )
    pdf_bytes = document.tobytes()
    document.close()

    result = parse_pdf(pdf_bytes)
    assert result["page_count"] == 1
    assert result["sections"]["question"] == "Write a function."
    assert result["code_blocks"][0]["language"] == "python"
    assert "def add" in result["code_blocks"][0]["code"]


def test_parse_pdf_extracts_unfenced_code_from_page_with_repeated_watermark():
    document = fitz.open()
    page = document.new_page()
    for point in ((160, 110), (310, 220), (460, 330)):
        page.insert_text(point, "25BCE4323", fontsize=28, color=(0.8, 0.8, 0.8), rotate=90)
    page.insert_text((72, 470), "def calculate_total(items):", fontsize=11)
    page.insert_text((92, 490), "    total = 0", fontsize=11)
    page.insert_text((92, 510), "    for item in items:", fontsize=11)
    page.insert_text((112, 530), "        total += item", fontsize=11)
    page.insert_text((92, 550), "    return total", fontsize=11)
    pdf_bytes = document.tobytes()
    document.close()

    result = parse_pdf(pdf_bytes)

    assert "25BCE4323" not in result["extracted_text"]
    assert result["code_blocks"] == [
        {
            "language": "python",
            "code": (
                "def calculate_total(items):\n"
                "    total = 0\n"
                "    for item in items:\n"
                "        total += item\n"
                "    return total"
            ),
        }
    ]
