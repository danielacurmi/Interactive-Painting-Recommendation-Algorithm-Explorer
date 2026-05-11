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
from datetime import datetime, timezone
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

@app.route("/explore")
def explore():
    return render_template("explore.html")

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
            MAX(r.created_at) AS interaction_time,

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
            "skip": r["skip"],
            "interaction_time": r["interaction_time"]
        })

    return interactions

def fetch_clip_user_interactions(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            r.painting_id,
            r.rank,
            r.request_id,

            MAX(s.viewing_time_seconds) AS viewing_time,
            MAX(s.rating) AS rating,

            BOOL_OR(s.favourite) AS favourite,
            BOOL_OR(s.not_interested) AS not_interested,
            BOOL_OR(s.save_to_gallary) AS save_to_gallery,
            BOOL_OR(s.click) AS click,

            MAX(s.review) AS review,

            MAX(r.created_at) AS interaction_time,

            CASE
                WHEN r.request_id IN (
                    SELECT DISTINCT r1.request_id
                    FROM recommendations_clip r1
                    WHERE EXISTS (
                        SELECT 1
                        FROM recommendations_clip r2
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
                        s2.click = TRUE
                        OR s2.favourite = TRUE
                        OR s2.rating IS NOT NULL
                        OR s2.viewing_time_seconds > 2
                    )
                )

                THEN TRUE
                ELSE FALSE
            END AS skip

        FROM recommendations_clip r

        LEFT JOIN interaction_summary s
            ON r.painting_id = s.painting_id
            AND r.user_id = s.user_id
            AND r.request_id = s.request_id

        WHERE r.user_id = %s

        GROUP BY
            r.painting_id,
            r.request_id,
            r.rank

    """, (user_id,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    interactions = []

    for r in rows:

        interactions.append({

            "painting_id": r["painting_id"],
            "request_id": r["request_id"],
            "rank": r["rank"],
            "viewing_time": r["viewing_time"],
            "rating": r["rating"],
            "favourite": r["favourite"],
            "not_interested": r["not_interested"],
            "save_to_gallery": r["save_to_gallery"],
            "click": r["click"],
            "review": r["review"],
            "skip": r["skip"],
            "interaction_time": r["interaction_time"]
        })

    return interactions

def fetch_sbert_user_interactions(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            r.painting_id,
            r.rank,
            r.request_id,

            MAX(s.viewing_time_seconds) AS viewing_time,
            MAX(s.rating) AS rating,

            BOOL_OR(s.favourite) AS favourite,
            BOOL_OR(s.not_interested) AS not_interested,
            BOOL_OR(s.save_to_gallary) AS save_to_gallery,
            BOOL_OR(s.click) AS click,

            MAX(s.review) AS review,

            MAX(r.created_at) AS interaction_time,

            CASE
                WHEN r.request_id IN (
                    SELECT DISTINCT r1.request_id
                    FROM recommendations_sbert r1
                    WHERE EXISTS (
                        SELECT 1
                        FROM recommendations_sbert r2
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
                        s2.click = TRUE
                        OR s2.favourite = TRUE
                        OR s2.rating IS NOT NULL
                        OR s2.viewing_time_seconds > 2
                    )
                )

                THEN TRUE
                ELSE FALSE
            END AS skip

        FROM recommendations_sbert r

        LEFT JOIN interaction_summary s
            ON r.painting_id = s.painting_id
            AND r.user_id = s.user_id
            AND r.request_id = s.request_id

        WHERE r.user_id = %s

        GROUP BY
            r.painting_id,
            r.request_id,
            r.rank

    """, (user_id,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    interactions = []

    for r in rows:

        interactions.append({

            "painting_id": r["painting_id"],
            "request_id": r["request_id"],
            "rank": r["rank"],
            "viewing_time": r["viewing_time"],
            "rating": r["rating"],
            "favourite": r["favourite"],
            "not_interested": r["not_interested"],
            "save_to_gallery": r["save_to_gallery"],
            "click": r["click"],
            "review": r["review"],
            "skip": r["skip"],
            "interaction_time": r["interaction_time"]
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

            _, top_ids, scores = get_thumbnail_for_concept(cursor, concept_type, label, top_k=15)

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
            painting_id,
            title,
            year_created,
            genre,
            art_style,
            media,
            description_tags,
            image_path,
            artist,
            birth_year,
            death_year,
            nationality,
            fields,
            art_movements,
            bio

        FROM paintings_and_artists_metadata_bert 
        WHERE painting_id = %s;
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
            "artist": row["artist"],
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

# Track NST progress
style_transfer_progress = {
    "current": 0,
    "total": 300,
    "percent": 0,
    "running": False
}

@app.route('/style-transfer-progress')
def style_transfer_progress_api():
    return jsonify(style_transfer_progress)

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

    # Create output filename
    timestamp = datetime.now().strftime("%Y_%m_%d__%H_%M_%S")
    output_filename = f"styled_{timestamp}.jpg"
    output_path = os.path.join(GENERATED_DIR, output_filename)

    style_transfer_progress["current"] = 0
    style_transfer_progress["total"] = 300
    style_transfer_progress["percent"] = 0
    style_transfer_progress["running"] = True

    # Run neural style transfer
    run_style_transfer(
        content_img_path=content_file,
        style_img_path=style_file,
        output_path=output_path,
        num_steps=300,
        show_progress=True
    )

    style_transfer_progress["running"] = False
    style_transfer_progress["percent"] = 100

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
device = torch.device("cpu")
device_nst = torch.device("cuda")
print(device_nst)

image_size = 512 if device_nst.type == "cuda" else 256
print(image_size)

normalization_mean = [0.485, 0.456, 0.406]
normalization_std = [0.229, 0.224, 0.225]
normalize = transforms.Normalize(mean=normalization_mean,
                                 std=normalization_std)

transform_style = transforms.Compose([
    transforms.Resize(image_size),
    transforms.CenterCrop(image_size),
    transforms.ToTensor(),
    normalize
])

def load_image(image_path):
    image = Image.open(image_path).convert('RGB')
    image = transform_style(image).unsqueeze(0)  # Add batch dimension
    return image.to(device_nst)


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
def load_vgg():
    vgg = models.vgg19(weights=VGG19_Weights.DEFAULT).features.to(device_nst).eval()
    for param in vgg.parameters():
        param.requires_grad = False
    return vgg

#content_layer = ['conv4_2']
#style_layers = ['conv_1', 'conv_2', 'conv_3', 'conv_4', 'conv_5']

content_layer = '21'
style_layers = ['0', '5', '10', '19', '28']

def get_content_feature(image, vgg):
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
    
    # Load VGG19 model
    vgg = load_vgg()

    try:
        # Load images
        content_img = load_image(content_img_path)
        style_img = load_image(style_img_path)

        # Extract Content and Style features from both images, respectively
        style_features = get_style_features(style_img, vgg, style_layers)
        content_features = get_content_feature(content_img, vgg)

        # Initialize generated image
        if init_from_content:
            generated_img = content_img.clone().to(device_nst).requires_grad_(True)
        else:
            generated_img = torch.randn((1, 3, 512, 512), device=device_nst, requires_grad=True)

        optimizer = optim.LBFGS([generated_img])

        # Loss tracking for graph plot
        losses = {"total": [], "content": [], "style": []}
        current_losses = {"total": None, "content": None, "style": None}

        def closure():
            optimizer.zero_grad()

            # Forward Pass
            gen_content = get_content_feature(generated_img, vgg)
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

            # Update progress
            style_transfer_progress["current"] = step + 1
            style_transfer_progress["percent"] = int(((step + 1) / num_steps) * 100)

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

    # Unload model after use
    finally:
        del vgg
        torch.cuda.empty_cache()
        import gc
        gc.collect()

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

def get_thumbnail_for_concept(cursor, concept_type, label, top_k=10):
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
# Create a weighted user profile vector based on interactions or cold start if new user
DEFAULT_INTERACTION_WEIGHTS = {
    "rating": 1.0,
    "review": 1.0,
    "favourite": 1.0,
    "not_interested": 1.0,
    "viewing_time": 1.0,
    "click": 1.0,
    "skip": 1.0
}

def normalise_rating(rating):
    if rating is None:
        return 0.0

    return (rating - 3) / 2

def normalise_viewing_time(viewing_time):
    if viewing_time is None:
        return 0.0

    return min(np.log1p(viewing_time) / np.log(60),  1.0)

def normalise_skip(interaction):
    if not interaction.get("skip"):
        return 0.0

    rank = interaction.get("rank", 10)
    return rank_discount(rank)

def extract_interaction_signals(interaction):
    return {
        "rating": normalise_rating(interaction.get("rating")),
        "favourite": 1.0 if interaction.get("favourite") else 0.0,
        "not_interested": 1.0 if interaction.get("not_interested") else 0.0,
        "review": 1.0 if interaction.get("review") else 0.0,
        "click": 1.0 if interaction.get("click") else 0.0,
        "viewing_time": normalise_viewing_time(interaction.get("viewing_time")),
        "skip": normalise_skip(interaction)
    }

def rank_discount(rank):
    return 1.0 / np.log2(rank + 2)

def temporal_decay(interaction_time, decay_lambda=0.03):
    """
    Exponential temporal decay.

    decay_lambda:
        Higher = faster forgetting
        Lower = slower forgetting
    """
    if interaction_time is None:
        return 1.0

    now = datetime.now(timezone.utc)
    age_days = (now - interaction_time).days
    decay = np.exp(-decay_lambda * age_days)

    return decay

def apply_temporal_decay(weight, interaction_time):
    decay = temporal_decay(interaction_time)
    return weight * decay

def compute_interaction_weight(interaction, weights):
    signals = extract_interaction_signals(interaction)
    weight = 0.0

    # Implicit and Explicit Feedback 
    # Positive signals
    weight += signals["rating"] * weights["rating"]
    weight += signals["favourite"] * weights["favourite"]
    weight += signals["review"] * weights["review"]
    weight += signals["click"] * weights["click"]

    # Negative signals
    weight -= signals["not_interested"] * weights["not_interested"]
    weight -= signals["skip"] * weights["skip"]

    # Contextual signal
    weight += signals["viewing_time"] * weights["viewing_time"]

    # Temporal Decay to give importance to newer interactions 
    interaction_time = interaction.get("interaction_time")
    weight = apply_temporal_decay(weight, interaction_time)

    return weight

# ResNet50
# Preprocess images the same way as they were trained on ImageNet
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std =[0.229, 0.224, 0.225]
    )
])

# Load embeddings
data = joblib.load('data/resnet50_embeddings.pkl')
embeddings_resnet = data['embeddings']
image_ids_resnet = data['image_ids']
embeddings_resnet_norm = embeddings_resnet / np.linalg.norm(embeddings_resnet, axis=1, keepdims=True)

pcaRESNET = PCA(n_components=512) 
pca_resnet = pcaRESNET.fit_transform(embeddings_resnet_norm)
resnet_norm = pca_resnet / np.linalg.norm(pca_resnet, axis=1, keepdims=True)

NUM_CLUSTERS = 20 
kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init=10)
cluster_labels = kmeans.fit_predict(resnet_norm)

# map cluster to indices
cluster_to_items = {i: [] for i in range(NUM_CLUSTERS)}
for idx, c in enumerate(cluster_labels):
    cluster_to_items[c].append(idx)

def score_paintings_from_interactions(interactions, embeddings, id_to_idx):
    """
    Implements:
    s(q) = Σ (w_i * sim(q, p_i)) / Σ w_i
    """

    N = embeddings.shape[0]
    scores = np.zeros(N)

    total_weight = 0.0

    for interaction in interactions:
        pid = interaction["painting_id"]
        w = interaction["weight"]

        # Skip weak signals
        if w < 1.0:
            continue

        if pid not in id_to_idx:
            continue

        idx = id_to_idx[pid]
        vec = embeddings[idx]   
        sim = embeddings @ vec   

        scores += w * sim
        total_weight += abs(w)

    if total_weight == 0:
        return None

    scores /= total_weight
    # Normalize to [0,1]
    min_s = scores.min()
    max_s = scores.max()

    if max_s > min_s:
        scores = (scores - min_s) / (max_s - min_s)
    return scores

def get_seen_paintings(user_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT painting_id
        FROM recommendations
        WHERE user_id = %s
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

    # Build user scores
    interactions = fetch_user_interactions(user_id)
    for i in interactions:
        i["weight"] = compute_interaction_weight(i, DEFAULT_INTERACTION_WEIGHTS)

    scores = score_paintings_from_interactions(interactions, resnet_norm, id_to_idx)

    if scores is None:
        return jsonify({
            "success": False,
            "error": "No strong interaction signal"
        }), 200

    # Prepare ranking input
    seen = get_seen_paintings(user_id)
    ranked_indices = np.argsort(scores)[::-1]
    filtered_ranked = [
        idx for idx in ranked_indices
        if int(image_ids[idx]) not in seen
        and scores[idx] >= 0.05
    ]

    # Cluster-based diversification
    selected = []
    cluster_counts = {c: 0 for c in range(NUM_CLUSTERS)}

    while len(selected) < k and filtered_ranked:

        best_idx = None
        best_score = -1
        best_cluster = None

        for idx in filtered_ranked:

            cluster = cluster_labels[idx]
            base_score = scores[idx]

            # soft penalty for repeated clusters
            diversity_penalty = 0.15 * cluster_counts[cluster]

            adjusted_score = base_score - diversity_penalty

            if adjusted_score > best_score:
                best_score = adjusted_score
                best_idx = idx
                best_cluster = cluster

        if best_idx is None:
            break

        selected.append(best_idx)
        cluster_counts[best_cluster] += 1

        filtered_ranked.remove(best_idx)

    # Build response
    results = []
    db_rows = []

    for rank, idx in enumerate(selected):
        painting_id = int(image_ids[idx])
        score = float(scores[idx])

        results.append({
            "painting_id": painting_id,
            "score": score
        })

        db_rows.append((
            session_id,
            user_id,
            painting_id,
            request_id,
            rank,
            score,
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
    conn = get_db_connection()
    cur = conn.cursor()

    execute_values(cur, """
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
    """, db_rows)

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "user_id": user_id,
        "request_id": request_id,
        "recommendations": final_results
    })

# SBERT
processed_data = joblib.load("data/processed_data.pkl")
embedding_matrices = joblib.load("data/SBERT_embedding_matrices.pkl")
# full similarity matrices are unfeasable 

WEIGHTS_SBERT = {
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

WEIGHTS_SBERT = normalise_weights(WEIGHTS_SBERT)

painting_id_to_index = {
    pid: idx for idx, (_, pid) in enumerate(processed_data)
}

def get_seen_paintings_explore(user_id, session_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT painting_id
        FROM recommendations_sbert
        WHERE user_id = %s
            AND session_id = %s
    """, (user_id, session_id))

    seen = {row[0] for row in cur.fetchall()}

    cur.close()
    conn.close()
    return seen

@app.route("/api/recommend_sbert", methods=["POST"]) 
def recommend_sbert(): 
    data = request.json 
    user_id = data["user_id"] 
    session_id = data.get("session_id") 
    
    if not user_id or not session_id: 
        return jsonify({ "success": False, 
                        "error": "Missing user_id or session_id" }), 400 
        
    k = data.get("k", 10) 
    request_id = generate_request_id() 
    interactions = fetch_sbert_user_interactions(user_id) 
    
    for i in interactions: 
        i["weight"] = compute_interaction_weight(i, DEFAULT_INTERACTION_WEIGHTS) 

    positive_profiles = {}
    negative_profiles = {}

    positive_weights = {}
    negative_weights = {}

    for field, matrix in embedding_matrices.items():

        dim = matrix.shape[1]

        positive_profiles[field] = np.zeros(dim)
        negative_profiles[field] = np.zeros(dim)

        positive_weights[field] = 0.0
        negative_weights[field] = 0.0
        
    for interaction in interactions:
        pid = interaction["painting_id"]
        w = interaction["weight"]

        if abs(w) < 0.1:
            continue

        if pid not in painting_id_to_index:
            continue

        idx = painting_id_to_index[pid]

        for field, matrix in embedding_matrices.items():
            vec = matrix[idx]

            if w > 0:
                positive_profiles[field] += w * vec
                positive_weights[field] += w

            else:
                negative_profiles[field] += abs(w) * vec
                negative_weights[field] += abs(w)
            
    # normalise per field 
    field_scores = {}
    for field, matrix in embedding_matrices.items():

        pos_sim = np.zeros(matrix.shape[0])
        neg_sim = np.zeros(matrix.shape[0])

        # Positive profile
        if positive_weights[field] > 0:
            pos_profile = (positive_profiles[field] / positive_weights[field])
            pos_profile /= (np.linalg.norm(pos_profile) + 1e-8)
            pos_sim = matrix @ pos_profile

        # Negative profile
        if negative_weights[field] > 0:
            neg_profile = (negative_profiles[field] / negative_weights[field])
            neg_profile /= (np.linalg.norm(neg_profile) + 1e-8)
            neg_sim = matrix @ neg_profile

        # Final field score
        field_scores[field] = pos_sim - (0.5 * neg_sim)
        
    scores = np.zeros(len(image_ids)) 
    for field, sim in field_scores.items(): 
        scores += WEIGHTS_SBERT.get(field, 0) * sim 
        
    # scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-8) 
    scores = np.clip(scores, -1.0, 1.0)
    top_k_idx = np.argsort(scores)[::-1] 

    seen = get_seen_paintings_explore(user_id, session_id) 
    results = [] 
    db_rows = [] 
    rank = 0 
    
    for idx in top_k_idx: 
        painting_id = int(image_ids[idx]) 
        score = float(scores[idx]) 
        
        if painting_id in seen: 
            continue 
        
        if score < 0.05:
            continue 
        
        results.append({ 
            "painting_id": painting_id, 
            "score": score 
            }) 
        
        db_rows.append(( 
            session_id, 
            user_id, 
            painting_id, 
            request_id, 
            rank, 
            score, 
            datetime.utcnow() 
            )) 
        
        rank += 1 
        
        if rank >= k: 
            break 
        
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
            "request_id": request_id }) 
        
    conn = get_db_connection() 
    cur = conn.cursor() 
    
    execute_values(cur, """ 
                    INSERT INTO recommendations_sbert ( 
                    session_id, 
                    user_id, 
                    painting_id, 
                    request_id, 
                    rank, 
                    score, 
                    created_at 
                    ) VALUES %s 
                    """, db_rows) 
    
    conn.commit() 
    cur.close() 
    conn.close() 
    
    return jsonify({ 
        "user_id": user_id, 
        "request_id": request_id, 
        "recommendations": final_results 
        })


#     with torch.no_grad():
#         field_scores = {}

#         for field, matrix in embedding_matrices_torch.items():

#             field_scores[field] = torch.zeros(
#                 matrix.shape[0],
#                 dtype=torch.float32,
#                 device=device
#             )

#         total_weight = 0.0

#         for interaction in interactions:

#             pid = interaction["painting_id"]
#             w = interaction["weight"]

#             if pid not in painting_id_to_index:
#                 continue

#             idx = painting_id_to_index[pid]

#             for field, matrix in embedding_matrices_torch.items():

#                 vec = matrix[idx]
#                 sim = matrix @ vec

#                 field_scores[field] += w * sim

#             total_weight += abs(w)

#         if total_weight == 0:
#             return jsonify({
#                 "success": False,
#                 "error": "No strong interaction signal"
#             }), 200

#         for field in field_scores:
#             field_scores[field] /= total_weight

#         scores = torch.zeros(
#             len(image_ids),
#             dtype=torch.float32,
#             device=device
#         )

#         for field, sim in field_scores.items():
#             scores += WEIGHTS_SBERT.get(field, 0) * sim

#         scores = (
#             (scores - torch.min(scores)) /
#             (torch.max(scores) - torch.min(scores) + 1e-8)
#         )

#         scores = scores.cpu().numpy()
#     top_k_idx = np.argsort(scores)[::-1]
#     seen = get_seen_paintings_explore(user_id)


# CLIP
# Load CLIP Model and Processor
print("CLIP device: ", device)
print("NST Device: ", device_nst)
print(torch.cuda.is_available())
model_clip = CLIPModel.from_pretrained("openai/clip-vit-base-patch32", use_safetensors=True).to(device)
model_clip.eval()
processor_clip = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

image_tensors = joblib.load('data/image_tensors.pkl')
text_tensors = joblib.load('data/text_tensors.pkl')

image_matrix = np.array(image_tensors, dtype=np.float32)
text_matrix = np.array(text_tensors, dtype=np.float32)

image_matrix = image_matrix / np.linalg.norm(image_matrix, axis=1, keepdims=True)
text_matrix = text_matrix / np.linalg.norm(text_matrix, axis=1, keepdims=True)

def retrieve_by_text(query, top_k=10):
    inputs = processor_clip(text=query, return_tensors="pt", padding=True, truncation=True).to(device)

    with torch.no_grad():
        q_emb = model_clip.get_text_features(**inputs)
        print("Embedding type: ", type(q_emb))
        q_emb = q_emb / q_emb.norm(dim=-1, keepdim=True)

    q_emb = q_emb.cpu().numpy()

    # cosine similarity
    scores = image_matrix @ q_emb.T  
    top_k_idx = np.argsort(scores[:, 0])[::-1][:top_k]

    return top_k_idx, scores[top_k_idx]

def retrieve_by_image(image, top_k=10):
    inputs = processor_clip(images=image, return_tensors="pt").to(device)

    with torch.no_grad():
        q_emb = model_clip.get_image_features(**inputs)
        q_emb = q_emb / q_emb.norm(dim=-1, keepdim=True)

    q_emb = q_emb.cpu().numpy()

    # cosine similarity
    scores = image_matrix @ q_emb.T
    top_k_idx = np.argsort(scores[:, 0])[::-1][:top_k]

    return top_k_idx, scores[top_k_idx]

def hybrid_retrieve(query, alpha=0.6, top_k=10):
    inputs = processor_clip(text=query, return_tensors="pt", padding=True, truncation=True).to(device)

    with torch.no_grad():
        text_emb = model_clip.get_text_features(**inputs)
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

def build_clip_user_profile(interactions, image_matrix, text_matrix, id_to_idx):
    image_dim = image_matrix.shape[1]
    text_dim = text_matrix.shape[1]

    # Image profiles
    positive_image_profile = np.zeros(image_dim, dtype=np.float32)
    negative_image_profile = np.zeros(image_dim, dtype=np.float32)

    # Text profiles
    positive_text_profile = np.zeros(text_dim, dtype=np.float32)
    negative_text_profile = np.zeros(text_dim, dtype=np.float32)

    positive_weight = 0.0
    negative_weight = 0.0

    for interaction in interactions:
        pid = interaction["painting_id"]
        w = interaction["weight"]

        # Ignore weak signals
        if abs(w) < 0.1:
            continue

        if pid not in id_to_idx:
            continue

        idx = id_to_idx[pid]
        image_vec = image_matrix[idx]
        text_vec = text_matrix[idx]

        # Positive
        if w > 0:
            positive_image_profile += w * image_vec
            positive_text_profile += w * text_vec
            positive_weight += w

        # Negative
        else:
            negative_image_profile += abs(w) * image_vec
            negative_text_profile += abs(w) * text_vec
            negative_weight += abs(w)

    # Normalize positive profiles
    if positive_weight > 0:
        positive_image_profile /= positive_weight
        positive_text_profile /= positive_weight

        positive_image_profile /= (np.linalg.norm(positive_image_profile) + 1e-8)
        positive_text_profile /= (np.linalg.norm(positive_text_profile) + 1e-8)

    # Normalize negative profiles
    if negative_weight > 0:
        negative_image_profile /= negative_weight
        negative_text_profile /= negative_weight

        negative_image_profile /= (np.linalg.norm(negative_image_profile) + 1e-8)
        negative_text_profile /= (np.linalg.norm(negative_text_profile) + 1e-8)

    return {
        "positive_image": positive_image_profile,
        "negative_image": negative_image_profile,
        "positive_text": positive_text_profile,
        "negative_text": negative_text_profile,
        "positive_weight": positive_weight,
        "negative_weight": negative_weight
    }

def get_seen_paintings_search(user_id, session_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT painting_id
        FROM recommendations_clip
        WHERE user_id = %s
            AND session_id = %s
    """, (user_id, session_id))

    seen = {row[0] for row in cur.fetchall()}

    cur.close()
    conn.close()
    return seen

@app.route("/api/search_clip", methods=["POST"])
def search_clip():
    try:
        data = request.get_json()

        user_id = data.get("user_id")
        session_id = data.get("session_id")
        request_id = data.get("request_id")
        query_text = data.get("query_text")

        if not user_id or not session_id or not query_text:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO clip_search_queries (user_id, session_id, query_text)
            VALUES (%s, %s, %s)
            RETURNING query_id;
        """, (user_id, session_id, query_text))

        query_id = cur.fetchone()[0]
        top_k_idx, scores = hybrid_retrieve(query_text, top_k=30)

        painting_ids = top_k_idx.tolist()
        scores = scores.flatten().tolist()
        db_paintings = fetch_paintings(painting_ids)
        db_map = {p["painting_id"]: p for p in db_paintings}

        final_results = []
        db_rows = []
        for rank, (pid, score) in enumerate(zip(painting_ids, scores), start=1):
            meta = db_map.get(pid)

            if not meta:
                continue

            image_url = build_painting_url(meta["image_path"])
            final_results.append({
                "painting_id": pid,
                "score": score,
                "image_url": image_url,
                "request_id": request_id
            })

            db_rows.append((
                session_id,
                user_id,
                pid,
                request_id,
                rank,
                float(score),
                datetime.utcnow()
            ))

        if db_rows:
            execute_values(cur, """
                INSERT INTO recommendations_clip (
                    session_id,
                    user_id,
                    painting_id,
                    request_id,
                    rank,
                    score,
                    created_at
                )
                VALUES %s
            """, db_rows)

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "user_id": user_id,
            "request_id": request_id,
            "query_id": query_id,
            "recommendations": final_results
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/api/recommend_clip", methods=["POST"])
def recommend_clip():
    try:
        data = request.get_json()

        user_id = data.get("user_id")
        session_id = data.get("session_id")

        if not user_id or not session_id:
            return jsonify({
                "success": False,
                "error": "Missing user_id or session_id"
            }), 400

        k = data.get("k", 10)
        request_id = generate_request_id()

        # Fetch interactions
        interactions = fetch_clip_user_interactions(user_id)
        for i in interactions:
            i["weight"] = compute_interaction_weight(i, DEFAULT_INTERACTION_WEIGHTS)

        # Build CLIP user profiles
        profiles = build_clip_user_profile(interactions, image_matrix, text_matrix, painting_id_to_index)

        # Validate interaction signal
        if (
            profiles["positive_weight"] == 0
            and profiles["negative_weight"] == 0
        ):
            return jsonify({
                "success": False,
                "error": "No interaction signal available"
            }), 200

        # IMAGE SIMILARITIES
        image_positive_scores = np.zeros(len(image_matrix))
        image_negative_scores = np.zeros(len(image_matrix))

        if profiles["positive_weight"] > 0:
            image_positive_scores = (image_matrix @ profiles["positive_image"])

        if profiles["negative_weight"] > 0:
            image_negative_scores = (image_matrix @ profiles["negative_image"])

        image_scores = (image_positive_scores - 0.5 * image_negative_scores)

        # TEXT SIMILARITIES
        text_positive_scores = np.zeros(len(text_matrix))
        text_negative_scores = np.zeros(len(text_matrix))

        if profiles["positive_weight"] > 0:
            text_positive_scores = (text_matrix @ profiles["positive_text"])

        if profiles["negative_weight"] > 0:
            text_negative_scores = (text_matrix @ profiles["negative_text"])

        text_scores = (text_positive_scores - 0.5 * text_negative_scores)

        # Hybrid fusion of text and image scores
        alpha = 0.6
        scores = (alpha * image_scores + (1 - alpha) * text_scores)

        # Normalize
        min_score = scores.min()
        max_score = scores.max()

        if max_score > min_score:
            scores = ((scores - min_score) / (max_score - min_score))

        # Remove already seen paintings
        seen = get_seen_paintings_search(user_id, session_id)
        ranked_indices = np.argsort(scores)[::-1]

        results = []
        db_rows = []

        rank = 0

        for idx in ranked_indices:

            painting_id = int(image_ids[idx])
            score = float(scores[idx])

            # Skip previously interacted paintings
            if painting_id in seen:
                continue

            # Optional threshold
            if score < 0.05:
                continue

            results.append({
                "painting_id": painting_id,
                "score": score
            })

            db_rows.append((
                session_id,
                user_id,
                painting_id,
                request_id,
                rank,
                score,
                datetime.utcnow()
            ))

            rank += 1

            if rank >= k:
                break

        # Fetch painting metadata
        painting_ids = [
            r["painting_id"]
            for r in results
        ]

        db_paintings = fetch_paintings(painting_ids)

        db_map = {
            p["painting_id"]: p
            for p in db_paintings
        }

        final_results = []
        for r in results:

            pid = r["painting_id"]

            meta = db_map.get(pid)

            if not meta:
                continue

            final_results.append({
                "painting_id": pid,
                "score": r["score"],
                "image_url": build_painting_url(
                    meta["image_path"]
                ),
                "request_id": request_id
            })

        # Store recommendations
        conn = get_db_connection()
        cur = conn.cursor()

        if db_rows:

            execute_values(cur, """
                INSERT INTO recommendations_clip (
                    session_id,
                    user_id,
                    painting_id,
                    request_id,
                    rank,
                    score,
                    created_at
                )
                VALUES %s
            """, db_rows)

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "user_id": user_id,
            "request_id": request_id,
            "recommendations": final_results
        })

    except Exception as e:

        print("recommend_clip ERROR:", str(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    

# TO-RUN: python app.py
if __name__ == "__main__":
    app.run(debug=True, threaded=True, use_reloader=False)