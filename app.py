from flask import Flask, request, jsonify
import yt_dlp
import requests
import os

app = Flask(__name__)


def get_captions(info):
    """Return English captions as plain text, or None if unavailable."""
    caps = info.get("subtitles", {}).get("en") or info.get("automatic_captions", {}).get("en")
    if not caps:
        return None
    vtt_url = next((c["url"] for c in caps if c.get("ext") == "vtt"), caps[0]["url"])
    raw = requests.get(vtt_url, timeout=15).text
    lines = [
        line.strip() for line in raw.splitlines()
        if line.strip() and "-->" not in line
        and not line.strip().isdigit() and not line.startswith("WEBVTT")
    ]
    return " ".join(dict.fromkeys(lines))  # de-dupe repeated caption lines


@app.route("/extract", methods=["POST"])
def extract():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "missing 'url' in request body"}), 400

    is_youtube = "youtube.com" in url or "youtu.be" in url

    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": f"could not read this link: {e}"}), 422

    title = info.get("title", "")

    if is_youtube:
        transcript = get_captions(info)
        if transcript:
            return jsonify({"title": title, "mode": "text", "transcript": transcript})

    # No captions available (or not YouTube) -> hand back a direct audio URL for Whisper
    try:
        with yt_dlp.YoutubeDL({"format": "bestaudio/best", "quiet": True}) as ydl:
            audio_info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": f"could not resolve audio: {e}"}), 422

    return jsonify({"title": title, "mode": "audio", "audio_url": audio_info.get("url")})


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
