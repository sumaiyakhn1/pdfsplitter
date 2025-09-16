from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import tempfile, os, zipfile, re, shutil
from PyPDF2 import PdfReader, PdfWriter
import pandas as pd
from io import BytesIO

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def split_and_zip_with_excel(file_bytes, df, reg_pattern, reg_col, target_col):
    # Create temp PDF
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_pdf.write(file_bytes)
    temp_pdf.close()

    # Strip column names
    df.columns = df.columns.str.strip()

    # Check required columns
    expected_columns = [reg_col, target_col]
    missing = [col for col in expected_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Available columns: {list(df.columns)}")

    # Create mapping dictionary
    mapping = dict(zip(df[reg_col].astype(str).str.strip(), df[target_col].astype(str).str.strip()))

    # Output directory
    output_dir = tempfile.mkdtemp()
    saved_files = []

    # Read PDF pages
    reader = PdfReader(temp_pdf.name)
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        text = page.extract_text() or ""

        # Extract registration number using regex
        match = re.search(reg_pattern, text, re.IGNORECASE)
        if match:
            reg_no = match.group(1).strip()
        else:
            reg_no = f"unknown_{i}"

        # Get mapped name or fallback
        new_name = mapping.get(reg_no, reg_no)
        out_path = os.path.join(output_dir, f"{new_name}.pdf")

        with open(out_path, "wb") as f:
            writer.write(f)
        saved_files.append(out_path)

    # Create ZIP
    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(zip_fd)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for fpath in saved_files:
            zf.write(fpath, os.path.basename(fpath))

    # Clean up temp files
    try:
        os.remove(temp_pdf.name)
        shutil.rmtree(output_dir)
    except:
        pass

    return zip_path


@app.post("/split-and-rename/")
async def split_and_rename(
    file: UploadFile,
    excel: UploadFile,
    reg_pattern: str = Form(..., description="Regex with capturing group e.g. (24-RK-\\d+)"),
    reg_col: str = Form(..., description="Excel column name for Registration No."),
    target_col: str = Form(..., description="Excel column name for College Roll No.")
):
    # Validate uploaded files
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF allowed"}, status_code=400)
    if not (excel.filename.lower().endswith(".xlsx") or excel.filename.lower().endswith(".xls")):
        return JSONResponse({"error": "Only Excel files allowed"}, status_code=400)

    try:
        # Read PDF bytes
        pdf_data = await file.read()

        # Read Excel directly from memory with correct engine
        excel_bytes = await excel.read()
        excel_stream = BytesIO(excel_bytes)

        if excel.filename.lower().endswith(".xlsx"):
            df = pd.read_excel(excel_stream, engine="openpyxl")
        else:
            df = pd.read_excel(excel_stream, engine="xlrd")

        # Split PDF and zip
        zip_path = split_and_zip_with_excel(pdf_data, df, reg_pattern, reg_col, target_col)
        return FileResponse(zip_path, filename="renamed_split_pdfs.zip")

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
