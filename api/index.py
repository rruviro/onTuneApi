from flask import Flask, jsonify, request
import logging
import re
import json
import requests
from bs4 import BeautifulSoup
import yt_dlp
import urllib.parse
from pydub import AudioSegment
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Use the API key directly
API_KEY = 'AIzaSyC_dbpXvWmDjWCAjM1VLrgJFwyeaQPnGyg'
# Build the YouTube client
youtube = build('youtube', 'v3', developerKey=API_KEY)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    return response

def get_playlist_info(playlist_id):
    try:
        playlist_items = []
        next_page_token = None

        while True:
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            playlist_items.extend(playlist_response['items'])
            next_page_token = playlist_response.get('nextPageToken')

            if not next_page_token:
                break

        song_info = []
        for item in playlist_items:
            video = item['snippet']
            song_info.append({
                'title': video['title'],
                'writer': video['videoOwnerChannelTitle'],
                'url': f"https://www.youtube.com/watch?v={video['resourceId']['videoId']}",
                'image_url': video['thumbnails']['high']['url'],
            })

        return {
            'songCount': len(song_info),
            'songInfo': song_info
        }
    except HttpError as e:
        logging.error(f"YouTube API error: {str(e)}")
        return {'error': f'YouTube API error: {str(e)}'}

def extract_playlist_id(url):
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.hostname in ('youtube.com', 'www.youtube.com', 'music.youtube.com'):
        query = urllib.parse.parse_qs(parsed_url.query)
        return query.get('list', [None])[0]
    return None

@app.route('/playlist', methods=['GET'])
def playlist_info_endpoint():
    try:
        with open('api/links.txt', 'r') as file:
            playlist_urls = [line.strip() for line in file.readlines()]
    except Exception as e:
        logging.error(f"Failed to read links.txt: {str(e)}")
        return jsonify({'error': f'Failed to read links.txt: {str(e)}'}), 500

    if not playlist_urls:
        return jsonify({'error': 'No playlist URLs found in links.txt'}), 400

    all_songs_info = []
    for playlist_url in playlist_urls:
        playlist_id = extract_playlist_id(playlist_url)
        if playlist_id:
            result = get_playlist_info(playlist_id)
            if isinstance(result, dict) and 'songInfo' in result:
                all_songs_info.extend(result['songInfo'])
            elif 'error' in result:
                logging.error(f"Error processing playlist {playlist_url}: {result['error']}")
        else:
            logging.error(f"Invalid playlist URL: {playlist_url}")

    return jsonify({
        'songCount': len(all_songs_info),
        'songInfo': all_songs_info
    })


def clean_title_and_writer(title, writer):
    """Clean and preprocess title and writer for better display."""
    def remove_parentheses(text):
        return re.sub(r'\s*\(.*?\)\s*', '', text).strip()

    def remove_symbols(text):
        return re.sub(r'[^A-Za-z0-9 ]', '', text).strip()

    def remove_text_before_dash(text):
        return text.split("-", 1)[-1].lstrip() if "-" in text else text

    def remove_writer_from_title(title, writer):
        writer_escaped = re.escape(writer)
        return re.sub(r'\b' + writer_escaped + r'\b', '', title).strip()

    title = remove_parentheses(title)
    writer = remove_parentheses(writer)
    title = remove_text_before_dash(title)
    title = remove_writer_from_title(title, writer)
    title = remove_symbols(title)

    return title, writer

def extract_video_id(url):
    """Extract the video ID from a YouTube URL."""
    from urllib.parse import urlparse, parse_qs
    parsed_url = urlparse(url)
    if parsed_url.hostname in ('youtu.be', 'www.youtu.be'):
        return parsed_url.path[1:]
    if parsed_url.hostname in ('youtube.com', 'www.youtube.com', 'music.youtube.com'):
        return parse_qs(parsed_url.query).get('v', [None])[0]
    return None

def fetch_video_metadata(video_id):
    """Fetch video metadata using the YouTube Data API."""
    try:
        response = youtube.videos().list(
            part='snippet,contentDetails',
            id=video_id
        ).execute()

        if not response['items']:
            return None

        snippet = response['items'][0]['snippet']
        content_details = response['items'][0]['contentDetails']

        return {
            'title': snippet['title'],
            'uploader': snippet['channelTitle'],
            'duration': content_details['duration']
        }
    except Exception as e:
        print(f"YouTube API error: {str(e)}")
        return None

def download_audio(video_url):
    """Download audio from YouTube using youtube-dl."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
    }

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            audio_url = info_dict.get('url', None)

            if not audio_url:
                return {'error': 'Failed to extract audio URL.'}

            title = info_dict.get('title', "Unknown Title")
            uploader = info_dict.get('uploader', "Unknown Uploader")

            return {
                'audioUrl': audio_url,
                'title': title,
                'uploader': uploader
            }

    except Exception as e:
        return {'error': f'Error: {str(e)}'}
@app.route('/get-audio', methods=['GET'])
def get_audio():
    video_url = request.args.get('url')
    if not video_url:
        return jsonify({'error': 'Missing video URL parameter'}), 400

    print(f"Received video URL: {video_url}")
    video_id = extract_video_id(video_url)
    print(f"Extracted Video ID: {video_id}")

    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        # Fetch video metadata (optional)
        video_metadata = fetch_video_metadata(video_id)
        print(f"Video Metadata: {video_metadata}")
        if not video_metadata:
            return jsonify({'error': 'Failed to retrieve video metadata'}), 500

        # Download and convert the audio
        audio_info = download_audio(video_url)
        if 'error' in audio_info:  # Check if an error occurred during download
            return jsonify(audio_info), 500

        return jsonify({
            'audioUrl': audio_info['audioUrl'],  # Stream URL for audio
            'audioFilePath': audio_info['audioFilePath'],  # Path to the downloaded MP3
            'title': video_metadata['title'],
            'writer': video_metadata['uploader'],
            'duration': video_metadata['duration']
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'error': f'Error processing request: {str(e)}'}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
