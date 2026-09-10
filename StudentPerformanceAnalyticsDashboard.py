"""
Student Performance Analytics Dashboard
----------------------------------------
A Flask web app that lets a user upload a CSV of student records and
instantly view performance statistics (subject-wise averages, top
performers, and grade distribution) computed with Pandas and NumPy.
Each upload is also logged to a SQLite database for reference.

Expected CSV columns: name, subject, score   (one row per student per subject)
Example:
    name,subject,score
    Asha,Math,88
    Asha,Science,76
    Ravi,Math,64
    Ravi,Science,91
"""

import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # needed for flash messages

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")
ALLOWED_EXTENSIONS = {"csv"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def init_db():
    """Create the uploads table on startup if it doesn't already exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            row_count INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_upload(filename, row_count):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO uploads (filename, uploaded_at, row_count) VALUES (?, ?, ?)",
        (filename, datetime.now().isoformat(timespec="seconds"), row_count),
    )
    conn.commit()
    conn.close()


def get_upload_history(limit=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT filename, uploaded_at, row_count FROM uploads ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def grade_from_score(score):
    """Simple grade bands used for the grade-distribution stat."""
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"


def analyze_dataframe(df):
    """
    Takes a DataFrame with columns: name, subject, score
    Returns a dict of computed statistics using Pandas/NumPy.
    """
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df = df.dropna(subset=["score"])

    # Subject-wise averages (vectorized groupby, not a manual loop)
    subject_avg = df.groupby("subject")["score"].mean().round(2).to_dict()

    # Overall stats via NumPy
    overall_avg = round(float(np.mean(df["score"])), 2)
    overall_std = round(float(np.std(df["score"])), 2)

    # Top performers by average score across all their subjects
    student_avg = df.groupby("name")["score"].mean().round(2)
    top_performers = student_avg.sort_values(ascending=False).head(5).to_dict()

    # Grade distribution
    df["grade"] = df["score"].apply(grade_from_score)
    grade_counts = df["grade"].value_counts().to_dict()

    return {
        "subject_avg": subject_avg,
        "overall_avg": overall_avg,
        "overall_std": overall_std,
        "top_performers": top_performers,
        "grade_counts": grade_counts,
        "total_records": len(df),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    history = get_upload_history()
    return render_template("index.html", results=None, history=history)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        flash("No file part in the request.")
        return redirect(url_for("home"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.")
        return redirect(url_for("home"))

    if not allowed_file(file.filename):
        flash("Please upload a .csv file.")
        return redirect(url_for("home"))

    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    try:
        df = pd.read_csv(filepath)
        required_cols = {"name", "subject", "score"}
        if not required_cols.issubset(set(df.columns.str.lower())):
            flash(f"CSV must contain columns: {', '.join(required_cols)}")
            return redirect(url_for("home"))

        df.columns = df.columns.str.lower()
        results = analyze_dataframe(df)
        log_upload(file.filename, results["total_records"])

    except Exception as e:
        flash(f"Could not process file: {e}")
        return redirect(url_for("home"))

    history = get_upload_history()
    return render_template("index.html", results=results, history=history)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
