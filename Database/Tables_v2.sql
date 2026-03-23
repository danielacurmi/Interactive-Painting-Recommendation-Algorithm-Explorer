CREATE TABLE artists (
    artist_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name_surname TEXT NOT NULL,
    birth_year INT,
    death_year INT,
    nationality TEXT,
	fields TEXT,
	art_movements TEXT,
    bio TEXT
);

CREATE TABLE paintings (
    painting_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,    
    artist_id INT REFERENCES artists(artist_id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    year_created INT CHECK (year_created > 0) NOT NULL,
    genre VARCHAR(100) NOT NULL,
	art_style TEXT NOT NULL,
	media TEXT,
    description_tags TEXT,
    image_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
     user_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
     created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
     consent_form BOOLEAN DEFAULT FALSE,
     ip_address ip_address INET
);

CREATE TABLE sessions (
    session_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    session_start TIMESTAMPTZ NOT NULL,
    session_end TIMESTAMPTZ
);

CREATE TYPE event_type_enum AS ENUM (
    'view_start',
    'view_end',
    'rating',
    'favourite',
    'not_interested',
    'save_to_gallary',
    'review'
);

CREATE TABLE interaction_events (
    event_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id INT REFERENCES sessions(session_id) ON DELETE CASCADE,
    painting_id INT REFERENCES paintings(painting_id) ON DELETE CASCADE,
    event_type event_type_enum NOT NULL,
    event_value TEXT,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE TABLE interaction_summary (
    interaction_id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id INT REFERENCES sessions(session_id) ON DELETE CASCADE,
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE,
    painting_id INT REFERENCES paintings(painting_id) ON DELETE CASCADE,
    viewing_time_seconds INT,
    rating INT CHECK (rating BETWEEN 1 AND 5),
    favourite BOOLEAN DEFAULT FALSE,
    not_interested BOOLEAN DEFAULT FALSE,
    save_to_gallary BOOLEAN DEFAULT FALSE,
    review TEXT
);

