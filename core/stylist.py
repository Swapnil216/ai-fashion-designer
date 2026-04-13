# import json
# from datetime import datetime, timedelta
# import ollama
#
# from core.database import get_active_wardrobe, load_config
# from core.weather import get_event_weather
#
# CONFIG = load_config()
#
# LOCAL_MODEL = 'llama3.1'
#
#
# def parse_user_intent(user_prompt):
#     now = datetime.now()
#     default_end = now + timedelta(hours=2)
#     default_city = CONFIG['user']['location']['default_city']
#
#     prompt = f"""
#         Current Date/Time: {now.strftime("%Y-%m-%d %H:%M")}
#         Default City: {default_city}
#
#         Analyze this user request: "{user_prompt}"
#
#         Extract the following into a raw JSON object:
#         - "occasion": What are they doing? (e.g., "Software engineer code review", "Dinner")
#         - "occasion_type": Classify this strictly as either "work" or "personal".
#         - "city": The highly specific location mentioned, including street, neighborhood, or building (e.g., "Lehrter Str, Berlin"). If none mentioned, use Default City.
#         - "start_time": Estimated start time (ISO format string). If not mentioned, use Current Date/Time.
#         - "end_time": Estimated end time (ISO format string). If not mentioned, use Current Date/Time + 2 hours.
#         """
#
#     try:
#         response = ollama.chat(model=LOCAL_MODEL, messages=[
#             {'role': 'user', 'content': prompt}
#         ], format='json')
#
#         return json.loads(response['message']['content'])
#     except Exception as e:
#         print(f"Failed to parse intent: {e}")
#         return {
#             "occasion": user_prompt,
#             "occasion_type": "personal",
#             "city": default_city,
#             "start_time": now.isoformat(),
#             "end_time": default_end.isoformat()
#         }
#
#
# def generate_outfit(user_prompt):
#
#     intent = parse_user_intent(user_prompt)
#     print(f"Extracted Intent: {intent.get('occasion')} in {intent.get('city')} (Type: {intent.get('occasion_type')})")
#
#     weather_data = get_event_weather(intent.get('city', 'Berlin'), intent.get('start_time'), intent.get('end_time'))
#
#     weather_filter = 'hot' if weather_data['max_temp'] > 18 else 'cold' if weather_data['min_temp'] < 10 else None
#     wardrobe_items = get_active_wardrobe(weather_filter)
#
#     if len(wardrobe_items) == 0:
#         return {
#             "error": "Your digital wardrobe is empty! 🧥\n\nPlease drop some photos into `data/raw_uploads/`, run `python core/ingestion.py`, and hit 'Refresh' on the page.",
#             "intent": intent,
#             "weather": weather_data
#         }
#
#     wardrobe_json = json.dumps([{
#         "id": item['item_id'], "category": item['category'], "sub_category": item['sub_category'],
#         "color": item['color_hex'], "formality": item['formality_score']
#     } for item in wardrobe_items], indent=2)
#
#     is_work = intent.get('occasion_type') == 'work'
#     active_style = CONFIG['user']['style_rules']['work'] if is_work else CONFIG['user']['style_rules']['default']
#
#     prompt = f"""
#         You are a high-end {CONFIG['user'].get('stylist_country', 'global')} personal stylist.
#         The user needs an outfit for: "{intent.get('occasion')}" in {intent.get('city')}.
#
#         Context:
#         - Weather Window: {weather_data['desc']} (Max: {weather_data['max_temp']}°C, Min: {weather_data['min_temp']}°C)
#         - Skin Tone Hex: {CONFIG['user']['skin_tone_hex']}
#         - Target Aesthetic: {active_style}.
#
#         Available wardrobe:
#         {wardrobe_json}
#
#         Select the best combination.
#
#         CRITICAL RULES:
#         1. The outfit MUST contain exactly one "upper", one "lower", and one "shoes". This is non-negotiable.
#         2. You may optionally add an "accessory" or an "outerwear" (layer) if the weather or occasion demands it.
#         3. Match the IDs precisely from the provided wardrobe list.
#
#         Return ONLY a JSON object exactly matching this structure (use null for Outerwear or Accessories if skipping):
#         {{
#           "outfit": {{
#             "Upper Wear": "item_id",
#             "Lower Wear": "item_id",
#             "Outerwear": "item_id_or_null",
#             "Shoes": "item_id",
#             "Accessories": "item_id_or_null"
#           }},
#           "reasoning": "A 2-3 sentence explanation of why this outfit works based strictly on the items chosen above."
#         }}
#         """
#
#
#     try:
#         # print("Consulting local Ollama stylist...")
#         # response = ollama.chat(
#         #     model=LOCAL_MODEL,
#         #     messages=[{'role': 'user', 'content': prompt}],
#         #     format='json',
#         #     options={'temperature': 0.9}
#         # )
#         #
#         # result = json.loads(response['message']['content'])
#         # result['intent'] = intent
#         # result['weather'] = weather_data
#         # return result
#         max_retries = 3
#
#         for attempt in range(max_retries):
#             try:
#                 print(f"🧠 Consulting local Ollama stylist (Attempt {attempt + 1}/{max_retries})...")
#                 response = ollama.chat(
#                     model=LOCAL_MODEL,
#                     messages=[{'role': 'user', 'content': prompt}],
#                     format='json',
#                     options={'temperature': 0.5}
#                 )
#
#                 result = json.loads(response['message']['content'])
#
#                 outfit = result.get('outfit', {})
#                 has_upper = bool(outfit.get('Upper Wear'))
#                 has_lower = bool(outfit.get('Lower Wear'))
#                 has_shoes = bool(outfit.get('Shoes'))
#
#                 if has_upper and has_lower and has_shoes:
#                     result['intent'] = intent
#                     result['weather'] = weather_data
#                     return result
#                 else:
#                     print("⚠️ AI forgot a core item (Upper, Lower, or Shoes). Forcing a retry...")
#
#             except Exception as e:
#                 print(f"Error parsing AI response: {e}")
#
#         return {
#             "error": "The stylist is having trouble putting together a complete outfit right now. Please try clicking 'Generate' again!"}
#
#     except Exception as e:
#         return {"error": f"Local AI failed to generate outfit: {e}"}


import json
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
    - "occasion": What are they doing? (e.g., "Software engineer code review", "Dinner")
    - "occasion_type": Classify this strictly as either "work" or "personal".
    - "city": The highly specific location mentioned, including street, neighborhood, or building (e.g., "Invalidenstr, Berlin"). If none mentioned, use Default City.
    - "start_time": Estimated start time (ISO format string). If not mentioned, use Current Date/Time.
    - "end_time": Estimated end time (ISO format string). If not mentioned, use Current Date/Time + 2 hours.
    """

    try:
        response = ollama.chat(model=LOCAL_MODEL, messages=[
            {'role': 'user', 'content': prompt}
        ], format='json')

        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"Failed to parse intent: {e}")
        return {
            "occasion": user_prompt,
            "occasion_type": "personal",
            "city": default_city,
            "start_time": now.isoformat(),
            "end_time": default_end.isoformat()
        }


def generate_outfit(user_prompt):
    intent = parse_user_intent(user_prompt)
    print(f"🎯 Extracted Intent: {intent.get('occasion')} in {intent.get('city')} (Type: {intent.get('occasion_type')})")

    weather_data = get_event_weather(intent.get('city', 'Berlin'), intent.get('start_time'), intent.get('end_time'))

    weather_filter = 'hot' if weather_data['max_temp'] > 18 else 'cold' if weather_data['min_temp'] < 10 else None
    wardrobe_items = get_active_wardrobe(weather_filter)

    if len(wardrobe_items) == 0:
        return {
            "error": "Your digital wardrobe is empty or has no suitable items for this weather! 🧥\n\nPlease drop some photos into `data/raw_uploads/`, run `python core/ingestion.py`, and hit 'Refresh' on the page.",
            "intent": intent,
            "weather": weather_data
        }

    wardrobe_json = json.dumps([{
        "id": item['item_id'], "category": item['category'], "sub_category": item['sub_category'],
        "color": item['color_hex'], "formality": item['formality_score']
    } for item in wardrobe_items], indent=2)

    is_work = intent.get('occasion_type') == 'work'
    active_style = CONFIG['user']['style_rules']['work'] if is_work else CONFIG['user']['style_rules']['default']
    stylist_country = CONFIG['user'].get('stylist_country', 'global')

    prompt = f"""
    You are a high-end {stylist_country} personal stylist. 
    The user needs an outfit for: "{intent.get('occasion')}" in {intent.get('city')}.

    Context:
    - Weather Window: {weather_data['desc']} (Max: {weather_data['max_temp']}°C, Min: {weather_data['min_temp']}°C)
    - Skin Tone Hex: {CONFIG['user']['skin_tone_hex']}
    - Target Aesthetic: {active_style}.

    Available wardrobe:
    {wardrobe_json}

    Select the best combination. 

    CRITICAL RULES:
    1. The outfit MUST contain exactly one "upper", one "lower", and one "shoes". This is non-negotiable.
    2. You may optionally add an "accessory" or an "outerwear" (layer) if the weather or occasion demands it.
    3. Match the IDs precisely from the provided wardrobe list.

    Return ONLY a JSON object exactly matching this structure (use null for Outerwear or Accessories if skipping):
    {{
      "outfit": {{
        "Upper Wear": "item_id",
        "Lower Wear": "item_id",
        "Outerwear": "item_id_or_null",
        "Shoes": "item_id",
        "Accessories": "item_id_or_null"
      }},
      "reasoning": "A 2-3 sentence explanation of why this outfit works based strictly on the items chosen above."
    }}
    """

    max_retries = 3

    valid_uppers = [str(item['item_id']) for item in wardrobe_items if item['category'] == 'upper']
    valid_lowers = [str(item['item_id']) for item in wardrobe_items if item['category'] == 'lower']
    valid_shoes = [str(item['item_id']) for item in wardrobe_items if item['category'] == 'shoes']

    if not valid_uppers or not valid_lowers or not valid_shoes:
        return {
            "error": "Your wardrobe is missing core items! You need at least one Upper, one Lower, and one pair of Shoes saved in your closet before I can style you."}

    for attempt in range(max_retries):
        try:
            print(f"🧠 Consulting local Ollama stylist (Attempt {attempt + 1}/{max_retries})...")
            response = ollama.chat(
                model=LOCAL_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                format='json',
                options={'temperature': 0.8}
            )

            result = json.loads(response['message']['content'])

            outfit = result.get('outfit', {})

            has_upper = str(outfit.get('Upper Wear')) in valid_uppers
            has_lower = str(outfit.get('Lower Wear')) in valid_lowers
            has_shoes = str(outfit.get('Shoes')) in valid_shoes

            if has_upper and has_lower and has_shoes:
                result['intent'] = intent
                result['weather'] = weather_data
                return result
            else:
                print("AI hallucinated a fake ID or used the wrong category! Forcing a retry...")

        except Exception as e:
            print(f"Error parsing AI response on attempt {attempt + 1}: {e}")

    return {
        "error": "The stylist is having trouble putting together a complete outfit right now. Please try clicking 'Generate Outfit' again!"}
