---
name: pdf-tools
description: Work with PDF files. Use when user wants to extract text, merge PDFs, or manipulate PDF documents.
---

# PDF Tools Skill

This skill provides instructions for working with PDF files.

## Setup

Install pdftk and other PDF utilities:

```bash
# Debian/Ubuntu
sudo apt-get install pdftk

# macOS
brew install pdftk-java
```

## Extract Text from PDF

Use pdftotext to extract text:

```bash
pdftotext input.pdf output.txt
```

To preserve layout:

```bash
pdftotext -layout input.pdf output.txt
```

## Merge PDFs

Combine multiple PDFs:

```bash
pdftk file1.pdf file2.pdf cat output merged.pdf
```

## Split PDF

Extract specific pages:

```bash
# Extract pages 1-5
pdftk input.pdf cat 1-5 output output.pdf

# Extract single page
pdftk input.pdf cat 7 output page7.pdf
```

## Get PDF Info

```bash
pdfinfo input.pdf
```

## Common Patterns

- Always check if the PDF is scanned (image-based) vs text-based
- For scanned PDFs, use OCR tools like tesseract first
- Use relative paths from the skill directory for any helper scripts
