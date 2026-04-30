# all necessary imports are listed below
from flask import Flask, render_template, jsonify, send_from_directory, request, send_file
import os, random, cv2, re, pywt, json
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from skimage.feature import local_binary_pattern
from flask_cors import CORS
import torch
import torch.optim as optim
from torchvision import transforms, models
from PIL import Image
from datetime import datetime
import psycopg2
import psycopg2.extras
from collections import defaultdict 
from torchvision.models import VGG19_Weights
import imageio
import joblib

#from Image_Feature_extraction.ipynb import run_style_transfer

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

# Move to Database
FAVOURITES_FILE = "favourites.json"
GENERATED_FILE = "generated_art.json"

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

def get_or_create_session(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check for active session within 24 hours
    cursor.execute("""
        SELECT session_id
        FROM sessions
        WHERE user_id = %s
        AND session_end IS NULL
        AND session_start >= CURRENT_TIMESTAMP - INTERVAL '1 day'
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()

    if row:
        session_id = row[0]
    else:
        # Expire any stale sessions
        cursor.execute("""
            UPDATE sessions
            SET session_end = CURRENT_TIMESTAMP
            WHERE user_id = %s
            AND session_end IS NULL
        """, (user_id,))

        # Create new session
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

def log_event(session_id, user_id, painting_id, event_type, metadata=None):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO interaction_events (session_id, user_id, painting_id, event_type, timestamp)
        VALUES (%s, %s, %s, %s, NOW())
        RETURNING event_id;
    """, (session_id, user_id, painting_id, event_type))

    event_id = cur.fetchone()[0]

    conn.commit()
    cur.close()
    conn.close()

    return event_id

def ensure_summary(session_id, user_id, painting_id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO interaction_summary (session_id, user_id, painting_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (session_id, user_id, painting_id)
        DO NOTHING;
    """, (session_id, user_id, painting_id))

    conn.commit()
    cur.close()
    conn.close()

def update_summary(session_id, user_id, painting_id, event_type, value=None):
    conn = get_db_connection()
    cur = conn.cursor()

    if event_type == "view_end":
        cur.execute("""
            UPDATE interaction_summary
            SET viewing_time_seconds = viewing_time_seconds + %s
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (value, session_id, user_id, painting_id))

    elif event_type == "favourite":
        cur.execute("""
            UPDATE interaction_summary
            SET favourite = 1
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "click":
        cur.execute("""
            UPDATE interaction_summary
            SET click = 1,
                skip = 0
            WHERE session_id=%s AND user_id=%s AND painting_id=%s;
        """, (session_id, user_id, painting_id))

    elif event_type == "save_gallary":
        cur.execute("""
            UPDATE interaction_summary
            SET save_gallary = 1
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
            SET not_interested = 1
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
    data = request.json

    session_id = data.get("session_id")
    user_id = data.get("user_id")
    painting_id = data.get("painting_id")
    event_type = data.get("event_type")
    value = data.get("value")  # optional (rating, time, review)

    if event_type not in EVENT_TYPES:
        return jsonify({"error": "Invalid event type"}), 400

    event_id = log_event(session_id, user_id, painting_id, event_type)
    ensure_summary(session_id, user_id, painting_id)
    update_summary(session_id, user_id, painting_id, event_type, value)

    return jsonify({
        "status": "success",
        "event_id": event_id
    })

# Get painting and artist metadata for each painting along with the image from the respective file path
@app.route("/api/random-images/<int:n>")
def random_images(n):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT painting_id, image_path
        FROM paintings
        ORDER BY RANDOM()
        LIMIT %s;
    """, (n,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify(rows)

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
    
# Make sure the file exists
if not os.path.exists(FAVOURITES_FILE):
    with open(FAVOURITES_FILE, "w") as f:
        json.dump([], f)

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
    try:
        with open(FAVOURITES_FILE, "r") as f:
            favourites = json.load(f)
        return jsonify(favourites)
    except Exception as e:
        print("Error reading favourites:", e)
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
        num_steps=300,
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
    ("Medieval", 1400, 1600),
    ("Renaissance", 1400, 1600),
    ("Baroque", 1600, 1750),
    ("Neoclassicism", 1750, 1850),
    ("Impressionism", 1870, 1900),
    ("Modern", 1900, 1960),
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
                WHERE year_created BETWEEN %s AND %s
            """, (start, end))

    else:
        return []

    return [r[0] for r in cursor.fetchall()]

image_tensors = joblib.load('image_tensors.pkl')
image_ids = joblib.load('ids.pkl')
image_matrix = np.array(image_tensors)  # (N, 512)
image_matrix = image_matrix / np.linalg.norm(image_matrix, axis=1, keepdims=True)

id_to_idx = {pid: i for i, pid in enumerate(image_ids)}

def get_thumbnail_for_concept(cursor, concept_type, label, top_k=5):
    """
    Returns a representative painting_id and the respective image_path
    """
    painting_ids = fetch_paintings_by_concept(cursor, concept_type, label)

    if len(painting_ids) == 0:
        return None

    # Step 1: filter valid embeddings
    valid_indices = [
        id_to_idx[pid]
        for pid in painting_ids
        if pid in id_to_idx
    ]

    if len(valid_indices) == 0:
        return None

    subset_embeddings = image_matrix[valid_indices]

    # Step 2: centroid
    centroid = np.mean(subset_embeddings, axis=0)
    centroid = centroid / np.linalg.norm(centroid)

    # Step 3: similarity to centroid
    sims = subset_embeddings @ centroid.T

    # Step 4: top-k nearest
    top_k_idx = np.argsort(sims)[-top_k:]

    # Step 5: random pick (bias reduction)
    chosen_local_idx = np.random.choice(top_k_idx)

    chosen_painting_id = painting_ids[chosen_local_idx]

    return chosen_painting_id

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
        painting_id = get_thumbnail_for_concept(cursor, concept_type, label)

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

# TO-RUN: python app.py
if __name__ == "__main__":
    app.run(debug=True)