from flask import Flask, render_template, request, send_file, redirect, url_for
import os
import sqlite3
import json
from datetime import datetime
from fpdf import FPDF
from analyzer import extract_text_from_pdf, analyze_resume

app = Flask(__name__)
DB_FILE = "history.db"
latest_batch_cache = {}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            job_title TEXT,
            match_score TEXT,
            timestamp TEXT,
            summary TEXT,
            matches TEXT,
            misses TEXT,
            suggestions TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Helper function to sanitize text and break long unspaced string tokens to prevent FPDF space crashes
def sanitize_text(text):
    if not text:
        return "None"
    # Convert non-latin characters/emojis to standard text safely
    clean = text.encode('latin-1', 'ignore').decode('latin-1')
    words = clean.split(' ')
    processed_words = []
    for word in words:
        # If any single string token has no spaces and is longer than 40 chars, split it
        if len(word) > 40:
            word = word[:37] + "..."
        processed_words.append(word)
    return " ".join(processed_words)

def save_to_history(filename, job_title, match_score, summary, matches, misses, suggestions):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('''
        INSERT INTO analysis_history (filename, job_title, match_score, timestamp, summary, matches, misses, suggestions)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, job_title, match_score, current_time, summary, 
          json.dumps(matches), json.dumps(misses), json.dumps(suggestions)))
    conn.commit()
    conn.close()

def get_all_history():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, filename, job_title, match_score, timestamp FROM analysis_history ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    return rows

def generate_pdf_file(score, summary, matches, misses, suggestions, custom_title=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    title_text = custom_title if custom_title else "AI Resume Matcher Evaluation Report"
    pdf.set_font("Helvetica", style="B", size=18)
    pdf.cell(190, 10, txt=sanitize_text(title_text), ln=True, align='C')
    pdf.set_font("Helvetica", size=10)
    pdf.cell(190, 10, txt=f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(190, 10, txt=f"Overall Match Score: {score}", ln=True)
    pdf.set_font("Helvetica", style="I", size=11)
    pdf.multi_cell(190, 6, txt=f"Summary: {sanitize_text(summary)}")
    pdf.ln(5)
    
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(190, 10, txt="Verified Keywords Matched:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(190, 6, txt=sanitize_text(", ".join(matches)))
    pdf.ln(5)
    
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(190, 10, txt="Critical Skills Missing:", ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(190, 6, txt=sanitize_text(", ".join(misses)))
    pdf.ln(5)
    
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(190, 10, txt="Strategic Action Items:", ln=True)
    pdf.set_font("Helvetica", size=11)
    for sug in suggestions:
        pdf.multi_cell(190, 6, txt=f"- {sanitize_text(sug)}")
        pdf.ln(2)
        
    path = "Generated_Report.pdf"
    pdf.output(path)
    return path

init_db()

@app.route('/')
def home():
    history_data = get_all_history()
    return render_template('index.html', history=history_data)

@app.route('/analyze', methods=['POST'])
def handle_analysis():
    global latest_batch_cache
    if request.method == 'POST':
        job_desc = request.form['job_description']
        files = request.files.getlist('resume')
        
        if not files or files[0].filename == '':
            return "<h3>⚠️ Error: No files selected!</h3>"

        results_list = []
        latest_batch_cache = {}
        guessed_title = job_desc.strip().split("\n")[0][:50]

        for file in files:
            temp_path = os.path.join(".", file.filename)
            file.save(temp_path)
            
            resume_text = extract_text_from_pdf(temp_path)
            if len(resume_text.strip()) == 0:
                os.remove(temp_path)
                continue

            ai_result = analyze_resume(resume_text, job_desc)
            os.remove(temp_path)
            
            score = "0%"
            summary = ""
            matched_skills = []
            missing_skills = []
            suggestions = []
            
            current_section = None
            for line in ai_result.split("\n"):
                line_str = line.strip()
                if not line_str: continue
                
                if "[SCORE]" in line_str: current_section = "score"
                elif "[SUMMARY]" in line_str: current_section = "summary"
                elif "[MATCHED KEYWORDS]" in line_str: current_section = "matches"
                elif "[MISSING KEYWORDS]" in line_str: current_section = "misses"
                elif "[IMPROVEMENT SUGGESTIONS]" in line_str: current_section = "suggestions"
                else:
                    if current_section == "score": score = line_str
                    elif current_section == "summary": summary += line_str + " "
                    elif current_section == "matches": matched_skills = [s.strip() for s in line_str.split(",") if s.strip()]
                    elif current_section == "misses": missing_skills = [s.strip() for s in line_str.split(",") if s.strip()]
                    elif current_section == "suggestions": suggestions.append(line_str.lstrip("*- "))

            save_to_history(file.filename, guessed_title, score, summary, matched_skills, missing_skills, suggestions)
            
            try: numeric_score = int(score.replace('%', '').strip())
            except ValueError: numeric_score = 0

            candidate_data = {
                "filename": file.filename,
                "score_str": score,
                "score_num": numeric_score,
                "summary": summary,
                "matches": matched_skills,
                "misses": missing_skills,
                "suggestions": suggestions
            }
            results_list.append(candidate_data)
            latest_batch_cache[file.filename] = candidate_data

        results_list = sorted(results_list, key=lambda x: x['score_num'], reverse=True)
        return render_template('result.html', results=results_list, is_multiple=len(results_list) > 1)

@app.route('/download_single_batch/<filename>')
def download_single_batch(filename):
    global latest_batch_cache
    cand = latest_batch_cache.get(filename)
    if not cand:
        return f"Report data for {filename} unavailable.", 400
        
    pdf_path = generate_pdf_file(
        cand['score_str'], cand['summary'], cand['matches'], cand['misses'], cand['suggestions'],
        custom_title=f"Evaluation Report: {filename}"
    )
    return send_file(pdf_path, as_attachment=True, download_name=f"Report_{filename}.pdf")

# --- ROUTE: DOWNLOAD MASTER CONDENSED BATCH REPORT ---
@app.route('/download_consolidated')
def download_consolidated():
    global latest_batch_cache
    if not latest_batch_cache:
        return "No batch run records available to condense.", 400
        
    pdf = FPDF()
    pdf.add_page()
    
    # Page 1: Cover / Executive Overview
    pdf.set_font("Helvetica", style="B", size=20)
    pdf.cell(190, 15, txt="Executive Batch Alignment Summary", ln=True, align='C')
    pdf.set_font("Helvetica", size=11)
    pdf.cell(190, 10, txt=f"Evaluation Matrix Run: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(190, 10, txt="Ranked Overview Performance Table:", ln=True)
    pdf.ln(2)
    
    # Table Header (Explicit horizontal constraints)
    pdf.set_font("Helvetica", style="B", size=11)
    pdf.cell(140, 8, "Candidate Document Name", border=1)
    pdf.cell(50, 8, "Match Alignment Score", border=1, ln=True)
    
    pdf.set_font("Helvetica", size=11)
    sorted_items = sorted(latest_batch_cache.values(), key=lambda x: x['score_num'], reverse=True)
    
    for idx, cand in enumerate(sorted_items):
        display_name = f"#{idx+1} - {cand['filename']}"
        if len(display_name) > 45:
            display_name = display_name[:42] + "..."
            
        pdf.cell(140, 8, sanitize_text(display_name), border=1)
        pdf.cell(50, 8, f"   {cand['score_str']}", border=1, ln=True)
        
    # Append individual deep-dives
    for cand in sorted_items:
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=16)
        
        clean_fname = cand['filename'] if len(cand['filename']) < 40 else cand['filename'][:37] + "..."
        pdf.cell(190, 10, txt=f"Candidate Profile: {sanitize_text(clean_fname)}", ln=True)
        
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(190, 8, txt=f"Evaluation Result: {cand['score_str']}", ln=True)
        pdf.ln(4)
        
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(190, 6, txt="Executive Core Summary:", ln=True)
        pdf.set_font("Helvetica", style="I", size=11)
        pdf.multi_cell(190, 6, txt=sanitize_text(cand['summary']))
        pdf.ln(4)
        
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(190, 6, txt="Identified Gaps:", ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(190, 6, txt=f"Missing Skills: {sanitize_text(', '.join(cand['misses']))}")
        pdf.ln(4)
        
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(190, 6, txt="Top Core Improvement Suggestions:", ln=True)
        pdf.set_font("Helvetica", size=11)
        for sug in cand['suggestions']:
            if sug.strip():
                # Using multi_cell here guarantees that long sentences wrap completely to the next line safely
                pdf.multi_cell(190, 6, txt=f"- {sanitize_text(sug)}")
                pdf.ln(1)
            
    path = "Consolidated_Batch_Report.pdf"
    pdf.output(path)
    return send_file(path, as_attachment=True, download_name="Consolidated_Batch_Report.pdf")

@app.route('/download_past/<int:record_id>')
def download_past(record_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT match_score, summary, matches, misses, suggestions, filename FROM analysis_history WHERE id = ?', (record_id,))
    row = cursor.fetchone()
    conn.close()
    if not row: return "Not found.", 404
    score, summary, matches_j, misses_j, suggestions_j, fname = row
    pdf_path = generate_pdf_file(score, summary, json.loads(matches_j), json.loads(misses_j), json.loads(suggestions_j), custom_title=f"Evaluation Report: {fname}")
    return send_file(pdf_path, as_attachment=True, download_name=f"Past_Report_{record_id}.pdf")

@app.route('/delete_record/<int:record_id>')
def delete_record(record_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM analysis_history WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, port=8080)