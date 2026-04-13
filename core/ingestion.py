import os
import shutil
import json
import io
import ollama
from PIL import Image
from pillow_heif import register_heif_opener
from rembg import remove
from core.database import add_item

register_heif_opener()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data/raw_uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "data/processed_items")
ARCHIVE_DIR = os.path.join(BASE_DIR, "data/archive")

# Local hosted model
VISION_MODEL = 'llama3.2-vision'


def extract_metadata(img):
    prompt = """
    Analyze this clothing item. Ignore any background objects (like a coffee coaster, it is only for reference to size to understand loose fit, tight fit, etc.).
    Return ONLY a raw JSON object with the following keys exactly as written, no markdown:
    - "category": Must be strictly one of ['upper', 'lower', 'shoes', 'accessory']
    - "sub_category": A short 1-2 word description (e.g., 't-shirt', 'chinos', 'watch_strap')
    - "color_hex": Estimate the dominant hex color code (e.g., '#000000', '#1A2B3C')
    - "formality_score": An integer from 1 (gym wear) to 10 (tuxedo)
    - "weather_suitability": Must be strictly one of ['hot', 'cold', 'all']
    """

    # Convert PIL image to JPEG bytes so Ollama can read it easily
    buffered = io.BytesIO()
    img.convert('RGB').save(buffered, format="JPEG")
    img_bytes = buffered.getvalue()

    try:
        response = ollama.chat(
            model=VISION_MODEL,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [img_bytes]
            }],
            format='json'
        )

        clean_text = response['message']['content'].strip()
        return json.loads(clean_text)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON from Ollama. Raw output: {response['message']['content']}")
        return None
    except Exception as e:
        print(f"Local AI Error: {e}")
        return None


def process_image(filename):
    raw_path = os.path.join(RAW_DIR, filename)
    print(f"\nProcessing the raw image - {filename}...")

    try:
        img = Image.open(raw_path)
        img.load()
    except Exception as e:
        print(f"Could not open image {filename}: {e}")
        return

    metadata = extract_metadata(img)
    if not metadata:
        return

    print(f"Identified the photo as: {metadata['sub_category']} (Category: {metadata['category']})")

    print("Removing background to isolate item...")
    img_byte_arr = io.BytesIO()
    img.convert('RGB').save(img_byte_arr, format='PNG')
    input_data = img_byte_arr.getvalue()

    output_data = remove(input_data)

    clean_filename = f"{os.path.splitext(filename)[0]}_clean.png"
    processed_path = os.path.join(PROCESSED_DIR, clean_filename)

    with open(processed_path, 'wb') as o:
        o.write(output_data)

    print("Pushing to DB...")
    relative_processed_path = f"data/processed_items/{clean_filename}"

    item_id = add_item(
        category=metadata['category'],
        sub_category=metadata['sub_category'],
        color_hex=metadata['color_hex'],
        formality_score=metadata['formality_score'],
        weather_suitability=metadata['weather_suitability'],
        image_path=relative_processed_path
    )

    archive_path = os.path.join(ARCHIVE_DIR, filename)
    shutil.move(raw_path, archive_path)
    print(f"Success! Item stored with ID: {item_id[:8]}")


def run_pipeline():
    if not os.path.exists(RAW_DIR) or not os.listdir(RAW_DIR):
        print("No new images found in data/raw_uploads/. Drop some photos in there!")
        return

    for filename in os.listdir(RAW_DIR):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif')):
            process_image(filename)


def reingest_item(item_id):
    """Finds the original image in the archive, re-crops, extracts new metadata, and updates DB."""
    from core.database import get_connection, update_item  # Local import to avoid pathing issues

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM wardrobe WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, "Item not found in database."

    # e.g., "data/processed_items/IMG_1899_clean.png" -> "IMG_1899"
    processed_path = row['image_path']
    base_name = os.path.basename(processed_path).replace("_clean.png", "")

    archive_file = None
    if os.path.exists(ARCHIVE_DIR):
        for f in os.listdir(ARCHIVE_DIR):
            if os.path.splitext(f)[0] == base_name:
                archive_file = os.path.join(ARCHIVE_DIR, f)
                break

    if not archive_file:
        return False, f"Original image for {base_name} not found in archive."

    print(f"\nReindexing {archive_file}...")

    try:
        img = Image.open(archive_file)
        img.load()
    except Exception as e:
        return False, f"Could not open archived image: {e}"

    metadata = extract_metadata(img)
    if not metadata or metadata.get('category') == 'REJECT':
        return False, "AI rejected the image (Detected only a coaster or invalid item)."

    print("Re-cropping image...")
    img_byte_arr = io.BytesIO()
    img.convert('RGB').save(img_byte_arr, format='PNG')
    output_data = remove(img_byte_arr.getvalue())

    full_processed_path = os.path.join(BASE_DIR, processed_path)
    with open(full_processed_path, 'wb') as o:
        o.write(output_data)

    update_item(
        item_id,
        metadata['category'],
        metadata['sub_category'],
        metadata['color_hex'],
        metadata['formality_score'],
        metadata['weather_suitability']
    )
    return True, "Successfully reingested!"


if __name__ == "__main__":
    print("Starting Local Ingestion Pipeline...")
    run_pipeline()
    print("\nPipeline finished.")