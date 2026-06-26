import pypdf
from google import genai

def extract_text_from_pdf(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

def analyze_resume(resume_text, job_description):
    client = genai.Client()
    
    prompt = f"""
    You are an expert HR recruiter. Analyze the Resume Text against the Job Description.

    === JOB DESCRIPTION ===
    {job_description}

    === RESUME TEXT ===
    {resume_text}

    === INSTRUCTIONS ===
    Provide an evaluation matching the following keys exactly. 
    Do not use markdown formatting (like asterisks **) in the lists.
    
    [SCORE]
    Provide only a percentage number (e.g., 85%)
    
    [SUMMARY]
    Provide a concise 1-2 sentence high-level summary of the match assessment.
    
    [MATCHED KEYWORDS]
    Provide a comma-separated list of technical skills/keywords found in both.
    
    [MISSING KEYWORDS]
    Provide a comma-separated list of critical skills from the job description missing in the resume.
    
    [IMPROVEMENT SUGGESTIONS]
    Provide 2-3 specific bullet points on how to improve this resume for this job.
    """
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    return response.text