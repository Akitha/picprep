import io
import os
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file
from PIL import Image

import config

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max upload

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def optimize_image(img, max_w, max_h, quality, fmt):
    """Resize to fit within max dimensions and compress for web."""
    img = img.convert("RGB")
    img.thumbnail((max_w, max_h), Image.LANCZOS)

    buf = io.BytesIO()
    if fmt == "webp":
        img.save(buf, format="WEBP", quality=quality, method=4)
    else:
        img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    buf.seek(0)
    return buf


def create_thumbnail(img, thumb_w, thumb_h, quality, fmt, bg_color):
    """Create a centered thumbnail on a solid background."""
    img = img.convert("RGB")

    # Scale image to fit inside thumbnail bounds
    ratio = min(thumb_w / img.width, thumb_h / img.height)
    new_w = int(img.width * ratio)
    new_h = int(img.height * ratio)
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Create background canvas and paste centered
    canvas = Image.new("RGB", (thumb_w, thumb_h), bg_color)
    offset_x = (thumb_w - new_w) // 2
    offset_y = (thumb_h - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))

    buf = io.BytesIO()
    if fmt == "webp":
        canvas.save(buf, format="WEBP", quality=quality, method=4)
    else:
        canvas.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    buf.seek(0)
    return buf


@app.route("/")
def index():
    return render_template("index.html", config=config)


@app.route("/process", methods=["POST"])
def process():
    files = request.files.getlist("images")
    if not files or files[0].filename == "":
        return "No files selected", 400

    # Read form params with defaults
    orig_prefix = request.form.get("orig_prefix", config.ORIGINAL_PREFIX).strip()
    thumb_prefix = request.form.get("thumb_prefix", config.THUMBNAIL_PREFIX).strip()
    try:
        start_num = int(request.form.get("start_number", "1"))
    except ValueError:
        start_num = 1

    thumb_w = int(request.form.get("thumb_width", config.THUMBNAIL_WIDTH))
    thumb_h = int(request.form.get("thumb_height", config.THUMBNAIL_HEIGHT))
    orig_quality = int(request.form.get("orig_quality", config.ORIGINAL_QUALITY))
    thumb_quality = int(request.form.get("thumb_quality", config.THUMBNAIL_QUALITY))
    max_width = int(request.form.get("max_width", config.MAX_ORIGINAL_WIDTH))
    max_height = int(request.form.get("max_height", config.MAX_ORIGINAL_HEIGHT))
    fmt = request.form.get("format", config.OUTPUT_FORMAT)
    if fmt not in ("jpg", "webp"):
        fmt = "jpg"

    ext = "webp" if fmt == "webp" else "jpg"
    bg_color = config.BACKGROUND_COLOR

    # Build zip in memory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, f in enumerate(files):
            if not f or not f.filename or not allowed_file(f.filename):
                continue

            num = start_num + i
            num_str = str(num)
            orig_name = f"{orig_prefix}{num_str}" if orig_prefix else num_str
            thumb_name = f"{thumb_prefix}{num_str}" if thumb_prefix else num_str

            img = Image.open(f.stream)

            # Optimized original
            orig_buf = optimize_image(
                img,
                max_width,
                max_height,
                orig_quality,
                fmt,
            )
            zf.writestr(f"originals/{orig_name}.{ext}", orig_buf.read())

            # Thumbnail
            thumb_buf = create_thumbnail(img, thumb_w, thumb_h, thumb_quality, fmt, bg_color)
            zf.writestr(f"thumbnails/{thumb_name}.{ext}", thumb_buf.read())

    zip_buf.seek(0)
    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="picprep_output.zip",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
