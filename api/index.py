import sys
import json
import re
import requests
from pytube import YouTube
from flask import Flask, jsonify, make_response, request
import logging
import subprocess
import urllib.parse  # For URL decoding

app = Flask(__name__)

# Setting up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

# Flask Route to get audio from YouTube video
@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')  # Get the video URL from the query parameter

    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    # Decode the URL in case it has special characters
    decoded_url = urllib.parse.unquote(video_url)

    # Strip query parameters that could cause issues
    base_video_url = strip_query_parameters(decoded_url)

    result = download_audio_with_pytube(base_video_url)
    return jsonify(result)

def strip_query_parameters(url):
    """
    Strips query parameters from the URL (e.g., list=..., start_radio=...)
    to avoid issues with pytube.
    """
    return url.split('?')[0]

# Function to download audio from YouTube using pytube
def download_audio_with_pytube(video_url):
    try:
        yt = YouTube(video_url)
        
        # Extracting audio stream
        stream = yt.streams.filter(only_audio=True, file_extension='mp4').first()
        audio_file = stream.download(output_path='/tmp', filename='audio.mp4')  # Download as mp4
        
        # Convert to mp3 using ffmpeg
        mp3_path = audio_file.replace(".mp4", ".mp3")
        subprocess.run(['ffmpeg', '-i', audio_file, mp3_path])

        # Extracting title and writer (uploader)
        title = yt.title
        writer = yt.author

        return {
            'audioUrl': mp3_path,
            'title': title,
            'writer': writer
        }
    except Exception as e:
        return {'error': f'Error downloading audio: {str(e)}'}

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
