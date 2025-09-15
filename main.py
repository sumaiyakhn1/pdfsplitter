from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import tempfile, os, zipfile, re, shutil
from PyPDF2 import PdfReader, PdfWriter

app = FastAPI()

# Allow Lovable / localhost for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def split_and_zip_bytes(file_bytes, pattern):
    # write uploaded bytes to a temp pdf
    temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_pdf.write(file_bytes)
    temp_pdf.close()

    output_dir = tempfile.mkdtemp()
    saved_files = []

    reader = PdfReader(temp_pdf.name)
    for i, page in enumerate(reader.pages, start=1):
        writer = PdfWriter()
        writer.add_page(page)
        text = page.extract_text() or ""
        match = re.search(pattern, text, re.IGNORECASE)
        name = match.group(1) if match else f"unknown_{i}"
        out_path = os.path.join(output_dir, f"{name}.pdf")
        with open(out_path, "wb") as f:
            writer.write(f)
        saved_files.append(out_path)

    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(zip_fd)
    with zipfile.ZipFile(zip_path, "w") as zf:
        for fpath in saved_files:
            zf.write(fpath, os.path.basename(fpath))

    # cleanup
    try:
        os.remove(temp_pdf.name)
        shutil.rmtree(output_dir)
    except:
        pass

    return zip_path

@app.post("/split-pdf/")
async def split_pdf(file: UploadFile, pattern: str = Form(...)):
    """
    Upload PDF + regex pattern (example: 'Roll No\.?\s*(\d+)')
    """
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Only PDF allowed"}, status_code=400)
    data = await file.read()
    try:
        zip_path = split_and_zip_bytes(data, pattern)
        return FileResponse(zip_path, filename="dmc_split.zip")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
