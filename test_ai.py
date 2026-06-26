import pypdf
from google import genai

# 1. Reuse our function to read the PDF text
def extract_text_from_pdf(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

# 2. Extract the text from your uploaded document
pdf_file_name = "sample_resume.pdf"
document_text = extract_text_from_pdf(pdf_file_name)

# 3. Create a fake Job Description to test the matching ability
fake_job_description = """
We are looking for a Software Engineering Intern who has hands-on experience building projects with Python. 
The ideal candidate should understand relational databases, SQL, and basic HTML. 
Strong problem-solving skills and experience with version control (Git) are highly preferred.
"""

print("Analyzing document with Gemini AI... Please wait...")

# 4. Initialize the AI client and send the data
client = genai.Client()

prompt = f"""
You are an expert HR recruiter and career coach. 
Compare the following Resume Text against the Job Description.

Resume Text:
{document_text}

Job Description:
{fake_job_description}

Please provide your evaluation in this exact format:
1. MATCH SCORE: (Give a percentage score out of 100 based on keyword overlap and skills)
2. KEYWORDS MATCHED: (List key technical terms found in both)
3. MISSING KEYWORDS: (List critical skills from the job description missing in the resume)
4. IMPROVEMENT SUGGESTIONS: (Give 2-3 specific bullet points on how to improve this resume for this job)
"""

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=prompt,
)

print("\n================ AI ANALYSIS RESULT ================\n")
print(response.text)
print("====================================================")