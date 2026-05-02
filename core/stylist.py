import json
import difflib
from datetime import datetime, timedelta
import ollama

from core.database import get_active_wardrobe, load_config
from core.weather import get_event_weather

CONFIG = load_config()
LOCAL_MODEL = 'llama3.1'


def parse_user_intent(user_prompt):
    now = datetime.now()
    default_end = now + timedelta(hours=2)
    default_city = CONFIG['user']['location'].get('default_city', 'Berlin')

    prompt = f"""
    Current Date/Time: {now.strftime("%Y-%m-%d %H:%M")}
    Default City: {default_city}

    Analyze this user request: "{user_prompt}"

    Extract the following into a raw JSON object:
    - "occasion": What are they doing?
    - "occasion_type": Classify this strictly as either "work" or "personal".
    - "city": The highly specific location mentioned. If none, use Default City.
    - "start_time": Estimated start time (ISO format string). If not mentioned, use Current Date/Time.
    - "end_time": Estimated end time (ISO format string). If not mentioned, use Current Date/Time + 2 hours.
    """

    try:
        response = ollama.chat(model=LOCAL_MODEL, messages=[{'role': 'user', 'content': prompt}], format='json')
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"Failed to parse intent: {e}")
        return {
            "occasion": user_prompt, "occasion_type": "personal", "city": default_city,
            "start_time": now.isoformat(), "end_time": default_end.isoformat()
        }


def find_best_match(target_category, ideal_desc, target_formality, active_wardrobe):
    """Pass 3: Semantic matching with Category-Aware Wear Fatigue."""
    candidates = [item for item in active_wardrobe if item['category'] == target_category]
    if not candidates:
        return None

    best_item = None
    best_score = -100

    for item in candidates:
        item_str = f"{item['color_hex'] or ''} {item['sub_category']}".lower().replace('_', ' ')

        #Text Similarity (0.0 to 1.0)
        text_score = difflib.SequenceMatcher(None, ideal_desc.lower(), item_str).ratio()

        #Formality Penalty (0.0 to 1.0)
        item_form = item['formality_score'] if item['formality_score'] is not None else 5
        form_penalty = abs(item_form - target_formality) / 10.0

        #CATEGORY-AWARE WEAR FATIGUE
        wear_penalty = 0.0
        if 'last_worn' in item.keys() and item['last_worn']:
            last_worn_date = datetime.strptime(item['last_worn'], "%Y-%m-%d")
            days_since_worn = (datetime.now() - last_worn_date).days

            # Apply different rules based on the type of clothing
            if target_category == 'upper':
                # Shirts/Tops: Strict 7-day cooldown. Highly penalized if worn recently.
                if days_since_worn < 7:
                    wear_penalty = (7 - days_since_worn) / 7.0

            elif target_category == 'lower':
                # Pants/Jeans: Relaxed 3-day cooldown. Penalty is cut in half.
                if days_since_worn < 3:
                    wear_penalty = ((3 - days_since_worn) / 3.0) * 0.5

            else:
                # Accessories, Shoes, Outerwear: Almost zero penalty.
                # (We add a tiny 0.1 penalty just to prevent wearing it 2 days in a row if there is a perfect alternative, otherwise it gets ignored).
                if days_since_worn < 2:
                    wear_penalty = 0.1

                    #Tie-Breaker Noise
        shuffle_noise = random.uniform(0.0, 0.05)

        # Final Score
        final_score = text_score - (form_penalty * 0.4) - (wear_penalty * 0.8) + shuffle_noise

        if final_score > best_score:
            best_score = final_score
            best_item = item['item_id']

    return best_item


def generate_outfit(user_prompt):
    intent = parse_user_intent(user_prompt)
    print(f"Extracted Intent: {intent.get('occasion')} in {intent.get('city')} (Type: {intent.get('occasion_type')})")

    weather_data = get_event_weather(intent.get('city', 'Berlin'), intent.get('start_time'), intent.get('end_time'))

    weather_filter = 'hot' if weather_data['max_temp'] > 25 else 'cold' if weather_data['min_temp'] < 15 else None
    wardrobe_items = get_active_wardrobe(weather_filter)

    if len(wardrobe_items) == 0:
        return {"error": "Your digital wardrobe is empty or has no suitable items for this weather!", "intent": intent,
                "weather": weather_data}

    is_work = intent.get('occasion_type') == 'work'
    active_style = CONFIG['user']['style_rules']['work'] if is_work else CONFIG['user']['style_rules']['default']
    stylist_country = CONFIG['user'].get('stylist_country', 'global')

    prompt = f"""
    You are a high-end {stylist_country} personal stylist. 
    The user needs an outfit for: "{intent.get('occasion')}" in {intent.get('city')}.

    Context:
    - Weather Window: {weather_data['desc']}
    - Target Aesthetic: {active_style}.

    Design the absolute PERFECT outfit for this occasion.

    CRITICAL RULES:
    1. You MUST include "Upper Wear", "Lower Wear", and "Shoes".
    2. "Outerwear" and "Accessories" are optional (use null if not needed).

    Return ONLY a JSON object exactly matching this structure:
    {{
      "reasoning": "A 2-3 sentence explanation of the look.",
      "ideal_outfit": {{
        "Upper Wear": {{"description": "e.g., light blue cotton button-down shirt", "formality": 6}},
        "Lower Wear": {{"description": "e.g., dark wash denim jeans", "formality": 4}},
        "Outerwear": null,
        "Shoes": {{"description": "e.g., white leather sneakers", "formality": 3}},
        "Accessories": {{"description": "e.g., silver watch", "formality": 5}}
      }}
    }}
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Consulting local AI Stylist (Attempt {attempt + 1}/{max_retries})...")
            response = ollama.chat(
                model=LOCAL_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                format='json',
                options={'temperature': 0.8}
            )

            result = json.loads(response['message']['content'])
            ideal_outfit = result.get('ideal_outfit', {})

            if not ideal_outfit.get('Upper Wear') or not ideal_outfit.get('Lower Wear') or not ideal_outfit.get(
                    'Shoes'):
                print("⚠️ AI skipped a core category. Retrying...")
                continue

            # THE SEMANTIC MATCHING PIPELINE
            print("Matching AI's dream outfit to your actual wardrobe...")
            final_outfit = {}

            category_mapping = {
                'Upper Wear': 'upper',
                'Lower Wear': 'lower',
                'Outerwear': 'upper',
                'Shoes': 'shoes',
                'Accessories': 'accessory'
            }

            for key, db_cat in category_mapping.items():
                target = ideal_outfit.get(key)
                if target and isinstance(target, dict):
                    match_id = find_best_match(db_cat, target.get('description', ''), target.get('formality', 5),
                                               wardrobe_items)
                    if match_id:
                        final_outfit[key] = match_id

            result['outfit'] = final_outfit
            result['intent'] = intent
            result['weather'] = weather_data
            return result

        except Exception as e:
            print(f"⚠️ Error on attempt {attempt + 1}: {e}")

    return {"error": "The stylist failed to generate an outfit."}