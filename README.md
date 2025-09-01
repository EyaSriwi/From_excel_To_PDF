📝 Lettre de Liaison Generator - CF MAIER ITAP

Python GUI application to generate medical liaison letters in PDF for CF MAIER ITAP. Supports employee search, PDF preview, and automated record keeping.

✨ Features

Load and normalize employee data from CSV

Autocomplete search by Matricule or Nom & Prénom

Generate PDF letters with company logo and hospital info

Preview PDF in-app

Save letters to a base Excel file to prevent duplicates

🛠️ Tech Stack

Python 3.8+

Tkinter – GUI interface

Pandas – CSV & Excel data manipulation

Pillow (PIL) – Image handling for logos & PDF preview

ReportLab – PDF generation

PyMuPDF (fitz) – PDF preview as image

OpenPyXL – Read/write Excel files

📂 Project Structure
lettre_liaison/
│
├── Requirement/
│   ├── lll.CSV
│   ├── logo.jpg
│   ├── logo.png
│   ├── cachet.png
│   └── Base_LettreLiaison.xlsx
│
├── main.py
└── README.md

⚙️ Requirements

CSV file (lll.CSV) and images (logo.jpg/png, cachet.png) in Requirement folder

Python libraries: pandas, pillow, reportlab, pymupdf, openpyxl
