import torch    
from torchvision import transforms
from PIL import Image
import torch.optim as optim
import torchvision.models as models
from torchvision.models import VGG19_Weights

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(device)

normalization_mean = [0.485, 0.456, 0.406]
normalization_std = [0.229, 0.224, 0.225]
normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225])

transform = transforms.Compose([
    transforms.Resize(512),              # Resize shorter side to 256
    transforms.CenterCrop(512),          # Then crop the center 224×224
    transforms.ToTensor(),
    normalize
])

def load_image(image_path):
    image = Image.open(image_path).convert('RGB')
    image = transform(image).unsqueeze(0)  # Add batch dimension
    return image.to(device)  # move to GPU if available

vgg = models.vgg19(weights=VGG19_Weights.DEFAULT).features.to(device).eval()
for param in vgg.parameters():
    param.requires_grad = False

content_layers = ['conv_4']
style_layers = ['conv_1', 'conv_2', 'conv_3', 'conv_4', 'conv_5']

content_layer = '21'  # 'conv4_2' corresponds to layer 21 in vgg19.features

def get_content_feature(image):
    x = image
    for i, layer in enumerate(vgg):
        x = layer(x)
        if str(i) == content_layer:
            return x
        
content_img = load_image(r'Testing scripts\feature_extraction_recysys_models_db\ref_photos\gatys_example.png')
content_features = get_content_feature(content_img)

def content_loss(gen_features, content_features):
    return torch.nn.functional.mse_loss(gen_features, content_features)

style_layers = ['0', '5', '10', '19', '28']

def get_style_features(image, model, layers):
    features = []
    x = image
    for i, layer in enumerate(model):
        x = layer(x)
        if str(i) in layers:
            features.append(x)
    return features

style_img = load_image(r'Testing scripts\feature_extraction_recysys_models_db\ref_paintings\Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg')
style_features = get_style_features(style_img, vgg, style_layers)

# generated_img = torch.randn((1, 3, 512, 512), device=device, requires_grad=True)
generated_img = content_img.clone().requires_grad_(True).to(device)

def gram_matrix(tensor):
    # tensor shape: (batch_size=1, channels, height, width)
    b, c, h, w = tensor.size()
    features = tensor.view(c, h * w)      # reshape to (channels, height*width)
    G = torch.mm(features, features.t())  # compute Gram matrix (channels x channels)
    return G / (2 * c * h * w)  

def style_loss(generated_features, style_features):
    loss = 0
    for gen_feat, style_feat in zip(generated_features, style_features):
        G_gen = gram_matrix(gen_feat)
        G_style = gram_matrix(style_feat)
        loss += torch.nn.functional.mse_loss(G_gen, G_style)
    return loss

loss_history = {"total": [], "content": [], "style": []}

def closure():
    optimizer.zero_grad()

    # Extract generated image features for style and content
    gen_content_feat = get_content_feature(generated_img)
    gen_style_feats = get_style_features(generated_img, vgg, style_layers)

    # Content loss
    c_loss = content_loss(gen_content_feat, content_features)

    # Style loss
    s_loss = style_loss(gen_style_feats, style_features)

    # Total loss (you can weight them)
    total_loss = c_loss + 1e9*s_loss  # usually style loss weighted heavily

    total_loss.backward()
    
    # Track losses
    loss_history["total"].append(total_loss.item())
    loss_history["content"].append(c_loss.item())
    loss_history["style"].append(s_loss.item())
    
    return total_loss

optimizer = optim.LBFGS([generated_img])

for step in range(300):
    optimizer.step(closure)
    print(f"Step {step}, Total Loss: {loss_history['total'][-1]:.4f}, Content Loss: {loss_history['content'][-1]:.4f}, Style Loss: {loss_history['style'][-1]:.4f}")


def save_image(tensor, path):
    # Clone the tensor to avoid modifying original
    image = tensor.clone().detach().cpu().squeeze(0)  # Remove batch dim
    image = image * torch.tensor([0.229, 0.224, 0.225]).view(3,1,1)
    image = image + torch.tensor([0.485, 0.456, 0.406]).view(3,1,1)
    image = torch.clamp(image, 0, 1)  # Ensure pixels are in [0,1]

    # Convert to PIL and save
    transforms.ToPILImage()(image).save(path)

save_image(generated_img, r"Testing scripts\feature_extraction_recysys_models_db\generated_images\generated_image_van_gogh.jpg")

#It works better if the generated image start with content image and then backprop
#Also rather than increasing the steps of the backprop you can increase the loss related to style, so a higher style_loss with low steps works the best