from flask import Flask, render_template, request, jsonify
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

app = Flask(__name__)

# Gemini API setup
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent" 

# Predefined structured questions for certain roles
structured_questions = {
    "machine learning engineer": [
        # Easy
        "What is Machine Learning?",
        "What are the types of Machine Learning?",
        "Explain supervised vs unsupervised learning.",
        
        # Medium
        "What is overfitting? How can you reduce it?",
        "What is cross-validation? Why is it important?",
        "Explain precision and recall.",

        # Hard
        "How do you handle imbalanced datasets?",
        "Explain gradient descent and its variants.",
        "What is regularization? Why is it used?",
    ],
    "software engineer": [
        # Easy
        "What is an API?",
        "What's the difference between GET and POST?",
        "Explain event-driven programming.",
        
        # Medium
        "What is closure in JavaScript?",
        "Explain the call stack and event loop.",
        "What is memoization and how does it work?",

        # Hard
        "What is currying in functional programming?",
        "Explain deadlock and race condition.",
        "Describe CAP theorem and its implications.",
    ],
}

# Track previously asked questions and difficulty level
previous_questions = []
question_levels = ["basic", "intermediate", "advanced"]
current_level_index = 0


def generate_gemini_content(prompt):
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    params = {
        "key": GEMINI_API_KEY
    }

    try:
        response = requests.post(GEMINI_API_URL, json=data, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"Error: {response.status_code}, {response.text}"
    except Exception as e:
        return f"Request failed: {str(e)}"


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/interview")
def interview_page():
    return render_template("interview.html")


@app.route("/validate-role", methods=["POST"])
def validate_role():
    data = request.get_json()
    role = data.get("role")
    job_desc = data.get("jobDescription")

    prompt = f"""
    You are an AI assistant checking whether the job description matches the given role.

    Role: {role}
    Job Description: {job_desc}

    Respond with only "MATCH" if the job description clearly relates to the role.
    Otherwise, respond with "NO MATCH".
    """

    result = generate_gemini_content(prompt)
    return jsonify({"match": result.strip().upper() == "MATCH"})

@app.route("/generate-question", methods=["POST"])
def generate_question():
    global previous_questions, current_level_index

    data = request.get_json()
    role = data.get("role", "").strip().lower()
    job_desc = data.get("jobDescription")

    # Try to get structured question first
    structured_q_list = structured_questions.get(role, None)

    if structured_q_list and len(previous_questions) < len(structured_q_list):
        question = structured_q_list[len(previous_questions)]
        previous_questions.append(question)
        return jsonify({"question": question})

    # If no structured questions, fall back to Gemini
    current_level = question_levels[current_level_index]
    prev_q_str = ", ".join(previous_questions) if previous_questions else "None"

    prompt = f"""
    You are an interviewer conducting mock interviews for a {role} position.
    
    Based on this job description:
    {job_desc}
    
    Ask one short, realistic, and common interview question at the "{current_level}" level.

    DO NOT repeat these previous questions: {prev_q_str}

    Keep it simple and conversational. One question only.
    """

    question = generate_gemini_content(prompt)

    if "Error" not in question and question.strip() not in previous_questions:
        previous_questions.append(question.strip())

        # Move to next difficulty every 3 unique questions
        if len(previous_questions) % 3 == 0 and current_level_index < len(question_levels) - 1:
            current_level_index += 1

    return jsonify({"question": question})


@app.route("/evaluate-answer", methods=["POST"])
def evaluate_answer():
    data = request.get_json()
    answer = data.get("answer")
    question = data.get("question")

    prompt = f"""
    Evaluate the following interview answer.

    Question: {question}
    Candidate Answer: {answer}

    Please provide:
    1. One-sentence summary of how well they answered
    2. A better version of the answer (keep it natural and conversational)
    3. Use <mark> tags around parts that were improved

    Format your response as:
    
    Feedback: [How well the user answered]
    Suggestion: [Highlight improvements with <mark>]</mark>
    Better Answer: [Improved full answer]

    Keep each part on a new line. No markdown or extra formatting.
    """

    evaluation = generate_gemini_content(prompt)

    # Split into lines for structured display
    feedback_parts = evaluation.split('\n')

    return jsonify({
        "evaluation": evaluation,
        "parts": {
            "Feedback": feedback_parts[0].replace("Feedback: ", ""),
            "Suggestion": feedback_parts[1].replace("Suggestion: ", ""),
            "BetterAnswer": feedback_parts[2].replace("Better Answer: ", "")
        }
    })

@app.route("/calculate-performance", methods=["POST"])
def calculate_performance():
    data = request.get_json()
    chat_log = data.get("chatLog", [])  # Array of {text, sender}

    if not chat_log:
        return jsonify({"error": "No chat log provided"}), 400

    # Extract only bot questions and user answers
    evaluation_pairs = []
    i = 0
    while i < len(chat_log):
        if chat_log[i]["sender"] == "bot" and i+1 < len(chat_log) and chat_log[i+1]["sender"] == "user":
            question = chat_log[i]["text"]
            answer = chat_log[i+1]["text"]
            evaluation_pairs.append((question, answer))
            i += 2
        else:
            i += 1

    if not evaluation_pairs:
        return jsonify({"error": "No valid Q&A pairs found"}), 400

    # Build prompt for Gemini
    prompt = """
    You are an AI Interview Coach. Analyze the following interview session and provide:

    For each question-answer pair:
      - Was the answer correct? (Yes / Partially / No)
      - Feedback on what was good or missing
      - A better version of the answer
    
    Then provide:
      1. Overall score out of 10
      2. Strengths of the candidate
      3. Areas to improve (list at least 2)
      4. Suggested topics to study

    Format your response EXACTLY like this:

    === EVALUATION ===
    Question: [Question]
    Candidate Answer: [Answer]
    Correctness: [Yes / Partially / No]
    Feedback: [Feedback]
    Better Answer: [Improved full answer]

    ...

    === SUMMARY ===
    Score: [score]
    Strengths: [comma-separated list]
    AreasToImprove: [comma-separated list]
    TopicsToStudy: [comma-separated list]

    Questions and Answers:
    """

    for q, a in evaluation_pairs:
        prompt += f"\nQuestion: {q}\nAnswer: {a}\n"

    gemini_response = generate_gemini_content(prompt)

    try:
        lines = gemini_response.strip().split('\n')
        evaluations = []
        summary = {}

        section = None
        current_eval = {}

        for line in lines:
            if line.startswith("==="):
                if "SUMMARY" in line:
                    section = "summary"
                else:
                    section = "eval"
                    if current_eval:
                        evaluations.append(current_eval)
                        current_eval = {}
            elif section == "eval" and ": " in line:
                key, val = line.split(": ", 1)
                current_eval[key.strip()] = val.strip()
            elif section == "summary" and ": " in line:
                key, val = line.split(": ", 1)
                summary[key.strip()] = val.strip()

        if current_eval:
            evaluations.append(current_eval)

        return jsonify({
            "success": True,
            "performance": {
                "details": evaluations,
                "summary": summary
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "raw": gemini_response
        })

if __name__ == "__main__":
    app.run(debug=True)
