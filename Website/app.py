# all necessary imports are listed below
from flask import Flask, render_template, jsonify, send_from_directory, request, send_file
import os, random, cv2, re, pywt, json
import numpy as np
from sklearn.cluster import KMeans
from skimage.feature import local_binary_pattern
from flask_cors import CORS
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import transforms, models
from PIL import Image
from datetime import datetime
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values
from collections import defaultdict 
from torchvision.models import VGG19_Weights
import joblib
import traceback
import h5py
from transformers import CLIPProcessor, CLIPModel
from sklearn.decomposition import PCA
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
import wordninja
from sentence_transformers import SentenceTransformer
import uuid

app = Flask(__name__)
BASE_PATH = os.environ.get("ARTRECSYS_BASE_PATH", "/artrecsys").rstrip("/")

class PrefixMiddleware:
    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        if self.prefix:
            path_info = environ.get("PATH_INFO", "")
            if path_info.startswith(self.prefix):
                environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
                environ["PATH_INFO"] = path_info[len(self.prefix):] or "/"
        return self.app(environ, start_response)


app.wsgi_app = PrefixMiddleware(app.wsgi_app, BASE_PATH)
DATASET_PATH = os.environ.get("ARTRECSYS_DATASET_PATH", os.getcwd())
app.secret_key = "secret"  # Needed for session storage
CORS(app)


def resolve_painting_path(image_path):
    paintings_dir = DATASET_PATH if DATASET_PATH.endswith("paintings") else os.path.join(DATASET_PATH, "paintings")
    normalized_path = image_path.lstrip("/\\")
    if normalized_path.startswith("paintings/"):
        normalized_path = normalized_path[len("paintings/"):]
    return os.path.join(paintings_dir, normalized_path)

all_images = [] # Collect all images

for root, dirs, files in os.walk(DATASET_PATH):
    for file in files:
        if file.lower().endswith((".jpg", ".jpeg", ".png")):
            rel_path = os.path.relpath(os.path.join(root, file), DATASET_PATH)
            all_images.append(rel_path.replace("\\", "/"))

@app.route("/")
def welcome():
    return render_template("welcome_page.html")

@app.route("/create_gallary")
def create_gallary():
    return render_template("create_gallary.html")

@app.route("/favourites")
def favourites():
    return render_template("favourites.html")

@app.route("/style_transfer")
def style_transfer():
    return render_template("style_transfer.html")

@app.route("/index")
def index():
    return render_template("index.html")

@app.route("/user_page")
def user_page():
    return render_template("user_page.html")

@app.route("/cold_start")
def cold_start():
    return render_template("cold_start.html")

# Database connection
def get_db_connection():
    db_password = os.environ.get("ARTRECSYS_DB_PASSWORD")
    db_password_file = os.environ.get("ARTRECSYS_DB_PASSWORD_FILE")

    if not db_password and db_password_file and os.path.exists(db_password_file):
        with open(db_password_file, "r", encoding="utf-8") as password_file:
            db_password = password_file.read().strip()

    conn = psycopg2.connect(
        host=os.environ.get("ARTRECSYS_DB_HOST", "artrecsys-db"),
        database=os.environ.get("ARTRECSYS_DB_NAME", "ART_RECSYS_DB"),
        user=os.environ.get("ARTRECSYS_DB_USER", "postgres"),
        password=db_password or "Catmelon304!"
    )
    return conn
print(get_db_connection())

# Helper Function for User IP address
# def get_user_ip():
#     """
#     Retrieve user's IP address from the request
#     """
#     # Handles proxy situations
#     if request.headers.get('X-Forwarded-For'):
#         ip = request.headers.get('X-Forwarded-For').split(',')[0]
#     else:
#         ip = request.remote_addr
#     return ip

# This function couldn't be used becuase a public IP is not a reliable device identifier
# due to NAT (multiple users behind one IP), mobile carrier gateways, VPNs, etc. 
# Using it as a proxy for “user/device” will systematically collapse distinct users into the same identity.

def get_client_id():
    return request.headers.get("X-User-ID")

# Check User
@app.route("/api/check_user", methods=["GET"])
def check_user():
    """
    Determine if user client ID already exists in database
    """
    try:
        client_id = get_client_id()

        if not client_id:
            return jsonify({"exists": False, "user_id": None})

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT user_id
            FROM users
            WHERE client_id = %s
        """

        cursor.execute(query, (client_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            return jsonify({
                "exists": True,
                "user_id": result[0]
            })
        else:
            return jsonify({
                "exists": False,
                "user_id": None
            })

    except Exception as e:
        print("ERROR in /api/check_user:", e)
        return jsonify({"error": str(e)}), 500
  
# Create User
@app.route("/api/create_user", methods=["POST"])
def create_user():
    """
    Create new user after consent accepted
    """  
    try:
        client_id = get_client_id()

        if not client_id:
            return jsonify({"success": False, "error": "Missing client_id"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO users (consent_form, client_id)
            VALUES (%s, %s)
            RETURNING user_id
        """

        cursor.execute(insert_query, (True, client_id))
        user_id = cursor.fetchone()[0]
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "user_id": user_id
        })

    except Exception as e:
        print("ERROR in /api/create_user:", e)
        return jsonify({"success": False, "error": str(e)}), 500

# Session Tracking
@app.route("/api/get_session", methods=["POST"])
def api_get_session():
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({"success": False}), 400

        session_id = get_or_create_session(user_id)

        return jsonify({
            "success": True,
            "session_id": session_id
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/end_session", methods=["POST"])
def end_session():
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"success": False, "error": "session_id required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE sessions
            SET session_end = CURRENT_TIMESTAMP
            WHERE session_id = %s AND session_end IS NULL
        """, (session_id,))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"success": False, "error": "Invalid or already ended"}), 400

        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("ERROR end_session:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/update_activity", methods=["POST"])
def update_activity():
    try:
        data = request.get_json()
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({"success": False}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            UPDATE sessions
            SET last_activity = CURRENT_TIMESTAMP
            WHERE session_id = %s AND session_end IS NULL
        """

        cursor.execute(query, (session_id,))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/validate_session", methods=["POST"])
def validate_session():
    data = request.get_json()
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"valid": False})

    valid = is_session_valid(session_id)

    return jsonify({"valid": valid})

def get_or_create_session(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Expire sessions older than 1 day 
    cursor.execute("""
        UPDATE sessions
        SET session_end = CURRENT_TIMESTAMP
        WHERE session_end IS NULL
        AND session_start < CURRENT_TIMESTAMP - INTERVAL '1 day'
    """)

    # Check for active session
    cursor.execute("""
        SELECT session_id
        FROM sessions
        WHERE user_id = %s
        AND session_end IS NULL
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()

    if row:
        session_id = row[0]
    else:
        cursor.execute("""
            INSERT INTO sessions (user_id, session_start, last_activity)
            VALUES (%s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING session_id
        """, (user_id,))

        session_id = cursor.fetchone()[0]

    conn.commit()
    cursor.close()
    conn.close()

    return session_id

def is_session_valid(session_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 1
        FROM sessions
        WHERE session_id = %s
        AND session_end IS NULL
        AND session_start >= CURRENT_TIMESTAMP - INTERVAL '1 day'
    """, (session_id,))

    valid = cursor.fetchone() is not None

    cursor.close()
    conn.close()

    return valid

EVENT_TYPES = {
    "view_start",
    "view_end",
    "click",
    "favourite",
    "save_gallary",
    "rating",
    "not_interested",
    "review",
    "skip"
}

def log_event(session_id, user_id, painting_id, event_type, event_value, request_id, metadata=None):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO interaction_events (session_id, user_id, painting_id, event_type, event_value, timestamp, request_id)
        VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        RETURNING event_id;
    """, (session_id, user_id, painting_id, event_type, event_value, request_id))

    event_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return event_id

def ensure_summary(session_id, user_id, painting_id, request_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO interaction_summary (session_id, user_id, painting_id, request_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (session_id, user_id, painting_id)
        DO NOTHING;
    """, (session_id, user_id, painting_id, request_id))

    conn.commit()
    cur.close()
    conn.close()

def update_summary(session_id, user_id, painting_id, event_type, value=None):
    conn = get_db_connection()
    cur = conn.cursor()

    if event_type == "view_end":
        cur.execute("""
            WITH last_start AS (
                SELECT timestamp
                FROM interaction_events
                WHERE session_id = %s
                AND user_id = %s
                AND painting_id = %s
                AND event_type = 'view_start'
                ORDER BY timestamp DESC
                LIMIT 1
            )
            UPDATE interaction_summary
            SET viewing_time_seconds = COALESCE(viewing_time_seconds, 0) +
                EXTRACT(EPOCH FROM (NOW() - (SELECT timestamp FROM last_start)))
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id,
            session_id, user_id, painting_id))

    elif event_type == "favourite":
        cur.execute("""
            UPDATE interaction_summary
            SET favourite = True
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "click":
        cur.execute("""
            UPDATE interaction_summary
            SET click = True
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "save_gallary":
        cur.execute("""
            UPDATE interaction_summary
            SET save_gallary = True
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "rating":
        cur.execute("""
            UPDATE interaction_summary
            SET rating = %s
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (value, session_id, user_id, painting_id))

    elif event_type == "not_interested":
        cur.execute("""
            UPDATE interaction_summary
            SET not_interested = True
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "review":
        cur.execute("""
            UPDATE interaction_summary
            SET review = %s
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (value, session_id, user_id, painting_id))

    conn.commit()
    cur.close()
    conn.close()

# Interaction Events Logging and Summary
@app.route("/api/interaction_event_logging", methods=["POST"])
def interaction_event_logging():
    try:
        data = request.json

        session_id = data.get("session_id")
        user_id = data.get("user_id")
        painting_id = data.get("painting_id")
        request_id = data.get("request_id")
        event_type = data.get("event_type")
        value = data.get("value")  

        if event_type not in EVENT_TYPES:
            return jsonify({"error": "Invalid event type"}), 400

        event_id = log_event(session_id, user_id, painting_id, event_type, value, request_id)
        ensure_summary(session_id, user_id, painting_id, request_id)
        update_summary(session_id, user_id, painting_id, event_type, value)

        return jsonify({
            "status": "success",
            "event_id": event_id
        })
    except Exception as e:
        print("ERROR:", e)   
        return jsonify({"error": str(e)}), 500

def fetch_user_interactions(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            r.painting_id,
            r.rank,

            MAX(s.viewing_time_seconds) AS viewing_time,
            MAX(s.rating) AS rating,
            BOOL_OR(s.favourite) AS favourite,
            BOOL_OR(s.not_interested) AS not_interested,
            BOOL_OR(s.save_to_gallary) AS save_to_gallery,
            BOOL_OR(s.click) AS click,
            MAX(s.review) AS review,

            CASE
                WHEN r.request_id IN (
                    SELECT DISTINCT r1.request_id
                    FROM recommendations r1
                    WHERE EXISTS (
                        SELECT 1
                        FROM recommendations r2
                        WHERE r2.user_id = r1.user_id
                        AND r2.created_at > r1.created_at
                    )
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM interaction_summary s2
                    WHERE s2.request_id = r.request_id
                    AND s2.painting_id = r.painting_id
                    AND (
                        s2.click = TRUE OR
                        s2.favourite = TRUE OR
                        s2.rating IS NOT NULL OR
                        s2.viewing_time_seconds > 2
                    )
                )
                THEN TRUE
                ELSE FALSE
            END AS skip

    FROM recommendations r
    LEFT JOIN interaction_summary s
        ON r.painting_id = s.painting_id
    AND r.user_id = s.user_id
    AND r.request_id = s.request_id

    WHERE r.user_id = %s

    GROUP BY r.painting_id, r.request_id, r.rank;
                """, (user_id,))
    rows = cur.fetchall()

    cur.close()
    conn.close()

    interactions = []

    for r in rows:
        interactions.append({
            "painting_id": r["painting_id"],
            "rank": r["rank"],
            "viewing_time": r["viewing_time"],
            "rating": r["rating"],
            "favourite": r["favourite"],
            "not_interested": r["not_interested"],
            "save_to_gallery": r["save_to_gallery"],
            "click": r["click"],
            "review": r["review"],
            "skip": r["skip"]
        })

    return interactions

# Get painting and artist metadata for each painting along with the image from the respective file path
@app.route("/api/random-images/<int:n>")
def random_images(n):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT painting_id, image_path
        FROM paintings
        
        LIMIT %s;
    """, (n,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)

def generate_request_id():
    return str(uuid.uuid4())

@app.route("/api/cold-start-images", methods=["POST"])
def cold_start_images():
    try:
        data = request.get_json()
        request_id  = generate_request_id()
        user_id = data.get("user_id")
        session_id = data.get("session_id")
        
        if not data:
            print("ERROR: No JSON body received")
            return jsonify({"success": False, "error": "No JSON body"}), 400

        concepts = data.get("concepts", []) 

        if not concepts:
            return jsonify({"success": False, "error": "No concepts provided"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Get top-k per concept
        concept_paintings = []

        for concept in concepts:
            concept_type = concept.get("type")
            label = concept.get("label")

            _, top_ids, scores = get_thumbnail_for_concept(cursor, concept_type, label, top_k=5)

            if not top_ids:
                continue

            cursor.execute("""
                SELECT painting_id, image_path
                FROM paintings_and_artists_metadata_bert
                WHERE painting_id = ANY(%s)
            """, (top_ids,))

            rows = cursor.fetchall()

            # shuffle per concept
            random.shuffle(rows)

            concept_paintings.append(rows)

        paintings = []
        seen = set()
        max_len = max(len(lst) for lst in concept_paintings)

        for i in range(max_len):
            for lst in concept_paintings:
                if i >= len(lst):
                    continue

                row = lst[i]
                pid = row["painting_id"]

                if pid in seen:
                    continue

                seen.add(pid)

                paintings.append({
                    "painting_id": pid,
                    "image_url": build_painting_url(row["image_path"]),
                    "request_id": request_id
                })

        execute_values(cursor, """
            INSERT INTO recommendations (
                session_id,
                user_id,
                painting_id,
                request_id,
                rank,
                score,
                created_at
            )
            VALUES %s
            ON CONFLICT DO NOTHING;
        """, [
            (
                session_id,
                user_id,
                p["painting_id"],
                request_id,
                rank,
                p.get("score", 0.0),
                datetime.utcnow()
            )
            for rank, p in enumerate(paintings)
        ])

        random.shuffle(paintings)
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "request_id": request_id,
            "paintings": paintings
        })

    except Exception as e:
        print("ERROR in /api/cold-start-images:")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/paintings/<path:filename>')
def serve_painting(filename):
    paintings_dir = os.path.join(DATASET_PATH, "paintings") if not DATASET_PATH.endswith("paintings") else DATASET_PATH
    return send_from_directory(
        paintings_dir,
        filename
    )

@app.route('/api/painting/<int:painting_id>')
def get_painting(painting_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT 
            p.painting_id,
            p.title,
            p.year_created,
            p.genre,
            p.art_style,
            p.media,
            p.description_tags,
            p.image_path,

            a.name_surname,
            a.birth_year,
            a.death_year,
            a.nationality,
            a.fields,
            a.art_movements,
            a.bio

        FROM paintings p
        JOIN artists a ON p.artist_id = a.artist_id
        WHERE p.painting_id = %s;
    """, (painting_id,))

    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return jsonify({"error": "Painting not found"}), 404

    cur.close()
    conn.close()

    image_path = resolve_painting_path(row["image_path"])
    image_path = image_path.replace("\\", "/")
    image = cv2.imread(image_path)
    if image is None:
        return jsonify({"error": "Image not found on server"}), 500
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    palette, palette_type = extract_visual_features(image_rgb)

    response = {
        "painting_id": row["painting_id"],
        "title": row["title"],
        "year_created": row["year_created"],
        "genre": row["genre"],
        "art_style": row["art_style"],
        "media": row["media"],
        "description_tags": row["description_tags"],
        "image_path": row["image_path"],

        "artist": {
            "name_surname": row["name_surname"],
            "birth_year": row["birth_year"],
            "death_year": row["death_year"],
            "nationality": row["nationality"],
            "fields": row["fields"],
            "art_movements": row["art_movements"],
            "bio": row["bio"]
        },

        "palette": palette.tolist(),
        "palette_type": palette_type
    }

    return jsonify(response)

@app.route('/api/add-favourite', methods=['POST'])
def add_favourite():
    data = request.get_json()
    painting_id = data.get("painting_id")
    user_id = data.get("user_id")

    print("user_id:", user_id)
    print("painting_id:", painting_id)

    if not painting_id or not user_id:
        return jsonify({"error": "Missing painting_id or user_id"}), 400

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO favourites (user_id, painting_id)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING;
    """, (user_id, painting_id))  

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Added to favourites"})

@app.route("/api/favourites", methods=["GET"])
def get_favourites():
    user_id = request.args.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT p.painting_id, p.image_path
            FROM favourites f
            JOIN paintings p ON f.painting_id = p.painting_id
            WHERE f.user_id = %s
        """, (user_id,))

        rows = cur.fetchall()

        favourites = [
            {
                "painting_id": row[0],
                "image_path": row[1]
            }
            for row in rows
        ]

        cur.close()
        conn.close()

        return jsonify({"favourites": favourites})

    except Exception as e:
        print("Error fetching favourites:", e)
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/gallary')
def get_gallery():
    import os
    from flask import jsonify
    directory = os.path.join(app.root_path, 'static', 'generated')
    files = [
        '/generated'
        for f in os.listdir(directory)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ]
    return jsonify(files)

# folder for saving generated results
paintings_dir = DATASET_PATH if DATASET_PATH.endswith("paintings") else os.path.join(DATASET_PATH, "paintings")
GENERATED_DIR = os.path.join(paintings_dir, "AI-Generated Images")
os.makedirs(GENERATED_DIR, exist_ok=True)

@app.route('/style-transfer', methods=['POST'])
def style_transfer_api():
    # Get uploaded files
    content_file = request.files.get('content')
    style_file = request.files.get('style')
    if not content_file or not style_file:
        return jsonify({'error': 'Missing files'}), 400

    # Save temporary files
    #content_path = os.path.join(GENERATED_DIR, content_file.filename)
    #style_path = os.path.join(GENERATED_DIR, style_file.filename)
    #content_file.save(content_path)
    #style_file.save(style_path)

    # Create output filename
    timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
    output_filename = f"styled_{timestamp}.jpg"
    output_path = os.path.join(GENERATED_DIR, output_filename)

    # Run neural style transfer
    run_style_transfer(
        content_img_path=content_file,
        style_img_path=style_file,
        output_path=output_path,
        num_steps=3,
        show_progress=True
    )

    # Save info to JSON log
    json_path = os.path.join(GENERATED_DIR, "created_art.json")
    entry = {"timestamp": timestamp,
             "content": content_file.filename,
             "style": style_file.filename,
             "output": output_filename}
    
    existing = []
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            existing = json.load(f)
    existing.append(entry)
    with open(json_path, "w") as f:
        json.dump(existing, f, indent=2)

    # Return file path
    return jsonify({"output": f"/download/{output_filename}"})

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(os.path.join(GENERATED_DIR, filename), as_attachment=True)

def extract_visual_features(image_rgb):
    # K-Means clustering to find the most popular colours - extract a colour palette
    k=10 
    pixels = image_rgb.reshape(-1, 3)
    kmeans = KMeans(n_clusters=k, random_state=42).fit(pixels)
    colors = kmeans.cluster_centers_.astype(int)
    palette = colors

    # classify what type of colour palatte an image has (warm/cold/black and white etc...)
    palette_norm = palette / 255.0
    warm_count, cool_count, gray_count = 0, 0, 0
    
    for color in palette_norm:
        r, g, b = color
        
        # if all channels are very close, check for greyscale/neutral
        if abs(r - g) < 0.1 and abs(r - b) < 0.1 and abs(g - b) < 0.1:
            gray_count += 1
            continue
        
        # convert to HSV for warm/cool tone check
        hsv = cv2.cvtColor(np.uint8([[color*255]]), cv2.COLOR_RGB2HSV)[0][0]
        h = hsv[0] 
        
        # hue in [0, 180] 
        if (0 <= h <= 20) or (160 <= h <= 180):  # reds
            warm_count += 1
        elif 20 < h <= 50:  # yellows/oranges
            warm_count += 1
        elif 50 < h <= 130:  # greens/blues
            cool_count += 1
        elif 130 < h < 160:  # purples/magentas
            cool_count += 1
    
    total = warm_count + cool_count + gray_count
    
    if gray_count == total:
        palette_type = "Black and White / Grayscale"
    elif warm_count > cool_count and warm_count >= total * 0.5:
        palette_type =  "Warm"
    elif cool_count > warm_count and cool_count >= total * 0.5:
        palette_type = "Cool"
    else:
        palette_type = "Mixed / Balanced"
    print("Palette type:", palette_type)

    return palette, palette_type    

# Neural Style Transfer
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(device)

image_size = 512 if torch.cuda.is_available() else 256  

normalization_mean = [0.485, 0.456, 0.406]
normalization_std = [0.229, 0.224, 0.225]
normalize = transforms.Normalize(mean=normalization_mean,
                                 std=normalization_std)

transform = transforms.Compose([
    transforms.Resize(image_size),              
    transforms.CenterCrop(image_size),          
    transforms.ToTensor(),
    normalize
])

def load_image(image_path):
    image = Image.open(image_path).convert('RGB')
    image = transform(image).unsqueeze(0)  # Add batch dimension
    return image.to(device) 


def save_image(tensor, path):
    image = tensor.detach().cpu().clone().squeeze(0)
    image = image * torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    image = image + torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    image = torch.clamp(image, 0, 1)
    transforms.ToPILImage()(image).save(path)

def gram_matrix(tensor):
    # tensor shape: (batch_size=1, channels, height, width)
    b, c, h, w = tensor.size()
    features = tensor.view(c, h * w)      # reshape to (channels, height*width)
    G = torch.mm(features, features.t())  # compute Gram matrix (channels x channels)
    return G / (2 * c * h * w)  

# Load VGG19 model with pre-trained weights 
vgg = models.vgg19(weights=VGG19_Weights.DEFAULT).features.to(device).eval()
for param in vgg.parameters():
    param.requires_grad = False

#content_layer = ['conv4_2']
#style_layers = ['conv_1', 'conv_2', 'conv_3', 'conv_4', 'conv_5']

content_layer = '21' 
style_layers = ['0', '5', '10', '19', '28']

def get_content_feature(image):
    x = image
    for i, layer in enumerate(vgg):
        x = layer(x)
        if str(i) == content_layer:
            return x
        
def get_style_features(image, model, layers):
    features = []
    x = image
    for i, layer in enumerate(model):
        x = layer(x)
        if str(i) in layers:
            features.append(x)
    return features

def compute_content_loss(generated_features, content_features):
    return torch.nn.functional.mse_loss(generated_features, content_features)

def compute_style_loss(generated_features, style_features):
    loss = 0
    for gen_feat, style_feat in zip(generated_features, style_features):
        gram_generated = gram_matrix(gen_feat)
        gram_style = gram_matrix(style_feat)
        loss += torch.nn.functional.mse_loss(gram_generated, gram_style)
    return loss

def run_style_transfer(content_img_path, style_img_path, output_path, num_steps=300,
                    init_from_content=True,
                    show_progress=True):
    
    # Load images 
    content_img = load_image(content_img_path)
    style_img = load_image(style_img_path)

    # Extract Content and Style features from both images, respectively 
    style_features = get_style_features(style_img, vgg, style_layers)
    content_features = get_content_feature(content_img)

    # Initialize generated image
    if init_from_content:
        generated_img = content_img.clone().to(device).requires_grad_(True)
    else:
        generated_img = torch.randn((1, 3, 512, 512), device=device, requires_grad=True)

    optimizer = optim.LBFGS([generated_img])

    # Loss tracking for graph plot
    losses = {"total": [], "content": [], "style": []}
    current_losses = {"total": None, "content": None, "style": None}
        
    def closure():
        optimizer.zero_grad()

        # Forward Pass
        gen_content = get_content_feature(generated_img)
        gen_style = get_style_features(generated_img, vgg, style_layers)

        # Compute style and content loss
        c_loss = compute_content_loss(gen_content, content_features)
        s_loss = compute_style_loss(gen_style, style_features)
        s_loss = (1e9*s_loss)

        total_loss = c_loss + s_loss
        total_loss.backward()

        current_losses["total"] = total_loss.item()
        current_losses["content"] = c_loss.item()
        current_losses["style"] = s_loss.item()

        return total_loss

    for step in range(num_steps):
        optimizer.step(closure)

        losses["total"].append(current_losses["total"])
        losses["content"].append(current_losses["content"])
        losses["style"].append(current_losses["style"])

        if show_progress:
            print(f"Step {step}, Total Loss: {current_losses['total']:.4f}, "
            f"Content Loss: {current_losses['content']:.4f}, "
            f"Style Loss: {current_losses['style']:.4f}")
        
    # Save output 
    with torch.no_grad():
        final_img = generated_img.detach().clone()

    save_image(final_img, output_path)
    print(f"Saved stylised image to {output_path}")

    return output_path

# Cold-Start Mitigation Strategy 
# Concept structure i.e. what each box will contain
def make_concept(concept_type, label, meta=None):
    return {
        "type": concept_type,   # artist, genre, style, period
        "label": label,
        "meta": meta or {}      # ids, file path etc... FOR THUMBNAIL
    }

# Candidate Pools from DB
def get_artist_candidates(cursor, limit=50):
    query = """
        SELECT a.artist_id, a.name_surname, COUNT(p.painting_id) as freq, a.art_movements
        FROM artists a
        JOIN paintings p ON a.artist_id = p.artist_id
        GROUP BY a.artist_id
        ORDER BY freq DESC
        LIMIT %s;
    """
    cursor.execute(query, (limit,))
    return cursor.fetchall()

def get_genre_candidates(cursor, limit=20):
    query = """
        SELECT genre, COUNT(*) as freq
        FROM paintings
        WHERE genre IS NOT NULL
        GROUP BY genre
        ORDER BY freq DESC
        LIMIT %s;
    """
    cursor.execute(query, (limit,))
    return cursor.fetchall()

def get_style_candidates(cursor, limit=20):
    query = """
        SELECT art_style, COUNT(*) as freq
        FROM paintings
        WHERE art_style IS NOT NULL
        GROUP BY art_style
        ORDER BY freq DESC
        LIMIT %s;
    """
    cursor.execute(query, (limit,))
    return cursor.fetchall()

PERIODS = [
    ("Medieval", 500, 1400),
    ("Renaissance", 1400, 1600),
    ("Baroque", 1600, 1750),
    ("Neoclassicism", 1750, 1820),
    ("Romanticism", 1800, 1850),
    ("Realism", 1840, 1880),
    ("Impressionism", 1870, 1890),
    ("Post-Impressionism", 1886, 1905),
    ("Modern", 1900, 1970),
    ("Contemporary", 1970, "Present")
]

# word cloud of sub-periods as an image
# Controlled Sampling with k items per category to ensure coverage
def split_head_tail(rows, head_ratio=0.3):
    split_idx = int(len(rows) * head_ratio)
    head = rows[:split_idx]       # popular
    tail = rows[split_idx:]       # long-tail
    return head, tail

def sample_artists(artist_rows, k=8):
    """
    3 curated i.e. top popular
    3 diverse by movement
    2 long-tail for exploration
    """
    head, tail = split_head_tail(artist_rows, head_ratio=0.3)

    selected = []
    used_ids = set()

    def build_artist(aid, name):
        thumb = generate_concept_thumbnail("artist", name)
        return make_concept(
            "artist",
            name,
            {
                "artist_id": aid,
                "thumbnail": thumb["thumbnail_path"] if thumb else None
            }
        )

    # Curated 
    for aid, name, _, _ in head:
        if len(selected) >= 3:
            break
        if aid not in used_ids:
            selected.append(build_artist(aid, name))
            used_ids.add(aid)

    # Diverse by movement
    grouped = defaultdict(list)
    for artist_id, name, freq, movements in head:
        key = movements if movements else "Unknown"
        grouped[key].append((artist_id, name))

    groups = list(grouped.values())
    random.shuffle(groups)

    for group in groups:
        if len(selected) >= 6:  # 3 curated + 3 diverse
            break

        random.shuffle(group)
        for aid, name in group:
            if aid not in used_ids:
                selected.append(build_artist(aid, name))
                used_ids.add(aid)
                break  # move to next group

    # Long-tail
    random.shuffle(tail)
    for aid, name, _, _ in tail:
        if len(selected) >= 8:
            break
        if aid not in used_ids:
            selected.append(build_artist(aid, name))
            used_ids.add(aid)

    # Fallback
    random.shuffle(artist_rows)
    for aid, name, _, _ in artist_rows:
        if len(selected) >= k:
            break
        if aid not in used_ids:
            selected.append(build_artist(aid, name))
            used_ids.add(aid)

    return selected[:k]

def sample_styles(styles_with_freq, k=7):
    head, tail = split_head_tail(styles_with_freq, 0.3)

    selected = []
    used = set()

    def build_style(style):
        thumb = generate_concept_thumbnail("style", style)
        return make_concept(
            "style",
            style,
            {
                "style": style,
                "thumbnail": thumb["thumbnail_path"] if thumb else None
            }
        )

    # curated
    for style, _ in head:
        if len(selected) >= 2:
            break
        if style not in used:
            selected.append(build_style(style))
            used.add(style)

    # diverse
    mid = head[2:]
    random.shuffle(mid)

    for style, _ in mid:
        if len(selected) >= 5:
            break
        if style not in used:
            selected.append(build_style(style))
            used.add(style)

    # long-tail
    random.shuffle(tail)
    for style, _ in tail:
        if len(selected) >= 7:
            break
        if style not in used:
            selected.append(build_style(style))
            used.add(style)

    # fallback
    random.shuffle(styles_with_freq)
    for style, _ in styles_with_freq:
        if len(selected) >= k:
            break
        if style not in used:
            selected.append(build_style(style))
            used.add(style)   

    return selected[:k]

def sample_genres(genres_with_freq, k=7):
    head, tail = split_head_tail(genres_with_freq, 0.3)

    selected = []
    used = set()

    def build_genre(genre):
        thumb = generate_concept_thumbnail("genre", genre)
        return make_concept(
            "genre",
            genre,
            {
                "genre": genre,
                "thumbnail": thumb["thumbnail_path"] if thumb else None
            }
        )

    # curated
    for genre, _ in head:
        if len(selected) >= 2:
            break
        if genre not in used:
            selected.append(build_genre(genre))
            used.add(genre)

    # diverse
    mid = head[2:]
    random.shuffle(mid)

    for genre, _ in mid:
        if len(selected) >= 5:
            break
        if genre not in used:
            selected.append(build_genre(genre))
            used.add(genre)

    # long-tail
    random.shuffle(tail)
    for genre, _ in tail:
        if len(selected) >= 7:
            break
        if genre not in used:
            selected.append(build_genre(genre))
            used.add(genre)

    # fallback
    random.shuffle(genres_with_freq)
    for genre, _ in genres_with_freq:
        if len(selected) >= k:
            break
        if genre not in used:
            selected.append(build_genre(genre))
            used.add(genre)

    return selected[:k]

def sample_periods(k=5):
    selected_periods = random.sample(PERIODS, k)

    results = []

    for name, start, end in selected_periods:
        thumb = generate_concept_thumbnail(
            "period",
            {"start": start, "end": end}
        )

        results.append(make_concept(
            "period",
            name,
            {
                "start": start,
                "end": end,
                "thumbnail": thumb["thumbnail_path"] if thumb else None
            }
        ))

    return results

@app.route("/api/get_box_titles", methods=["GET"])
def get_box_titles():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 2: candidate pools
        artists = get_artist_candidates(cursor, limit=50)
        genres = get_genre_candidates(cursor, limit=20)
        styles = get_style_candidates(cursor, limit=20)

        # Step 3: controlled sampling
        artist_boxes = sample_artists(artists, k=8)
        style_boxes = sample_styles(styles, k=7)
        genre_boxes = sample_genres(genres, k=7)
        period_boxes = sample_periods(k=5)

        # combine + shuffle
        all_boxes = artist_boxes + style_boxes + genre_boxes + period_boxes
        random.shuffle(all_boxes)

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "boxes": all_boxes
        })

    except Exception as e:
        print("ERROR in /api/get_box_titles:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/has_preferences", methods=["GET"])
def has_preferences():
    try:
        client_id = get_client_id()

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT u.user_id
            FROM users u
            JOIN cold_start_preferences p ON u.user_id = p.user_id
            WHERE u.client_id = %s
            LIMIT 1
        """

        cursor.execute(query, (client_id,))
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            "has_preferences": bool(result)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/log_user_preferences", methods=["POST"])
def log_user_preferences():
    try:
        data = request.get_json()

        user_id = data.get("user_id")
        preferences = data.get("preferences", [])

        if not user_id or not preferences:
            return jsonify({"success": False, "error": "Missing data"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO cold_start_preferences
            (user_id, preference_type, preference_label)
            VALUES (%s, %s, %s)
        """

        for pref in preferences:
            p_type = pref.get("type")
            label = pref.get("label")

            cursor.execute(insert_query, (
                user_id,
                p_type,
                label
            ))

        cursor.execute("""
            UPDATE users
            SET has_completed_cold_start = TRUE
            WHERE user_id = %s
        """, (user_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("ERROR in /api/log_user_preferences:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/get_user_preferences", methods=["GET"])
def get_user_preferences():
    try:
        client_id = get_client_id()

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT 
                preference_type AS type,
                preference_label AS label
            FROM cold_start_preferences p
            JOIN users u ON p.user_id = u.user_id
            WHERE u.client_id = %s
        """

        cursor.execute(query, (client_id,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "preferences": rows
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def normalise_period_label(label):
    PERIOD_MAP = {
        "Medieval": {"start": 500, "end": 1400},
        "Renaissance": {"start": 1400, "end": 1600},
        "Baroque": {"start": 1600, "end": 1750},
        "Neoclassicism": {"start": 1750, "end": 1820},
        "Romanticism": {"start": 1800, "end": 1850},
        "Realism": {"start": 1840, "end": 1880},
        "Impressionism": {"start": 1870, "end": 1890},
        "Post-Impressionism": {"start": 1886, "end": 1905},
        "Modern": {"start": 1900, "end": 1970},
        "Contemporary": {"start": 1970, "end": "Present"},
    }
    return PERIOD_MAP.get(label)

# Thumbnails per concept in cold-start page
def fetch_paintings_by_concept(cursor, concept_type, label):
    """
    Returns painting_ids filtered by concept type
    """
    if concept_type == "artist":
        cursor.execute("""
            SELECT painting_id
            FROM paintings_and_artists_metadata_bert
            WHERE artist = %s
        """, (label,))

    elif concept_type == "genre":
        cursor.execute("""
            SELECT painting_id
            FROM paintings_and_artists_metadata_bert
            WHERE genre = %s
        """, (label,))

    elif concept_type == "style":
        cursor.execute("""
            SELECT painting_id
            FROM paintings_and_artists_metadata_bert
            WHERE art_style = %s
        """, (label,))

    elif concept_type == "period":
        # Convert string to structured range
        if isinstance(label, str):
            label = normalise_period_label(label)

        # Safeguard
        if not label or not isinstance(label, dict):
            print(f"[WARNING] Unknown period label: {label}")
            return []

        start = label["start"]
        end = label["end"]

        if end == "Present":
            cursor.execute("""
                SELECT painting_id
                FROM paintings_and_artists_metadata_bert
                WHERE year_created >= %s
            """, (start,))
        else:
            cursor.execute("""
                SELECT painting_id
                FROM paintings_and_artists_metadata_bert
                WHERE year_created IS NOT NULL
                AND year_created BETWEEN %s AND %s
            """, (start, end))

    else:
        return []

    rows = cursor.fetchall()
    painting_ids = [
        r["painting_id"] if isinstance(r, dict) else r[0]
        for r in rows
    ]
    print("PAINTING IDS TYPE SAMPLE:", type(painting_ids[0]), painting_ids[:5])

    return painting_ids

image_tensors = joblib.load('data/image_tensors.pkl')
image_ids = joblib.load('data/ids.pkl')
image_matrix = np.array(image_tensors)  # (N, 512)
image_matrix = image_matrix / np.linalg.norm(image_matrix, axis=1, keepdims=True)

id_to_idx = {pid: i for i, pid in enumerate(image_ids)}

def get_thumbnail_for_concept(cursor, concept_type, label, top_k=5):
    """
    Returns a representative painting_id and the respective image_path
    """
    painting_ids = fetch_paintings_by_concept(cursor, concept_type, label)

    if len(painting_ids) == 0:
        return None, [], None

    # Filter valid embeddings
    valid_indices = [
        (pid, id_to_idx[pid])
        for pid in painting_ids
        if pid in id_to_idx
    ]

    if len(valid_indices) == 0:
        return None, [], None
    
    pids, indices = zip(*valid_indices)
    subset_embeddings = image_matrix[list(indices)]
    print(len(valid_indices))

    # Centroid i.e. average embedding vector of the concept
    centroid = np.mean(subset_embeddings, axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    # Similarity to centroid and top-k nearest
    scores = subset_embeddings @ centroid.T
    top_k_idx = np.argsort(scores)[-top_k:][::-1]
    top_k_painting_ids = [pids[i] for i in top_k_idx]

    # Random pick from top-k (bias reduction)
    chosen_local_idx = np.random.choice(top_k_idx)
    chosen_painting_id = pids[chosen_local_idx]

    return chosen_painting_id, top_k_painting_ids, scores[top_k_idx] 

def build_painting_url(image_path):
    normalized = image_path.replace("\\", "/").lstrip("/")

    # ensure no duplicate "paintings/"
    if normalized.startswith("paintings/"):
        normalized = normalized[len("paintings/"):]

    return f"{BASE_PATH}/paintings/{normalized}"

def get_thumbnail_path(cursor, painting_id):
    cursor.execute("""
        SELECT image_path
        FROM paintings_and_artists_metadata_bert
        WHERE painting_id = %s
    """, (painting_id,))

    row = cursor.fetchone()
    if not row:
        return None

    return build_painting_url(row[0])

def generate_concept_thumbnail(concept_type, label):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        painting_id, _, _ = get_thumbnail_for_concept(cursor, concept_type, label)

        if not painting_id:
            return None

        image_path = get_thumbnail_path(cursor, painting_id)

        return {
            "painting_id": painting_id,
            "thumbnail_path": image_path
        }

    finally:
        cursor.close()
        conn.close()

# User-Profile Creation
# TO-DO: user can rank which are most imp to see how results change
# Have a normalised wieght value 
# Create a weighted user profile vector based on interactions or cold start if new user
INTERACTION_WEIGHTS = {
    "rating": 2.0,
    "review": 0.5,
    "favourite": 3.0,
    "not_interested": -3.0,
    "save_to_gallery": 2.0,
    "viewing_time": 1.0,  
    "click": 0.5,
    "skip": -2.0
}

def rank_discount(rank):
    return 1.0 / np.log2(rank + 2)

def compute_interaction_weight(interaction):
    """
    Compute weight from a single interaction record
    interaction: dict containing both implicit and/or explicit user feedback
    """
    weight = 0.0

    # Explicit Feedback with high signal since it's more indicative of user preferences
    rating = interaction.get("rating")
    if rating is not None:
        if rating >= 4:
            weight += INTERACTION_WEIGHTS["rating"] * (rating / 5.0)
        elif rating <= 2:
            weight -= INTERACTION_WEIGHTS["rating"] * (1 - rating / 5.0)

    if interaction.get("favourite"):
        weight += INTERACTION_WEIGHTS["favourite"]

    if interaction.get("not_interested"):
        weight += INTERACTION_WEIGHTS["not_interested"]

    if interaction.get("review"):
        weight += INTERACTION_WEIGHTS["review"]  

    if interaction.get("save_to_gallery"):
        weight += INTERACTION_WEIGHTS["save_to_gallery"]

    # Implicit Feedback has a lower signal since it's relatively weak 
    if interaction.get("click"):
        weight += INTERACTION_WEIGHTS["click"]

    viewing_time = interaction.get("viewing_time")
    if viewing_time is not None:
        # Log-scaled dwell time 
        norm_time = np.log1p(viewing_time) / np.log(60)
        norm_time = min(norm_time, 1.0)  # cap
        weight += INTERACTION_WEIGHTS["viewing_time"] * norm_time

    # Skip is a derived negative interaction
    if interaction.get("skip"):
        rank = interaction.get("rank", 10)  # fallback

        # Rank discount (log-based)
        discount = rank_discount(rank)

        weight += INTERACTION_WEIGHTS["skip"] * discount

    return weight

def create_user_profile(interactions, image_matrix, id_to_idx):
    """
    interactions: list of dicts, each containing:
        {
            "painting_id": int,
            "click": bool,
            "viewing_time": int,
            "skip": bool,
            "rating": int,
            "review": str,
            "favourite": bool,
            "not_interested": bool,
            "save_to_gallery": bool
        }
    """
    weighted_sum = np.zeros(image_matrix.shape[1])
    total_weight = 0.0

    for interaction in interactions:
        pid = interaction["painting_id"]

        if pid not in id_to_idx:
            continue

        idx = id_to_idx[pid]
        vector = image_matrix[idx]

        weight = interaction["weight"]

        weighted_sum += weight * vector
        total_weight += abs(weight)

    if total_weight == 0:
        raise ValueError("No valid signal")

    user_profile = weighted_sum / total_weight
    user_profile = user_profile / np.linalg.norm(user_profile)

    return user_profile

# ResNet50/VGG-19
# Preprocess images the same way as they were trained on ImageNet
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std =[0.229, 0.224, 0.225]
    )
])

def preprocess_image(image_path):
    try:
        img = Image.open(image_path).convert("RGB")
        img = transform(img)
        return img
    except:
        return None
    
model_resnet = models.resnet50(pretrained=True)

# Remove final classification layer (fc)
model_resnet = torch.nn.Sequential(*list(model_resnet.children())[:-1])
model_resnet.to(device)
model_resnet.eval()  

class VGG19FeatureExtractor(nn.Module):
    def __init__(self):
        super().__init__()
        vgg = models.vgg19(weights=models.VGG19_Weights.IMAGENET1K_V1)
        self.features = vgg.features

        # Freeze 
        for param in self.features.parameters():
            param.requires_grad = False

        # Layers to extract from
        self.selected_layers = [17, 26, 35]
        self.pool = nn.AdaptiveAvgPool2d((1, 1))

    def forward(self, x):
        outputs = []

        for i, layer in enumerate(self.features):
            x = layer(x)
            if i in self.selected_layers:
                pooled = self.pool(x)
                pooled = pooled.view(pooled.size(0), -1)  # flatten
                outputs.append(pooled)

        # Concatenate multi-level features
        return torch.cat(outputs, dim=1)

model_vgg = VGG19FeatureExtractor().to(device)
model_vgg.eval()

def extract_resnet_features(model, img_tensor):
    img_tensor = img_tensor.unsqueeze(0).to(device)

    with torch.no_grad():
        features = model(img_tensor)

    features = features.squeeze(-1).squeeze(-1)  # (1, 2048)
    
    return features.cpu().numpy().flatten()

def extract_vgg_19_features(model, img_tensor):
    img_tensor = img_tensor.unsqueeze(0).to(device)

    with torch.no_grad():
        features = model(img_tensor) # (1, 1280)

    return features.cpu().numpy().flatten() 

# Load embeddings
data = joblib.load('data/resnet50_embeddings.pkl')
embeddings_resnet = data['embeddings']
image_ids_resnet = data['image_ids']

data = joblib.load('data/VGG19_embeddings.pkl')
embeddings_vgg = data['embeddings']
image_ids_vgg = data['image_ids']

embeddings_resnet_norm = embeddings_resnet / np.linalg.norm(embeddings_resnet, axis=1, keepdims=True)
embeddings_vgg_norm = embeddings_vgg / np.linalg.norm(embeddings_vgg, axis=1, keepdims=True)

pcaRESNET = PCA(n_components=512) # or 128, 512 depending on tradeoff
pcaVGG = PCA(n_components=256)  
pca_resnet = pcaRESNET.fit_transform(embeddings_resnet_norm)
pca_vgg = pcaVGG.fit_transform(embeddings_vgg_norm)

resnet_norm = pca_resnet / np.linalg.norm(pca_resnet, axis=1, keepdims=True)
vgg_norm = pca_vgg / np.linalg.norm(pca_vgg, axis=1, keepdims=True)

def retrieve_top_k_from_user(user_profile, embeddings, k=10):
    scores = embeddings @ user_profile
    top_k_idx = np.argsort(scores)[::-1][:k]
    return top_k_idx, scores[top_k_idx]

def get_seen_paintings(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT painting_id
        FROM interaction_events
        WHERE user_id = %s
        AND event_type IN ('view_start', 'click', 'favourite', 'rating')
    """, (user_id,))

    seen = {row[0] for row in cur.fetchall()}

    cur.close()
    conn.close()
    return seen

@app.route("/api/recommend_resnet", methods=["POST"])
def recommend_resnet():
    data = request.json
    user_id = data["user_id"]
    session_id = data.get("session_id")

    if not user_id or not session_id:
        return jsonify({
            "success": False,
            "error": "Missing user_id or session_id"
        }), 400

    k = data.get("k", 10)

    request_id = generate_request_id()
    interactions = fetch_user_interactions(user_id)
    for i in interactions:
        i["weight"] = compute_interaction_weight(i)

    user_profile = create_user_profile(interactions, embeddings_resnet, id_to_idx)
    user_profile = pcaRESNET.transform(user_profile.reshape(1, -1)).flatten()
    user_profile = user_profile / np.linalg.norm(user_profile)

    top_k_idx, scores = retrieve_top_k_from_user(user_profile, resnet_norm, k)
    print("painting IDs: ", top_k_idx)
    print("scores: ", scores)

    seen = get_seen_paintings(user_id)
    results = []
    db_rows = []

    for rank, (idx, score) in enumerate(zip(top_k_idx, scores)):
        painting_id = int(image_ids[idx])
        if painting_id in seen:
            continue

        results.append({
            "painting_id": painting_id,
            "score": float(score)
        })

        db_rows.append((
            session_id,
            user_id,
            painting_id,
            request_id,
            rank,
            float(score),
            datetime.utcnow()
        ))

    painting_ids = [r["painting_id"] for r in results]
    db_paintings = fetch_paintings(painting_ids)
    db_map = {p["painting_id"]: p for p in db_paintings}

    final_results = []
    for r in results:
        pid = r["painting_id"]
        meta = db_map.get(pid)

        if not meta:
            continue

        final_results.append({
            "painting_id": pid,
            "score": r["score"],
            "image_url": build_painting_url(meta["image_path"]),
            "request_id": request_id
        })

    # Store recommendations in DB
    # conn = get_db_connection()
    # cur = conn.cursor()

    # execute_values(cur, """
    #     INSERT INTO recommendations (
    #         session_id,
    #         user_id,
    #         painting_id,
    #         request_id,
    #         rank,
    #         score,
    #         created_at
    #     )
    #     VALUES %s
    # """, db_rows)

    # conn.commit()
    # cur.close()
    # conn.close()

    return jsonify({
        "user_id": user_id,
        "request_id": request_id,
        "recommendations": final_results
    })

def retrieve_top_k(query_path, model_name, model, embeddings, transform, k=10):
    # Load and preprocess query 
    img = preprocess_image(query_path)

    # Extract features, L2 Norm, Apply PCA, L2 Norm again, Cosine similarity
    if(model_name == 'model_vgg'):
        query_embeddings = extract_vgg_19_features(model, img)
        query_embeddings = query_embeddings / np.linalg.norm(query_embeddings)
        query_embeddings = pcaVGG.transform(query_embeddings.reshape(1, -1)).flatten()
        query_embeddings = query_embeddings / np.linalg.norm(query_embeddings)
        scores = embeddings @ query_embeddings
    elif(model_name == 'model_resnet'):
        query_embeddings = extract_resnet_features(model, img)
        query_embeddings = query_embeddings / np.linalg.norm(query_embeddings)
        query_embeddings = pcaRESNET.transform(query_embeddings.reshape(1, -1)).flatten()
        query_embeddings = query_embeddings / np.linalg.norm(query_embeddings)
        scores = embeddings @ query_embeddings

    # Top-k retreival 
    top_k_idx = np.argsort(scores)[::-1][:k]

    return top_k_idx, scores[top_k_idx]

# SBERT 
# Title preprocessing i.e. NULL/missing handling and text normalisation 
ROMAN_NUMERAL_PATTERN = re.compile(r'\b(i{1,3}|iv|v|vi{0,3}|ix|x)\b', re.IGNORECASE)

def normalize_roman_numerals(text: str) -> str:
    return ROMAN_NUMERAL_PATTERN.sub(lambda m: m.group(0).upper(), text)

def process_title(title: str) -> str:
    # Handle NULL/missing values 
    if title is None or title.strip() == "":
        return "unknown title"

    # Normalise whitespace
    title = title.strip() 
    title = re.sub(r'\s+', ' ', title)

    # Fix broken apostrophes e.g. "Martin S" → "Martin's" and normalise roman numerals
    title = re.sub(r"\b([A-Za-z]+)\s+S\b", r"\1's", title)
    title = normalize_roman_numerals(title)

    # Remove trailing index numbers only when safe
    if re.search(r'(untitled|drawing|study|composition|abstraction)', title, re.IGNORECASE):
        title = re.sub(r'\s*\(?\d+\)?$', '', title)

    title = re.sub(r'\s+', ' ', title).strip()

    return title

# Used to avoid cutting mid-word
def safe_cut(text, length):
    cut = text[:length]
    return cut[:cut.rfind(" ")] if " " in cut else cut

# Bio preprocessing, including character cutoff since bio fields contain the most 
# characters and heavily bias the embedding space if left untrimmed
def process_bio(bio: str, max_chars=2000) -> str:
    if bio is None or bio.strip() == "":
        return "no biography available"
    
    # Normalise whitespace, including newlines and tabs
    bio = bio.strip()
    bio = re.sub(r'\s+', ' ', bio)

    # Truncate so that bio is token-safe for SBERT 
    if len(bio) > max_chars:
        head_len = int(max_chars * 0.6)
        tail_len = max_chars - head_len

        head = safe_cut(bio, head_len)
        tail = safe_cut(bio[::-1], tail_len)[::-1]

        bio = f"{head} ... {tail}"

    return bio

# This method can be used for all categorical fields, to handle NULL/missing values, convert all fields to lowercase apart 
# from artist and remove excess whitespace 
def process_categorical_field(field_value: str, field_name: str = None) -> str:
    # Handle NULL/missing values 
    if field_value is None or field_value.strip() == "":
        return f"unknown {field_name}"

    field_value = field_value.strip()

    # Normalise whitespace and convert all categoricals to lowercase except artist since it harms entity recognition
    field_value = re.sub(r'\s+', ' ', field_value)
    if field_name != "artist":
        field_value = field_value.lower()

    return field_value

# This method can be used for all multi-value fields, it handles nulls/missing values, 
# converts all comma seperated items to lower case, and applies the respective preprocessing for description_tags, 
# joining all value segments using |
def process_multi_value_field(feild_value: str, field_name: str = None) -> str:
    # Handle NULL/missing values
    if feild_value is None or feild_value.strip() == "":
        return f"unknown {field_name}" 

    # Split on comma 
    items = feild_value.split(",")
    cleaned = []
    for item in items:
        item = item.strip().lower()
        if item == "":
            continue
        
        # Replace hyphens with space when in-between words only and normalise internal whitespace
        if field_name == "description tags":
            item = re.sub(r'(?<=\w)-(?=\w)', ' ', item)

            # Apply segmentation only if; no spaces already, long enough, purely alphabetic
            if " " not in item and len(item) > 10 and item.isalpha():
                split_words = wordninja.split(item)

                # Safety checks to avoid bad splits (e.g. single char fragments)
                if (len(split_words) > 1 and all(len(w) > 2 for w in split_words) and len(" ".join(split_words)) >= len(item) * 0.8):
                    item = " ".join(split_words) 

        item = re.sub(r'\s+', ' ', item)
        cleaned.append(item)

    if not cleaned:
        return f"unknown {field_name}" 

    # Deduplicate while preserving order
    unique_items = list(dict.fromkeys(cleaned))

    return " | ".join(unique_items)

# Instead of using years, encode them as semantic 
def process_year(year_created):
    # NULL/missing 
    if year_created is None or str(year_created).strip() == "":
        return "unknown period"

    try:
        year = int(year_created)
    except (ValueError, TypeError):
        return "unknown period"

    # Period mapping 
    if year < 1400:
        return "medieval period 14th century"
    elif year < 1600:
        return "renaissance period 16th century"
    elif year < 1700:
        return "baroque period 17th century"
    elif year < 1800:
        return "rococo enlightenment period 18th century"
    elif year <= 1850:
        return "early modern period 18th century"
    elif year <= 1900:
        return "late 19th century impressionism era"
    elif year <= 1945:
        return "early 20th century modernism"
    elif year <= 1970:
        return "mid 20th century post war modern"
    elif year <= 2000:
        return "late 20th century contemporary"
    else:
        return "contemporary period 20th century" 

def format_text_fields(title, year_created, genre, art_style, media, description_tags, artist, nationality, fields, art_movements, bio):
    title_processed = process_title(title)
    year_processed = process_year(year_created)
    genre_processed = process_categorical_field(genre, "genre")
    art_style_processed = process_categorical_field(art_style, "art style")
    media_processed = process_multi_value_field(media, "media")
    description_tags_processed = process_multi_value_field(description_tags, "description tags")
    artist_processed = process_categorical_field(artist, "artist")
    nationality_processed = process_categorical_field(nationality, "nationality")
    fields_processed = process_multi_value_field(fields, "fields")
    art_movements_processed = process_multi_value_field(art_movements, "art movements")
    bio_processed = process_bio(bio)

    # Structured reperesntation 
    structured = {
        "title": title_processed,
        "year_period": year_processed,
        "genre": genre_processed,
        "art_style": art_style_processed,
        "media": media_processed.split(" | "),
        "description_tags": description_tags_processed.split(" | "),
        "artist": artist_processed,
        "nationality": nationality_processed,
        "fields": fields_processed.split(" | "),
        "art_movements": art_movements_processed.split(" | "),
        "bio": bio_processed
    }

    return structured
processed_data = joblib.load("data/processed_data.pkl")

# Load SBERT model to be used for per-field embedding extraction 
model = SentenceTransformer('all-mpnet-base-v2') # all-roberta-large-v1, paraphrase-multilingual-mpnet-base-v2
def prepare_field_text(value):
    if isinstance(value, list):
        return " | ".join(value) if value else ""
    text = str(value).strip()
    return text

embedding_matrices = joblib.load("data/SBERT_embedding_matrices.pkl")

#query_clean = format_text_fields(query["title"], query["year_created"], query["genre"], query["art_style"], query["media"],
                    #query["description_tags"], query["artist"], query["art_movements"], query["fields"], query["nationality"], 
                    #query["bio"])

def encode_query_sbert(query_structured, model):
    query_embeddings = {}

    for field, value in query_structured.items():
        text = prepare_field_text(value)

        if text == "":
            continue

        query_embeddings[field] = model.encode(text, normalize_embeddings=True)
    return query_embeddings

WEIGHTS = {
    "title": 0.2,
    "genre": 0.1,
    "art_style": 0.1,
    "description_tags": 0.1,
    "media": 0.05,
    "year_period": 0.05,
    "artist": 0.05,
    "nationality": 0.03,
    "fields": 0.03,
    "art_movements": 0.1,
    "bio": 0.03   
}

def normalise_weights(weights):
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}

WEIGHTS = normalise_weights(WEIGHTS)

def compute_similarity_per_field_sbert(query_embeddings, embedding_matrices):
    similarities = {}

    for field, matrix in embedding_matrices.items():
        q = query_embeddings.get(field)

        if q is None:
            similarities[field] = np.zeros(matrix.shape[0])
            continue

        sim = matrix @ q   
        similarities[field] = sim

    return similarities

def weighted_late_fusion(similarities, weights):
    final_scores = np.zeros(len(next(iter(similarities.values()))))

    for field, sim in similarities.items():
        final_scores += weights.get(field, 0) * sim

    return final_scores

def get_top_k(final_scores, query_index, k=30):
    final_scores = final_scores.copy()
    final_scores[query_index] = -np.inf
    top_indices = np.argpartition(final_scores, -k)[-k:]
    top_indices = top_indices[np.argsort(final_scores[top_indices])[::-1]]
    return top_indices, final_scores[top_indices]

painting_id_to_index = {
    pid: idx for idx, (_, pid) in enumerate(processed_data)
}
def recommend_sbert(query_structured, model, embedding_matrices, weights, painting_id_to_index, query_id, k=10):
    query_embeddings = encode_query_sbert(query_structured, model)
    similarities = compute_similarity_per_field_sbert(query_embeddings, embedding_matrices)
    final_scores = weighted_late_fusion(similarities, weights)
    query_index = painting_id_to_index[int(query_id)]
    top_indices, scores = get_top_k(final_scores, query_index, k)
    return top_indices, scores, similarities

# CLIP
# Load CLIP Model and Processor  
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", use_safetensors=True).to(device)
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

image_tensors = joblib.load('data/image_tensors.pkl')
text_tensors = joblib.load('data/text_tensors.pkl')

image_matrix = np.array(image_tensors)  # (N, 512)
text_matrix = np.array(text_tensors)    # (N, 512)

image_matrix = image_matrix / np.linalg.norm(image_matrix, axis=1, keepdims=True)
text_matrix = text_matrix / np.linalg.norm(text_matrix, axis=1, keepdims=True)

def retrieve_by_text(query, top_k=10):
    inputs = processor(text=query, return_tensors="pt", padding=True, truncation=True).to(device)

    with torch.no_grad():
        q_emb = model.get_text_features(**inputs)
        q_emb = q_emb / q_emb.norm(dim=-1, keepdim=True)

    q_emb = q_emb.cpu().numpy()

    # cosine similarity
    scores = image_matrix @ q_emb.T  
    top_k_idx = np.argsort(scores[:, 0])[::-1][:top_k]

    return top_k_idx, scores[top_k_idx]

def retrieve_by_image(image, top_k=10):
    inputs = processor(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        q_emb = model.get_image_features(**inputs)
        q_emb = q_emb / q_emb.norm(dim=-1, keepdim=True)

    q_emb = q_emb.cpu().numpy()

    # cosine similarity
    scores = image_matrix @ q_emb.T
    top_k_idx = np.argsort(scores[:, 0])[::-1][:top_k]

    return top_k_idx, scores[top_k_idx]

def hybrid_retrieve(query, alpha=0.6, top_k=10):
    inputs = processor(text=query, return_tensors="pt", padding=True, truncation=True).to(device)

    with torch.no_grad():
        text_emb = model.get_text_features(**inputs)
        text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)

    text_emb = text_emb.cpu().numpy()

    # cosine similarity
    text_scores = image_matrix @ text_emb.T
    text_side_scores = text_matrix @ text_emb.T

    final_scores = alpha * text_scores + (1 - alpha) * text_side_scores
    top_k_idx = np.argsort(final_scores[:, 0])[::-1][:top_k]

    return top_k_idx, final_scores[top_k_idx]

def fetch_paintings(painting_ids):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Preserve order 
    cur.execute("""
        SELECT 
            painting_id,
            image_path
        FROM paintings_and_artists_metadata_bert
        WHERE painting_id = ANY(%s)
        ORDER BY array_position(%s, painting_id);
    """, (painting_ids, painting_ids))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows

# TO-RUN: python app.py
if __name__ == "__main__":
    app.run(debug=True)