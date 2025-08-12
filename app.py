import os
import io
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
import tempfile
from datetime import datetime

# Import all your existing modules
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains.summarize import load_summarize_chain
from langchain_core.documents import Document
from urllib.parse import urlparse, parse_qs

# Google imports
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Gemini import
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'your_secret_key_change_this'  # Change this to a random secret key

# Your existing configuration
from dotenv import load_dotenv
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
SERVICE_ACCOUNT_EMAIL = os.getenv("SERVICE_ACCOUNT_EMAIL")
EXISTING_DOCUMENT_ID = os.getenv("EXISTING_DOCUMENT_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/youtube.readonly']
USE_METHOD = "share_with_service"
    
# Your existing functions (keeping them exactly the same)
def setup_google_services():
    """Initialize Google services"""
    try:   
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        docs_service = build('docs', 'v1', credentials=credentials)
        drive_service = build('drive', 'v3', credentials=credentials)
        return docs_service, drive_service, credentials
    except FileNotFoundError:
        return None, None, None
    except Exception as e:
        return None, None, None

def format_transcript_for_docs(transcript_text):
    """Format transcript with proper line breaks for Google Docs"""
    try:
        lines = transcript_text.strip().split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if line:
                formatted_lines.append(line)
        formatted_transcript = '\n\n'.join(formatted_lines)
        return formatted_transcript
    except Exception as e:
        return transcript_text

def create_formatted_content(summary, video_url, transcript_text, video_info):
    """Create properly formatted content for Google Docs"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_transcript = format_transcript_for_docs(transcript_text)
    
    content_parts = [
        f"{video_info['title']}\n",
        "\nVideo Details:",
        f"├─ Title: {video_info['title']}",
        f"├─ Video ID: {video_info['id']}",
        f"├─ URL: {video_url}",
        f"└─ Generated: {timestamp}\n",
        "\n═══════════════════════════════════════════════════════════════\n",
        "\n🤖 AI SUMMARY\n",
        f"{summary}\n",
        "\n═══════════════════════════════════════════════════════════════\n",
        "\n📝 FULL TRANSCRIPT\n",
        f"{formatted_transcript}\n",
        "\n═══════════════════════════════════════════════════════════════"
    ]
    
    content = '\n'.join(content_parts)
    return content

def method1_create_via_drive(drive_service, docs_service, title, content):
    """Create via Drive with proper formatting"""
    try:
        file_metadata = {
            'name': title,
            'mimeType': 'application/vnd.google-apps.document'
        }
        
        file = drive_service.files().create(body=file_metadata).execute()
        doc_id = file.get('id')
        
        requests = [
            {
                'insertText': {
                    'location': {'index': 1},
                    'text': content
                }
            }
        ]
        
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={'requests': requests}).execute()
        
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return doc_id, doc_url
    except HttpError as error:
        return None, None
    except Exception as e:
        return None, None

def method2_update_shared_doc(docs_service, doc_id, content):
    """Update shared doc with proper formatting"""
    try:
        doc = docs_service.documents().get(documentId=doc_id).execute()
        content_length = doc.get('body').get('content')[-1].get('endIndex')
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_content = f"\n\n--- Updated on {timestamp} ---\n\n{content}\n"
        
        requests = [
            {
                'insertText': {
                    'location': {'index': content_length - 1},
                    'text': new_content
                }
            }
        ]
        
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={'requests': requests}).execute()
        
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return doc_id, doc_url
    except HttpError as error:
        return None, None
    except Exception as e:
        return None, None

def create_local_file(summary, video_url, transcript_text, video_info):
    """Create local file content and return file path"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{video_info['clean_title']}_{timestamp}.txt"
        
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(os.getcwd(), 'temp_files')
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        filepath = os.path.join(temp_dir, filename)
        content = create_formatted_content(summary, video_url, transcript_text, video_info)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return filepath, filename
    except Exception as e:
        return None, None

def get_video_title(video_id):
    """Get video title"""
    try:
        if YOUTUBE_API_KEY:
            youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
            request = youtube.videos().list(part='snippet', id=video_id)
            response = request.execute()
            
            if response.get('items'):
                title = response['items'][0]['snippet']['title']
                return title
        
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        video_data = transcript_list.video_data
        if video_data:
            return video_data['title']
        
        return f"YouTube Video - {video_id}"
    except Exception as e:
        return f"YouTube Video - {video_id}"

def get_video_info(video_id):
    """Get complete video info"""
    try:
        video_title = get_video_title(video_id)
        # Clean title more aggressively for filename safety
        clean_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_title = clean_title.replace(' ', '_')  # Replace spaces with underscores
        clean_title = clean_title[:30]  # Shorter length for better compatibility
        
        return {
            'title': video_title,
            'clean_title': clean_title,
            'id': video_id
        }
    except Exception as e:
        return {
            'title': f"YouTube Video - {video_id}",
            'clean_title': f"YouTube_Video_{video_id}",
            'id': video_id
        }

def extract_video_id(youtube_url):
    """Extract video ID"""
    parsed_url = urlparse(youtube_url)
    if parsed_url.hostname in ["www.youtube.com", "youtube.com"]:
        return parse_qs(parsed_url.query).get("v", [None])[0]
    elif parsed_url.hostname == "youtu.be":
        return parsed_url.path.lstrip("/")
    return None

def summarize_with_gemini(transcript_text):
    """Gemini fallback"""
    try:
        if not GEMINI_AVAILABLE:
            return None, "Gemini library not installed"
        
        if not GEMINI_API_KEY:
            return None, "Gemini API key not provided"
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Please write a concise summary of the following YouTube video transcript:
        
        {transcript_text}
        
        Summary:
        """
        
        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text.strip(), None
        else:
            return None, "Gemini returned empty response"
    except Exception as e:
        return None, f"Gemini error: {e}"

def simple_extractive_summary(transcript_text):
    """Simple extractive"""
    try:
        sentences = transcript_text.replace('\n', ' ').split('. ')
        sentences = [s.strip() + '.' for s in sentences if s.strip()]
        
        total_sentences = len(sentences)
        if total_sentences <= 5:
            summary_sentences = sentences
        else:
            start_sentences = sentences[:2]
            middle_start = total_sentences // 3
            middle_sentences = sentences[middle_start:middle_start + 2]
            end_sentences = sentences[-2:]
            summary_sentences = start_sentences + middle_sentences + end_sentences
        
        summary = ' '.join(summary_sentences)
        return summary, None
    except Exception as e:
        return None, f"Simple summary error: {e}"

def get_transcript(youtube_url):
    """Extract transcript from YouTube URL"""
    try:
        video_id = extract_video_id(youtube_url)
        if not video_id:
            return None, "Failed to extract video ID"
        
        ytt_api = YouTubeTranscriptApi()
        fetched_transcript = ytt_api.fetch(video_id)
        full_text = "\n".join([snippet.text for snippet in fetched_transcript])
        
        return full_text, None
    except Exception as e:
        return None, f"Error extracting transcript: {e}"

def generate_summary(transcript_text):
    """Generate summary with fallback methods"""
    try:
        # Try OpenAI first
        llm = ChatOpenAI(
            temperature=0.7, 
            model_name="gpt-3.5-turbo",
            openai_api_key=OPENAI_API_KEY
        )
        
        prompt_template = PromptTemplate.from_template(
            "Write a concise summary of the following YouTube video transcript:\n\n{text}"
        )
        
        chain = load_summarize_chain(llm, chain_type="stuff", prompt=prompt_template)
        doc = Document(page_content=transcript_text)
        result = chain.invoke([doc])
        summary = result['output_text'] if 'output_text' in result else str(result)
        
        return summary, None
    except Exception as e:
        # Try Gemini fallback
        summary, error = summarize_with_gemini(transcript_text)
        if summary:
            return summary, None
        
        # Try simple extractive fallback
        summary, error = simple_extractive_summary(transcript_text)
        if summary:
            return summary, None
        
        return None, "All summary methods failed"

def save_to_google_docs(summary, video_url, transcript_text):
    """Try to save to Google Docs"""
    docs_service, drive_service, credentials = setup_google_services()
    
    if not docs_service or not drive_service:
        return None, None, "Google services not available"
    
    video_id = extract_video_id(video_url)
    video_info = get_video_info(video_id)
    content = create_formatted_content(summary, video_url, transcript_text, video_info)
    
    # Try different methods
    if USE_METHOD == "drive_then_docs":
        title = f"{video_info['clean_title']} - {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        doc_id, doc_url = method1_create_via_drive(drive_service, docs_service, title, content)
        if doc_id:
            return doc_id, doc_url, None
    
    elif USE_METHOD == "share_with_service" and EXISTING_DOCUMENT_ID:
        doc_id, doc_url = method2_update_shared_doc(docs_service, EXISTING_DOCUMENT_ID, content)
        if doc_id:
            return doc_id, doc_url, None
    
    return None, None, "Google Docs methods failed"

# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/summarize', methods=['POST'])
def summarize():
    try:
        youtube_url = request.form.get('youtube_url', '').strip()
        
        if not youtube_url:
            return jsonify({'error': 'Please provide a YouTube URL'})
        
        # Extract transcript
        transcript, error = get_transcript(youtube_url)
        if error:
            return jsonify({'error': f'Transcript extraction failed: {error}'})
        
        # Generate summary
        summary, error = generate_summary(transcript)
        if error:
            return jsonify({'error': f'Summary generation failed: {error}'})
        
        # Try to save to Google Docs
        doc_id, doc_url, docs_error = save_to_google_docs(summary, youtube_url, transcript)
        
        # Always create local file for download
        video_id = extract_video_id(youtube_url)
        video_info = get_video_info(video_id)
        filepath, filename = create_local_file(summary, youtube_url, transcript, video_info)
        
        if not filepath:
            return jsonify({'error': 'Failed to create download file'})
        
        # Prepare response
        response_data = {
            'success': True,
            'video_title': video_info['title'],
            'video_id': video_id,
            'summary': summary,
            'transcript_length': len(transcript),
            'download_filename': filename,
            'google_docs_status': 'success' if doc_id else 'failed',
            'google_docs_url': doc_url if doc_url else None,
            'google_docs_error': docs_error if docs_error else None
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'})

@app.route('/download/<path:filename>')
def download_file(filename):
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        safe_filename = secure_filename(decoded_filename)
        
        temp_dir = os.path.join(os.getcwd(), 'temp_files')
        
        # Try multiple filename variations
        possible_files = [
            os.path.join(temp_dir, safe_filename),
            os.path.join(temp_dir, decoded_filename),
            os.path.join(temp_dir, filename)
        ]
        
        # Also check for files in the directory that contain similar names
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                if safe_filename in file or decoded_filename in file:
                    possible_files.append(os.path.join(temp_dir, file))
        
        # Try each possible file path
        for filepath in possible_files:
            if os.path.exists(filepath):
                return send_file(filepath, as_attachment=True, download_name=safe_filename)
        
        # If no file found, list available files for debugging
        available_files = []
        if os.path.exists(temp_dir):
            available_files = os.listdir(temp_dir)
        
        return jsonify({
            'error': 'File not found',
            'requested': decoded_filename,
            'available_files': available_files
        }), 404
        
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

# Add a route to list available files for debugging
@app.route('/list_files')
def list_files():
    try:
        temp_dir = os.path.join(os.getcwd(), 'temp_files')
        if os.path.exists(temp_dir):
            files = []
            for file in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, file)
                file_info = {
                    'name': file,
                    'size': os.path.getsize(filepath),
                    'modified': datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                }
                files.append(file_info)
            return jsonify({'files': files})
        else:
            return jsonify({'files': [], 'message': 'temp_files directory does not exist'})
    except Exception as e:
        return jsonify({'error': f'Error listing files: {str(e)}'})

# Add a direct download route that handles file creation if needed
@app.route('/download_direct', methods=['POST'])
def download_direct():
    try:
        data = request.get_json()
        summary = data.get('summary')
        video_url = data.get('video_url')
        transcript = data.get('transcript')
        video_info = data.get('video_info')
        
        if not all([summary, video_url, transcript, video_info]):
            return jsonify({'error': 'Missing required data'}), 400
        
        # Create file directly
        filepath, filename = create_local_file(summary, video_url, transcript, video_info)
        
        if filepath and os.path.exists(filepath):
            return send_file(filepath, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': 'Failed to create download file'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Direct download failed: {str(e)}'}), 500

if __name__ == '__main__':
    # Create temp directory if it doesn't exist
    temp_dir = os.path.join(os.getcwd(), 'temp_files')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    app.run(debug=True, host='0.0.0.0', port=5000)