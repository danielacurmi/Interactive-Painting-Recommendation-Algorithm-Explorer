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

#from Image_Feature_extraction.ipynb import run_style_transfer

app = Flask(__name__)
DATASET_PATH = r'C:\Users\danie\Desktop\'\Daniela Curmi\University\Third Year\Final Year Project\Final Year Project Code Implementation\Website\paintings'
app.secret_key = "secret"  # Needed for session storage
CORS(app)

FAVOURITES_FILE = "favourites.json"
GENERATED_FILE = "generated_art.json"

# TO-DO: replace with a DB ?
all_images = [] # Collect all images

for root, dirs, files in os.walk(DATASET_PATH):
    for file in files:
        if file.lower().endswith((".jpg", ".jpeg", ".png")):
            rel_path = os.path.relpath(os.path.join(root, file), DATASET_PATH)
            all_images.append(rel_path.replace("\\", "/"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/create")
def create_board():
    return render_template("create_board.html")

@app.route("/favourites")
def favourites():
    return render_template("favourites.html")

@app.route("/style_transfer")
def style_transfer():
    return render_template("style_transfer.html")

@app.route("/api/random-images/<int:n>")
def random_images(n):
    sample = random.sample(all_images, min(n, len(all_images)))
    return jsonify(sample)

@app.route("/paintings/<path:filename>")
def serve_image(filename):
    return send_from_directory(DATASET_PATH, filename)


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

    # (Optional) save info to JSON log
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

def extract_texture_features(image_rgb):
    # every pixel compared with 8 neighbours in a 1 pixel radius 
    def extract_lbp_features(image, neighbours=8, radius=1):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        lbp = local_binary_pattern(gray, neighbours, radius, method="uniform")
        
        # histogram of LBP
        hist, _ = np.histogram(lbp.ravel(),
                                bins=np.arange(0, neighbours + 3),
                                range=(0, neighbours + 2))
        hist = hist.astype("float")
        hist /= hist.sum()  
        
        plt.figure(figsize=(8,4))
        plt.bar(range(len(hist)), hist, tick_label=range(len(hist)), color="gray")
        plt.title(f"LBP Histogram (Neighbours={neighbours}, Radius={radius})")
        plt.xlabel("LBP Pattern")
        plt.ylabel("Normalized Frequency")
        plt.show()
        
        return hist, lbp

    # plot the histogram, visualize the LBP image and print feature vector
    hist, lbp_image = extract_lbp_features(image_rgb)
    plt.imshow(lbp_image, cmap="gray")
    plt.title("LBP Image")
    plt.axis("off")
    plt.show()
    print ("LBP feature vector: \n", hist, "\n")

    # produces a texture profile of the image across multiple orientations and scales
    def extract_gabor_features(image, k=31):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        features = []
        
        # define gabor parameters i.e. orientations(theta), scales(sigma), wavelengths(lamda)
        for theta in (0, np.pi/4, np.pi/2, 3*np.pi/4):  
            for sigma in (1, 3):  
                for lamda in (np.pi/4, np.pi/2):  
                    kernel = cv2.getGaborKernel((k, k), sigma, theta, lamda, 0.5, 0, ktype=cv2.CV_32F)
                    fimg = cv2.filter2D(gray, cv2.CV_8UC3, kernel)
                    features.append(round(fimg.mean(), 3))
                    features.append(round(fimg.var(), 3))
        return np.array(features)

    gabor_features = extract_gabor_features(image_rgb)
    print("Gabor Features (mean & variance per filter, length={}): \n".format(len(gabor_features)), gabor_features, "\n")

    # decompose image into different frequency bands using discrete wavelet transform with haar wavlet
    def extract_wavelet_features(image, wavelet="haar"):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        coeffs2 = pywt.dwt2(gray, wavelet)
        LL, (LH, HL, HH) = coeffs2
        
        # mean and variance of each band
        features = [
            LL.mean(), LL.var(),
            LH.mean(), LH.var(),
            HL.mean(), HL.var(),
            HH.mean(), HH.var()
        ]
        return np.array(features)
    wavelet_features = extract_wavelet_features(image_rgb, wavelet="haar")
    print("Wavelet Features (mean & variance for LL, LH, HL, HH): \n", wavelet_features, "\n")

    # value to describe the complexity of a fractal pattern 
    def fractal_dimension(image, threshold=128):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # binarize
        _, bw = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        bw = bw // 255
        
        def boxcount(Z, k):
            S = np.add.reduceat(
                np.add.reduceat(Z, np.arange(0, Z.shape[0], k), axis=0),
                                np.arange(0, Z.shape[1], k), axis=1)
            return len(np.where((S > 0) & (S < k*k))[0])

        # sizes of boxes
        p = min(bw.shape)
        n = 2**np.floor(np.log(p)/np.log(2))
        n = int(n)
        sizes = 2**np.arange(int(np.log(n)/np.log(2)), 1, -1)

        counts = []
        for size in sizes:
            counts.append(boxcount(bw, size))

        # fit log-log
        coeffs = np.polyfit(np.log(sizes), np.log(counts), 1)
        return -coeffs[0]  

    fd = fractal_dimension(image_rgb)
    print("Fractal Dimension:", fd, "\n")

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

# TO-RUN: python app,py
if __name__ == "__main__":
    app.run(debug=True)