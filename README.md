# 🎯 YT-DocSummarizer

A Flask-based web application that:
- Extracts transcripts from YouTube videos
- Generates concise AI-powered summaries (OpenAI + Gemini fallback)
- Saves summaries to Google Docs or downloads locally
- Supports multiple summarization methods (LLM, Gemini, extractive)

---

## 🚀 Features
- **YouTube Transcript Extraction** using `youtube-transcript-api`
- **AI Summarization** with OpenAI GPT-3.5 Turbo, Gemini 1.5 Flash, or simple extractive fallback
- **Google Docs Integration** (Service Account support)
- **Download as TXT** with clean formatting
- Fully responsive web UI using Flask templates

---

## 🛠️ Tech Stack
- **Backend:** Flask (Python)
- **AI:** OpenAI API, Gemini API
- **Integrations:** Google Docs API, Google Drive API, YouTube Data API
- **Frontend:** HTML, CSS (Flask Jinja Templates)

---

## 📦 Installation
# Clone repository
git clone https://github.com/divyadarji/YT-DocSummarizer.git
cd YT-DocSummarizer

# Create and activate venv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file and add your keys
OPENAI_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
YOUTUBE_API_KEY=your_key_here
SERVICE_ACCOUNT_FILE=path/to/service_account.json
SERVICE_ACCOUNT_EMAIL=your_service_email
EXISTING_DOCUMENT_ID=optional_doc_id

# Run application
python app.py
