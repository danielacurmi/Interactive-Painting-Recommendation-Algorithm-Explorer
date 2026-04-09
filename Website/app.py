# all necessary imports are listed below
from flask import Flask, render_template, jsonify, send_from_directory, request, send_file
import os, random, cv2, re, pywt, json
import numpy as np
import matplotlib.pyplot as plt
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
from collections import defaultdict

#from Image_Feature_extraction.ipynb import run_style_transfer

app = Flask(__name__)
DATASET_PATH = r'C:\Users\danie\Desktop\_\Daniela Curmi\University\Final Year Project\Final Year Project Code Implementation\Website'
app.secret_key = "secret"  # Needed for session storage
CORS(app)

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
    conn = psycopg2.connect(
        host="localhost",
        database="ART_RECSYS_DB",
        user="postgres",
        password="Catmelon304!"
    )
    return conn

# Helper Function for User IP address
def get_user_ip():
    """
    Retrieve user's IP address from the request
    """
    # Handles proxy situations
    if request.headers.get('X-Forwarded-For'):
        ip = request.headers.get('X-Forwarded-For').split(',')[0]
    else:
        ip = request.remote_addr
    return ip

# Check User
@app.route("/api/check_user", methods=["GET"])
def check_user():
    """
    Determine if user IP already exists in database
    """
    try:
        ip_address = get_user_ip()

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT user_id
            FROM users
            WHERE ip_address = %s
        """

        cursor.execute(query, (ip_address,))
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
        ip_address = get_user_ip()

        conn = get_db_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO users (consent_form, ip_address)
            VALUES (%s, %s)
            RETURNING user_id
        """

        cursor.execute(insert_query, (True, ip_address))
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
@app.route("/api/create_session", methods=["POST"])
def create_session():
    try:
        data = request.get_json()
        user_id = data.get("user_id")

        if not user_id:
            return jsonify({
                "success": False,
                "error": "user_id is required"
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO sessions (user_id, session_start)
            VALUES (%s, CURRENT_TIMESTAMP)
            RETURNING session_id
        """

        cursor.execute(insert_query, (user_id,))
        session_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "session_id": session_id
        })
    except Exception as e:
        print("ERROR in /api/create_session:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    
# Keep the same session when reloading the website with localStorage Cache then end session if session exceeds 4 days or new session starded    
@app.route("/api/end_session", methods=["POST"]) 
def end_session(): 
    try: 
        data = request.get_json(silent=True)

        if not data:
            data = json.loads(request.data)

        session_id = data.get("session_id")

        if not session_id:
            return jsonify({
                "success": False,
                "error": "session_id is required"
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        update_query = """
            UPDATE sessions
            SET session_end = CURRENT_TIMESTAMP
            WHERE session_id = %s AND session_end IS NULL
        """

        cursor.execute(update_query, (session_id,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "success": False,
                "error": "Invalid or already ended session"
            }), 400

        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("ERROR in /api/end_session:", e)
        return jsonify({"success": False, "error": str(e)}), 500

def close_expired_sessions(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        UPDATE sessions
        SET session_end = CURRENT_TIMESTAMP
        WHERE user_id = %s
        AND session_end IS NULL
        AND last_activity < CURRENT_TIMESTAMP - INTERVAL '2 minutes'
    """

    cursor.execute(query, (user_id,))
    conn.commit()

    cursor.close()
    conn.close()

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

# Interaction Events Logging
@app.route("/api/interaction_event_logging", methods=["GET"])
def interaction_event_logging():
    a = "hello"
    return a

# Interaction Summary
@app.route("/api/interaction_event_summary", methods=["GET"])
def interaction_event_summary():
    a = "hello"
    return a

#interaction_events
#interaction_summary 

#event_id, session_id, painting_id, event_type, event_value

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
    return send_from_directory(
        os.path.join(DATASET_PATH, "paintings"),
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

    image_path = os.path.join(DATASET_PATH, row["image_path"])
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

# @app.route("/api/image-info/<path:filename>")
# def image_info(filename):
#     image_path = os.path.join(DATASET_PATH, filename)

#     # parse filename for genre, artist, painting, and year 
#     parts = os.path.splitext(os.path.basename(filename))[0].split("_")
#     artist_part = parts[0]
#     painting_part = "_".join(parts[1:])
#     match = re.search(r"\b\d{4}\b", painting_part)
#     if match:
#         year = match.group(0)
#         painting_part = painting_part.replace(year, "").replace("-", " ")
#     else:
#         year = "Unknown"
#         painting_part = painting_part.replace("-", " ")

#     genre = os.path.basename(os.path.dirname(image_path)).replace("_", " ").title()

#     artist = artist_part.replace("-", " ").title()
#     painting_name = painting_part.replace("-", " ").title()

#     image = cv2.imread(image_path)
#     image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

#     palette, palette_type = extract_visual_features(image_rgb)

#     return jsonify({
#         "genre": genre,
#         "artist": artist,
#         "painting_name": painting_name,
#         "year": year,
#         "palette": palette.tolist(),
#         "palette_type": palette_type
#     })

# folder for saving generated results
GENERATED_DIR = os.path.join(os.getcwd(), "paintings\AI-Generated Images")
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

# Utilities 
imsize = 512 if torch.cuda.is_available() else 256  # choose smaller if no GPU

loader = transforms.Compose([
    transforms.Resize(imsize),
    transforms.CenterCrop(imsize),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                        std =[0.229, 0.224, 0.225])
])

unloader = transforms.Compose([
    transforms.Normalize(mean=[0.,0.,0.],
                        std=[1/0.229,1/0.224,1/0.225]),
    transforms.Normalize(mean=[-0.485, -0.456, -0.406],
                        std=[1.,1.,1.]),
    transforms.Lambda(lambda t: torch.clamp(t, 0, 1)),
    transforms.ToPILImage()
])

def load_image(path, transform=loader, device=device):
    image = Image.open(path).convert('RGB')
    image = transform(image).unsqueeze(0)  # add batch dim
    return image.to(device, torch.float)

def tensor_to_pil(tensor):
    image = tensor.cpu().clone().squeeze(0)
    return unloader(image)

def save_image(tensor, path):
    image = tensor.cpu().clone().squeeze(0)
    pil = unloader(image)
    pil.save(path)

# Gram matrix 
def gram_matrix(feature_maps):
    # feature_maps: tensor of shape [batch=1, C, H, W]
    b, c, h, w = feature_maps.size()
    features = feature_maps.view(c, h * w)  # [C, H*W]
    G = torch.mm(features, features.t())  # [C, C]
    return G.div(c * h * w)  # normalize

# Model to extract features 
class VGGFeatures(nn.Module):
    def __init__(self, vgg, content_layers, style_layers):
        super().__init__()
        self.vgg_layers = vgg.features.eval()
        self.content_layers = content_layers
        self.style_layers = style_layers

    def forward(self, x):
        content_feats = {}
        style_feats = {}
        cur = x
        for name, layer in self.vgg_layers._modules.items():
            cur = layer(cur)
            # name is string index: '0','1',... we map to conv names by counting convs
            # We'll use a mapping approach below (see usage) to pick nice names.
            # For simplicity, the caller will select layers by module index strings.
            if name in self.content_layers:
                content_feats[name] = cur
            if name in self.style_layers:
                style_feats[name] = cur
        return content_feats, style_feats

# Loss functions (MSE) 
mse_loss = nn.MSELoss()

def compute_content_loss(gen_feat, content_feat):
    return mse_loss(gen_feat, content_feat)

def compute_style_loss(gen_feat, style_gram):
    gen_gram = gram_matrix(gen_feat)
    return mse_loss(gen_gram, style_gram)

def total_variation_loss(img):
    # img [1,3,H,W]
    x_diff = img[:, :, :, 1:] - img[:, :, :, :-1]
    y_diff = img[:, :, 1:, :] - img[:, :, :-1, :]
    return torch.sum(torch.abs(x_diff)) + torch.sum(torch.abs(y_diff))

# Main style transfer function 
def run_style_transfer(content_img_path, style_img_path,
                    output_path='output.jpg',
                    content_weight=1e0,
                    style_weight=1e6,
                    tv_weight=1e-6,
                    num_steps=500,
                    init_from_content=True,
                    show_progress=False):
    # Load images
    content_img = load_image(content_img_path)
    style_img = load_image(style_img_path)

    # Load pretrained VGG19
    vgg = models.vgg19(pretrained=True).to(device).eval()

    # Choose layers by their module index in vgg.features
    # Classic choices (PyTorch vgg module indices may differ between versions):
    # conv1_1: 0, conv2_1: 5, conv3_1: 10, conv4_1: 19, conv4_2: 21, conv5_1: 28
    style_layer_idxs = ['0', '5', '10', '19', '28']   # style layers
    content_layer_idxs = ['21']                       # content layer (conv4_2)
    feature_extractor = VGGFeatures(vgg, content_layer_idxs, style_layer_idxs)

    # Precompute style features' Gram matrices
    _, style_feats = feature_extractor(style_img)
    style_grams = {layer: gram_matrix(feat).detach() for layer, feat in style_feats.items()}

    # Precompute content features
    content_feats, _ = feature_extractor(content_img)
    content_targets = {layer: feat.detach() for layer, feat in content_feats.items()}

    # Initialize generated image
    if init_from_content:
        generated = content_img.clone().requires_grad_(True)
    else:
        generated = torch.randn_like(content_img).requires_grad_(True)

    # Set optimizer: LBFGS or Adam
    # When using ADAM less style and more accurate content - do more testing
    optimizer = optim.Adam([generated], lr=0.02)
    # optimizer = optim.LBFGS([generated], max_iter=20, lr=1.0)
    # optimizer = optim.Adam([generated], lr=0.02)

    run = [0]
    while run[0] <= num_steps:
        def closure():
            optimizer.zero_grad()
            gen_content_feats, gen_style_feats = feature_extractor(generated)

            # content loss
            c_loss = 0.0
            for layer in content_targets:
                c_loss += compute_content_loss(gen_content_feats[layer], content_targets[layer])
            c_loss = c_loss * content_weight

            # style loss
            s_loss = 0.0
            for layer in style_grams:
                s_loss += compute_style_loss(gen_style_feats[layer], style_grams[layer])
            s_loss = s_loss * style_weight

            # total variation loss (optional)
            tv = tv_weight * total_variation_loss(generated)

            loss = c_loss + s_loss + tv
            loss.backward()

            if show_progress and run[0] % 50 == 0:
                print(f"Step {run[0]}/{num_steps}, total_loss: {loss.item():.4f}, content: {c_loss.item():.4f}, style: {s_loss.item():.4f}, tv: {tv.item():.6f}")

            run[0] += 1
            return loss

        optimizer.step(closure)

    # Clamp output and save
    with torch.no_grad():
        final_img = generated.clone().detach()
        final_img = torch.clamp(final_img, -5, 5)  # keep in some numeric range
    save_image(final_img, output_path)
    print(f"Saved stylized image to {output_path}")

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

    # Curated 
    for aid, name, _, _ in head:
        if len(selected) >= 3:
            break
        if aid not in used_ids:
            selected.append(make_concept("artist", name, {"artist_id": aid}))
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
                selected.append(make_concept("artist", name, {"artist_id": aid}))
                used_ids.add(aid)
                break  # move to next group

    # Long-tail
    random.shuffle(tail)
    for aid, name, _, _ in tail:
        if len(selected) >= 8:
            break
        if aid not in used_ids:
            selected.append(make_concept("artist", name, {"artist_id": aid}))
            used_ids.add(aid)

    # Fallback
    random.shuffle(artist_rows)
    for aid, name, _, _ in artist_rows:
        if len(selected) >= k:
            break
        if aid not in used_ids:
            selected.append(make_concept("artist", name, {"artist_id": aid}))
            used_ids.add(aid)

    return selected[:k]

def sample_styles(styles_with_freq, k=7):
    head, tail = split_head_tail(styles_with_freq, 0.3)

    selected = []
    used = set()

    # curated
    for s, _ in head:
        if len(selected) >= 2:
            break
        if s not in used:
            selected.append(make_concept("style", s))
            used.add(s)

    # diverse
    mid = head[2:]
    random.shuffle(mid)

    for s, _ in mid:
        if len(selected) >= 5:
            break
        if s not in used:
            selected.append(make_concept("style", s))
            used.add(s)

    # long-tail
    random.shuffle(tail)
    for s, _ in tail:
        if len(selected) >= 7:
            break
        if s not in used:
            selected.append(make_concept("style", s))
            used.add(s)

    # fallback
    random.shuffle(styles_with_freq)
    for s, _ in styles_with_freq:
        if len(selected) >= k:
            break
        if s not in used:
            selected.append(make_concept("style", s))
            used.add(s)

    return selected[:k]

def sample_genres(genres_with_freq, k=7):
    head, tail = split_head_tail(genres_with_freq, 0.3)

    selected = []
    used = set()

    # curated
    for g, _ in head:
        if len(selected) >= 2:
            break
        if g not in used:
            selected.append(make_concept("genre", g))
            used.add(g)

    # diverse
    mid = head[2:]
    random.shuffle(mid)

    for g, _ in mid:
        if len(selected) >= 5:
            break
        if g not in used:
            selected.append(make_concept("genre", g))
            used.add(g)

    # long-tail
    random.shuffle(tail)
    for g, _ in tail:
        if len(selected) >= 7:
            break
        if g not in used:
            selected.append(make_concept("genre", g))
            used.add(g)

    # fallback
    random.shuffle(genres_with_freq)
    for g, _ in genres_with_freq:
        if len(selected) >= k:
            break
        if g not in used:
            selected.append(make_concept("genre", g))
            used.add(g)

    return selected[:k]

def sample_periods(k=5):
    selected = random.sample(PERIODS, k)
    return [
        make_concept("period", name, {"start": start, "end": end})
        for name, start, end in selected
    ]

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

@app.route("/api/log_user_preferences", methods=["POST"])
def log_user_preferences():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # TO-DO:
        # log user preferences from cold start page

        return jsonify({
            "success": True
        })

    except Exception as e:
        print("ERROR in /api/log_user_preferences:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    
# TO-RUN: python app.py
if __name__ == "__main__":
    app.run(debug=True)