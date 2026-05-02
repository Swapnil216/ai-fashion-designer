#To run, use streamlit run app.py
import streamlit as st
import os
from core.stylist import generate_outfit
from core.database import get_connection, retire_item, update_item
from core.database import upgrade_db_schema, log_outfit_as_worn

# Set layout to wide to accommodate the catalog grid
st.set_page_config(page_title="AI Fashion Designer", page_icon="👔", layout="wide")

st.title("👔 Local AI Stylist")
# Define the two main views
tab_stylist, tab_closet = st.tabs(["✨ Style Me", "🚪 My Closet"])

@st.cache_resource
def run_once_on_startup():
    upgrade_db_schema()
    return True

run_once_on_startup()
# ==========================================
# TAB 1: THE STYLIST ENGINE
# ==========================================
with tab_stylist:
    if "current_outfit" not in st.session_state:
        st.session_state.current_outfit = None

    user_prompt = st.text_input(
        "Where are you going?",
        placeholder="e.g., Going to the office for a code review, then drinks after 6 PM."
    )


    def fetch_new_outfit():
        with st.spinner("Consulting local AI..."):
            st.session_state.current_outfit = generate_outfit(user_prompt)


    if st.button("Generate Outfit") and user_prompt:
        fetch_new_outfit()

    if st.session_state.current_outfit:
        result = st.session_state.current_outfit

        if "error" in result:
            st.error(result["error"])
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.success(f"📍 **Occasion:** {result['intent'].get('occasion')} in {result['intent'].get('city')}")
            with col2:
                st.info(f"⛅ **Weather:** {result['weather']['desc']}")

            st.write("---")
            st.write(f"### 💡 Stylist Notes:\n{result['reasoning']}")

            st.write("### ✨ Your Outfit")

            # --- THE TRUE-CATEGORY OVERRIDE ---
            if "outfit" in result:
                raw_ids = []
                for _, item_data in result["outfit"].items():
                    if not item_data or str(item_data).lower() in ["null", "none", "item_id_or_null"]:
                        continue
                    if isinstance(item_data, list):
                        raw_ids.extend(item_data)
                    else:
                        raw_ids.append(item_data)

                clean_ids = [str(i).strip() for i in raw_ids if str(i).strip()]

                if clean_ids:
                    conn = get_connection()
                    cursor = conn.cursor()

                    unique_ids = list(set(clean_ids))
                    placeholders = ','.join(['?'] * len(unique_ids))

                    cursor.execute(
                        f"SELECT category, sub_category, color_hex, image_path FROM wardrobe WHERE item_id IN ({placeholders})",
                        tuple(unique_ids))
                    true_items = cursor.fetchall()
                    conn.close()

                    display_groups = {}
                    for row in true_items:
                        cat_name = row['category'].title()
                        if cat_name not in display_groups:
                            display_groups[cat_name] = []
                        display_groups[cat_name].append(row)

                    display_order = ["Upper", "Lower", "Shoes", "Accessory"]

                    for target_cat in display_order:
                        if target_cat in display_groups:
                            st.subheader(target_cat)
                            items = display_groups[target_cat]

                            cols = st.columns(max(len(items), 4))
                            for idx, row in enumerate(items):
                                img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), row['image_path'])
                                with cols[idx]:
                                    if os.path.exists(img_path):
                                        clean_name = str(row['sub_category']).replace('_', ' ').title()
                                        st.image(img_path, caption=clean_name, width="stretch")
                                    else:
                                        st.warning("Image missing")

                    # --- MEMORY LOGGING & REROLL BUTTONS ---
                    st.write("---")
                    col_a, col_b = st.columns(2)

                    with col_a:
                        if st.button("👗 I'm wearing this! (Log to Memory)", type="primary", use_container_width=True):
                            log_outfit_as_worn(clean_ids)
                            st.success("Logged! These items will take a break before being recommended again.")
                            st.balloons()

                    with col_b:
                        # Replaces the duplicate "try another" buttons with one clean column button
                        if st.button("🎲 Not my vibe, try another", use_container_width=True):
                            fetch_new_outfit()
                            st.rerun()

# ==========================================
# TAB 2: THE WARDROBE CATALOG
# ==========================================
with tab_closet:
    st.header("Your Digital Wardrobe")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wardrobe WHERE is_active = 1 ORDER BY category")
    all_items = cursor.fetchall()
    conn.close()

    if not all_items:
        st.info("Your closet is empty! Drop some photos into `data/raw_uploads/` and run `python core/ingestion.py`.")
    else:
        # --- BATCH EDIT MODE TOGGLE ---
        batch_edit = st.toggle("✏️ Enable Visual Batch Edit Mode")
        st.write("---")

        if batch_edit:
            st.info("Change the tags directly under the images. Click 'Save All Changes' at the bottom when finished.")

            # Wrap the entire editing grid in one massive form
            with st.form(key="master_batch_edit_form"):
                # We use slightly wider columns (4 instead of 6) so the dropdowns fit nicely
                cols = st.columns(4)

                for idx, item in enumerate(all_items):
                    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), item['image_path'])

                    with cols[idx % 4]:
                        # Show the image
                        if os.path.exists(img_path):
                            st.image(img_path, width="stretch")
                        else:
                            st.warning("Missing file")

                        # The Inputs (We tie them to the item_id so we can read them later)
                        st.selectbox(
                            "Category",
                            ['upper', 'lower', 'shoes', 'accessory'],
                            index=['upper', 'lower', 'shoes', 'accessory'].index(item['category']),
                            key=f"cat_{item['item_id']}"
                        )
                        st.text_input("Sub-category", value=item['sub_category'], key=f"sub_{item['item_id']}")
                        st.text_input("Color Hex", value=item['color_hex'] or "", key=f"col_{item['item_id']}")

                        current_formality = item['formality_score'] if item['formality_score'] is not None else 5
                        st.slider("Formality", 1, 10, value=int(current_formality), key=f"form_{item['item_id']}")

                        current_weather = item['weather_suitability'] if item['weather_suitability'] else 'all'
                        st.selectbox(
                            "Weather",
                            ['hot', 'cold', 'all'],
                            index=['hot', 'cold', 'all'].index(current_weather),
                            key=f"wea_{item['item_id']}"
                        )
                        st.write("---")  # Visual divider between rows

                # The Master Submit Button
                if st.form_submit_button("💾 Save All Changes to Database", type="primary", use_container_width=True):
                    # When clicked, loop through all items and read the new values from session state
                    for item in all_items:
                        iid = item['item_id']
                        update_item(
                            item_id=iid,
                            category=st.session_state[f"cat_{iid}"],
                            sub_category=st.session_state[f"sub_{iid}"],
                            color_hex=st.session_state[f"col_{iid}"],
                            formality_score=st.session_state[f"form_{iid}"],
                            weather_suitability=st.session_state[f"wea_{iid}"]
                        )
                    st.toast("✨ Database updated successfully!", icon="✅")
                    st.rerun()

        else:
            # --- THE STANDARD VISUAL GRID (View Only) ---
            catalog = {}
            for item in all_items:
                cat = item['category'].title()
                if cat not in catalog:
                    catalog[cat] = []
                catalog[cat].append(item)

            global_btn_counter = 0

            for cat_name, items in catalog.items():
                st.write(f"### {cat_name}")

                cols = st.columns(6)
                for idx, item in enumerate(items):
                    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), item['image_path'])
                    with cols[idx % 6]:
                        if os.path.exists(img_path):
                            st.image(img_path, caption=item['sub_category'].title(), width="stretch")

                            global_btn_counter += 1
                            btn_col1, btn_col2 = st.columns(2)

                            with btn_col1:
                                if st.button("🔄 Reingest", key=f"reingest_{item['item_id']}_{global_btn_counter}"):
                                    with st.spinner("Analyzing original..."):
                                        from core.ingestion import reingest_item

                                        success, msg = reingest_item(item['item_id'])
                                        if success:
                                            st.toast("✨ Healed image!", icon="✅")
                                            st.rerun()
                                        else:
                                            st.error(msg)
                            with btn_col2:
                                if st.button("🗑️ Trash", key=f"discard_{item['item_id']}_{global_btn_counter}"):
                                    retire_item(item['item_id'])
                                    st.rerun()
                        else:
                            st.error("Missing file")
                st.write("---")