# app.py
from flask import Flask, request, jsonify, render_template
from resume_analyzer import analyze_resume_file
import os

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    return render_template("upload.html")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """
    Endpoint:
    - resume_file: file
    - job_description: optional text
    Returns JSON with all scoring components.
    """
    if "resume_file" not in request.files:
        return jsonify({"error": "Missing resume file."}), 400

    uploaded_file = request.files["resume_file"]
    job_desc = request.form.get("job_description", "")

    file_bytes = uploaded_file.read()
    filename = uploaded_file.filename or "resume"

    result = analyze_resume_file(file_bytes, filename, job_desc)
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
