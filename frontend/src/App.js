// frontend/src/App.js
import React, { useState } from "react";
import axios from "axios";

function App() {
  const [file, setFile] = useState(null);
  const [uploadRes, setUploadRes] = useState(null);
  const [docType, setDocType] = useState("sale_deed");
  const [ownerName, setOwnerName] = useState("");
  const [propertyAddress, setPropertyAddress] = useState("");

  const onFileChange = (e) => {
    setFile(e.target.files[0]);
    setUploadRes(null);
  };

  const upload = async () => {
    if (!file) return alert("Choose a file first");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await axios.post("http://127.0.0.1:8000/upload/", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setUploadRes(res.data);
    } catch (err) {
      alert("Upload failed: " + (err.response?.data?.detail || err.message));
    }
  };

  const generate = async () => {
    if (!ownerName) return alert("Provide owner/testator name");
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("owner_name", ownerName);
    form.append("property_address", propertyAddress);
    try {
      const res = await axios.post("http://127.0.0.1:8000/generate/", form);
      const data = res.data;
      alert("Document generated.\nDownload: " + data.download + "\nQR: " + data.qr);
    } catch (err) {
      alert("Generate failed: " + (err.response?.data?.detail || err.message));
    }
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h2>Legal Notary Prototype — Frontend</h2>

      <section style={{ marginBottom: 20 }}>
        <h4>Upload & Verify Document</h4>
        <input type="file" accept="image/*" onChange={onFileChange} />
        <button onClick={upload} style={{ marginLeft: 8 }}>
          Upload
        </button>

        {uploadRes && (
          <div style={{ marginTop: 12 }}>
            <div><strong>File ID:</strong> {uploadRes.file_id}</div>
            <div><strong>Filename:</strong> {uploadRes.filename}</div>
            <div><strong>Faces found:</strong> {uploadRes.faces_found}</div>
            <div style={{ marginTop: 8 }}>
              <strong>OCR text (truncated):</strong>
              <pre style={{ whiteSpace: "pre-wrap", maxHeight: 160, overflow: "auto" }}>
                {uploadRes.ocr_text ? uploadRes.ocr_text.slice(0, 1000) : "(no text extracted)"}
              </pre>
            </div>

            <div style={{ marginTop: 8 }}>
              <strong>QR:</strong>
              <div>
                {/* Use the full QR URL returned by backend */}
                <img
                  alt="qr"
                  src={uploadRes.qr_url}
                  style={{ width: 150, height: 150, objectFit: "contain", border: "1px solid #ddd" }}
                />
              </div>
            </div>
          </div>
        )}
      </section>

      <section>
        <h4>Generate Document</h4>
        <label>Type: </label>
        <select value={docType} onChange={(e) => setDocType(e.target.value)}>
          <option value="sale_deed">Sale Deed</option>
          <option value="will">Will</option>
        </select>
        <div style={{ marginTop: 8 }}>
          <input placeholder="Owner / Testator name" value={ownerName} onChange={(e) => setOwnerName(e.target.value)} />
        </div>
        <div style={{ marginTop: 8 }}>
          <input placeholder="Property Address (if sale deed)" value={propertyAddress} onChange={(e) => setPropertyAddress(e.target.value)} />
        </div>
        <button onClick={generate} style={{ marginTop: 10 }}>Generate</button>
      </section>
    </div>
  );
}

export default App;


