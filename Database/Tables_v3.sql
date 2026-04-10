CREATE TABLE painting_colour_features (
    painting_id INT PRIMARY KEY REFERENCES paintings(painting_id) ON DELETE CASCADE,
    colour_histogram VECTOR(128),
    colour_moments VECTOR(9),
    palette VECTOR(10)
);

CREATE TABLE painting_texture_features (
    painting_id INT PRIMARY KEY REFERENCES paintings(painting_id) ON DELETE CASCADE,
    lbp VECTOR(256),
    gabor VECTOR(64),
    wavelets VECTOR(64),
    fractal_dimension VECTOR(1)
);

CREATE TABLE painting_local_features (
    painting_id INT PRIMARY KEY REFERENCES paintings(painting_id) ON DELETE CASCADE,
    orb_vector VECTOR(256),
    stroke_segmentation VECTOR(128),
    brushstroke_descriptors VECTOR(128)
);

CREATE TABLE painting_cnn_embeddings (
    painting_id INT PRIMARY KEY REFERENCES paintings(painting_id) ON DELETE CASCADE,
    resnet50_embedding VECTOR(2048),
    vgg19_embedding VECTOR(4096)
);