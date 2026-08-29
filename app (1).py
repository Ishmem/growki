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


def detect_platform(url):
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    if "instagram.com" in url:
        return "Instagram"
    if "tiktok.com" in url:
        return "TikTok"
    if "facebook.com" in url or "fb.watch" in url:
        return "Facebook"
    return "Other"


@app.route("/extract", methods=["POST"])
def extract():
    # Always returns HTTP 200, even on failure — the "mode" field (text /
    # audio / error) is what Make's router branches on, so a 4xx/5xx here
    # would just make the HTTP module itself fail instead of routing cleanly.
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url:
        return jsonify({"mode": "error", "title": "", "platform": "", "message": "missing 'url' in request body"}), 200

    platform = detect_platform(url)

    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"mode": "error", "title": "", "platform": platform, "message": f"could not read this link: {e}"}), 200

    title = info.get("title", "")

    if platform == "YouTube":
        transcript = get_captions(info)
        if transcript:
            return jsonify({"title": title, "mode": "text", "platform": platform, "transcript": transcript}), 200

    # No captions available (or not YouTube) -> hand back a direct audio URL for Whisper
    try:
        with yt_dlp.YoutubeDL({"format": "bestaudio/best", "quiet": True}) as ydl:
            audio_info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"mode": "error", "title": title, "platform": platform, "message": f"could not resolve audio: {e}"}), 200

    return jsonify({"title": title, "mode": "audio", "platform": platform, "audio_url": audio_info.get("url")}), 200


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
