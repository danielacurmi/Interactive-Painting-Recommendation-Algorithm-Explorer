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

#from Image_Feature_extraction.ipynb import run_style_transfer

app = Flask(__name__)
DATASET_PATH = r'C:\Users\danie\Desktop\_\Daniela Curmi\University\Final Year Project\Final Year Project Code Implementation\Website\paintings'
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

@app.route("/api/random-images/<int:n>")
def random_images(n):
    sample = random.sample(all_images, min(n, len(all_images)))
    return jsonify(sample)

@app.route("/paintings/<path:filename>")
def serve_image(filename):
    return send_from_directory(DATASET_PATH, filename)

# -----------------------------
# DATABASE CONNECTION
# -----------------------------
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="ART_RECSYS_DB",
        user="postgres",
        password="Catmelon304!"
    )
    return conn

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
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

# -----------------------------
# CHECK USER ENDPOINT
# -----------------------------
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

        return jsonify({"exists": bool(result)})

    except Exception as e:
        print("ERROR in /api/check_user:", e)
        return jsonify({"error": str(e)}), 500
    
# -----------------------------
# CREATE USER ENDPOINT
# -----------------------------
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
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# -----------------------------
# SESSION 
# -----------------------------
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

        return json({
            "success": True,
            "session_id": session_id
        })
    except Exception as e:
        print("ERROR in /api/create_session:", e)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
@app.route("/api/end_session", methods=["POST"])
def end_session():
    try:
        data = request.get_json()
        session_id = data.get("session_id")

        conn = get_db_connection()
        cursor = conn.cursor()

        update_query = """
            UPDATE sessions
            SET session_end = CURRENT_TIMESTAMP
            WHERE session_id = %s
        """

        cursor.execute(update_query, (session_id,))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"success": True})

    except Exception as e:
        print("ERROR in /api/end_session:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    
# -----------------------------
# INTERACTION EVENTS LOGGING
# -----------------------------
@app.route("/api/interaction_event_logging", methods=["GET"])
def interaction_event_logging():
    a = "hello"
    return a

# -----------------------------
# INTERACTION SUMMARY 
# -----------------------------
@app.route("/api/interaction_event_summary", methods=["GET"])
def interaction_event_summary():
    a = "hello"
    return a

#interaction_events
#interaction_summary 

#event_id, session_id, painting_id, event_type, event_value


# Make sure the file exists
if not os.path.exists(FAVOURITES_FILE):
    with open(FAVOURITES_FILE, "w") as f:
        json.dump([], f)


@app.route("/api/add-favourite", methods=["POST"])
def add_favourite():
    data = request.get_json()
    image = data.get("image")

    if not image:
        return jsonify({"error": "No image provided"}), 400

    try:
        # Load current favourites
        with open(FAVOURITES_FILE, "r") as f:
            favourites = json.load(f)

        # Avoid duplicates
        if image not in favourites:
            favourites.append(image)

        # Save back to file
        with open(FAVOURITES_FILE, "w") as f:
            json.dump(favourites, f)

        return jsonify({"message": "Added to favourites"}), 200
    except Exception as e:
        print("Error saving favourite:", e)
        return jsonify({"error": str(e)}), 500


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

@app.route("/api/image-info/<path:filename>")
def image_info(filename):
    image_path = os.path.join(DATASET_PATH, filename)

    # parse filename for genre, artist, painting, and year 
    parts = os.path.splitext(os.path.basename(filename))[0].split("_")
    artist_part = parts[0]
    painting_part = "_".join(parts[1:])
    match = re.search(r"\b\d{4}\b", painting_part)
    if match:
        year = match.group(0)
        painting_part = painting_part.replace(year, "").replace("-", " ")
    else:
        year = "Unknown"
        painting_part = painting_part.replace("-", " ")

    genre = os.path.basename(os.path.dirname(image_path)).replace("_", " ").title()

    artist = artist_part.replace("-", " ").title()
    painting_name = painting_part.replace("-", " ").title()

    image = cv2.imread(image_path)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    palette, palette_type = extract_visual_features(image_rgb)

    return jsonify({
        "genre": genre,
        "artist": artist,
        "painting_name": painting_name,
        "year": year,
        "palette": palette.tolist(),
        "palette_type": palette_type
    })

# folder for saving generated results
GENERATED_DIR = os.path.join(os.getcwd(), "generated")
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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

# --------------- Utilities ---------------
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

# --------------- Gram matrix ---------------
def gram_matrix(feature_maps):
    # feature_maps: tensor of shape [batch=1, C, H, W]
    b, c, h, w = feature_maps.size()
    features = feature_maps.view(c, h * w)  # [C, H*W]
    G = torch.mm(features, features.t())  # [C, C]
    return G.div(c * h * w)  # normalize

# --------------- Model to extract features ---------------
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

# --------------- Loss functions (MSE) ---------------
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

# --------------- Main style transfer function ---------------
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

# TO-RUN: python app.py
if __name__ == "__main__":
    app.run(debug=True)