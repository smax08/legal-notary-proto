# backend/main.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import shutil, uuid, json, io, os
import pytesseract
from PIL import Image
import qrcode
import numpy as np
import cv2
import face_recognition
import shutil as sh

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
GENERATED_DIR = BASE_DIR / "generated"
UPLOAD_DIR.mkdir(exist_ok=True)
GENERATED_DIR.mkdir(exist_ok=True)

# try to find tesseract automatically; allow override via env var TESSERACT_CMD
tesseract_cmd = os.getenv("TESSERACT_CMD") or sh.which("tesseract")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

app = FastAPI(title="Legal Notary Prototype (OCR + QR improvements)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def preprocess_image_bytes(image_bytes: bytes, target_width=1200):
    """
    Input: raw image bytes
    Output: PIL Image suitable for pytesseract after preprocessing
    Steps: decode -> convert gray -> upscale if small -> denoise -> threshold (Otsu)
    """
    # decode to numpy array
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR
    if img is None:
        raise ValueError("Could not decode image bytes")

    # convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # upscale if width < target_width for better OCR
    h, w = gray.shape
    if w < target_width:
        scale = target_width / float(w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # denoise & smooth a bit
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # adaptive threshold or Otsu threshold
    # first try Otsu:
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # if resulting text looks inverted (light text on dark bg), invert
    # compute mean and if mean is dark, keep; else invert when needed
    if np.mean(th) < 127:
        th = cv2.bitwise_not(th)

    pil_img = Image.fromarray(th)
    return img, pil_img  # return original color (BGR) and processed PIL for OCR

@app.post("/upload/")
async def upload_document(file: UploadFile = File(...)):
    """
    Accepts image files (png/jpg/jpeg). Runs OCR and face detection.
    Returns: file_id, filename, ocr_text, faces_found, qr_url
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = Path(file.filename).name if file.filename else f"{uuid.uuid4()}.jpg"
    file_bytes = await file.read()

    # save raw upload for later retrieval (optional)
    file_id = str(uuid.uuid4())
    ext = Path(filename).suffix or ".jpg"
    dest_name = f"{file_id}{ext}"
    dest_path = UPLOAD_DIR / dest_name
    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    # OCR preprocessing + extraction
    ocr_text = ""
    try:
        orig_cv_img, prepped_pil = preprocess_image_bytes(file_bytes)
        # Use configuration: OEM 3 (default neural), PSM 6 = assume a single uniform block of text
        config = "--oem 3 --psm 6"
        # If you need Hindi + English: use lang='eng+hin' (ensure traineddata installed)
        ocr_text = pytesseract.image_to_string(prepped_pil, config=config)
    except Exception as e:
        ocr_text = f"[OCR error] {e}"

    # Face detection using face_recognition on RGB image
    faces_found = 0
    try:
        # convert orig_cv_img (BGR) -> RGB
        rgb = cv2.cvtColor(orig_cv_img, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb, model="hog")  # or model="cnn" if GPU/installed
        faces_found = len(face_locations)
    except Exception:
        faces_found = 0

    # Create QR containing only minimal metadata (keeps the QR small)
    metadata = {"id": file_id, "filename": filename, "faces": faces_found}
    qr = qrcode.QRCode(box_size=3, border=2)  # smaller box_size -> smaller raw QR image
    qr.add_data(json.dumps(metadata))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Resize QR to a reasonable fixed pixel size (for display / printing)
    qr_final_size = (300, 300)  # pixels; change to 200 if you want smaller
    qr_img = qr_img.resize(qr_final_size, Image.NEAREST)

    qr_name = f"{file_id}_qr.png"
    qr_path = UPLOAD_DIR / qr_name
    qr_img.save(qr_path, format="PNG")

    # Return full QR URL (absolute) so frontend just uses it
    qr_url = f"http://127.0.0.1:8000/file/{qr_name}"

    return JSONResponse({
        "file_id": file_id,
        "filename": filename,
        "ocr_text": ocr_text,
        "faces_found": faces_found,
        "qr_url": qr_url
    })

@app.get("/file/{filename}")
async def serve_file(filename: str):
    fpath = UPLOAD_DIR / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(fpath)

# Simple document generator (keeps small QR too)
@app.post("/generate/")
async def generate_document(doc_type: str = Form(...), owner_name: str = Form(...), property_address: str = Form("")):
    doc_id = str(uuid.uuid4())
    if doc_type.lower() not in {"sale_deed", "will"}:
        raise HTTPException(status_code=400, detail="Unsupported document type")

    if doc_type.lower() == "sale_deed":
        content = (f"SALE DEED\n\nDocument ID: {doc_id}\nOwner: {owner_name}\nProperty Address: {property_address}\n\n"
                   "This is a prototype document.")
    else:
        content = (f"LAST WILL AND TESTAMENT\n\nDocument ID: {doc_id}\nTestator: {owner_name}\n\n"
                   "This is a prototype document.")

    out_path = GENERATED_DIR / f"{doc_id}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    # QR for document
    metadata = {"doc_id": doc_id, "type": doc_type, "owner": owner_name}
    qr = qrcode.QRCode(box_size=3, border=2)
    qr.add_data(json.dumps(metadata))
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((300, 300), Image.NEAREST)
    qr_name = f"{doc_id}_qr.png"
    qr_img.save(GENERATED_DIR / qr_name)

    return JSONResponse({
        "doc_id": doc_id,
        "download": f"http://127.0.0.1:8000/generated/{out_path.name}",
        "qr": f"http://127.0.0.1:8000/generated/{qr_name}"
    })

@app.get("/generated/{filename}")
async def serve_generated(filename: str):
    fpath = GENERATED_DIR / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(fpath)

