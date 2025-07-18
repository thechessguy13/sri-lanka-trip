import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from datetime import datetime, date
import urllib.parse
import pydeck as pdk
from streamlit_option_menu import option_menu # <-- ADD THIS IMPORT

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sri Lanka Trip",
    page_icon="🇱🇰",
    layout="wide",
)

# --- STYLING ---
st.markdown("""
<style>
    /* Main containers */
    .st-emotion-cache-18ni7ap, .st-emotion-cache-1d391kg { padding: 1rem 1rem 1rem; }
    /* Card-like containers for widgets */
    div[data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {
        border: 1px solid rgba(255, 255, 255, 0.2); background-color: #1E1E1E;
        border-radius: 10px; padding: 20px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
    }
    /* Custom metric box styling */
    .metric-container {
        background-color: #262730;
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        border: 1px solid #444;
    }
    .metric-label { color: #fafafa; margin: 0; font-size: 1rem; }
    .metric-value { font-size: 2rem; color: #29B5E8; margin: 5px 0; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# --- DATA DEFAULTS & STATIC ASSETS ---
DEFAULT_SHEET_DATA = {
    "Tips": [
        ["Category", "Tip"], ["Money", "Always carry small change."], ["Health", "Drink only bottled water."],
        ["Culture", "Dress modestly for temples."], ["General", "Buy a local SIM card."]
    ],
    "Phrases": [
        ["English", "Sinhala", "Pronunciation"], ["Hello", "Ayubowan", "Aayu-bo-wan"],
        ["Thank you", "Istuti", "Is-thu-thi"], ["How much?", "Kiyadha?", "Kee-yah-dha?"]
    ],
    "Checklist": [
        ["Category", "Item"], ["Documents", "Passport & Visa"], ["Electronics", "Universal Power Adapter"]
    ]
}
LOCATION_COORDINATES = {
    'Sigiriya': [80.7600, 7.9571], 'Trincomalee': [81.2359, 8.5874],
    'Pasikuda': [81.5644, 7.9197], 'Kandy': [80.6350, 7.2906],
    'Nuwara Eliya': [80.7667, 6.9686], 'Colombo': [79.8612, 6.9271]
}
FIXED_CURRENCIES = ["LKR", "INR", "USD"]


# --- BACKEND & API FUNCTIONS ---
@st.cache_resource(ttl=600)
def connect_to_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"GSheets Connection Error: {e}"); return None

@st.cache_data(ttl=600)
def get_or_create_sheet_data(_client, sheet_name):
    try:
        spreadsheet = _client.open_by_url(st.secrets["google_sheets"]["sheet_url"])
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        st.toast(f"'{sheet_name}' sheet not found. Creating it for you...")
        spreadsheet = _client.open_by_url(st.secrets["google_sheets"]["sheet_url"])
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)
        default_data = DEFAULT_SHEET_DATA.get(sheet_name)
        if default_data: worksheet.update('A1', default_data)
        get_or_create_sheet_data.clear()
    except Exception as e:
        st.error(f"Error accessing sheet '{sheet_name}': {e}"); return pd.DataFrame()
    return pd.DataFrame(worksheet.get_all_records())

@st.cache_data(ttl=3600)
def get_exchange_rates(api_key):
    fallback = {"result": "error", "rates": {"LKR": 300, "INR": 83.5, "USD": 1}}
    if not api_key or api_key == "YOUR_EXCHANGERATE_API_KEY_HERE": return fallback
    try:
        data = requests.get(f"https://v6.exchangerate-api.com/v6/{api_key}/latest/USD").json()
        if data.get("result") == "success": return {"result": "success", "rates": data["conversion_rates"]}
        return fallback
    except Exception: return fallback

@st.cache_data(ttl=1800)
def get_weather(city, api_key):
    if not api_key or api_key == "YOUR_OPENWEATHERMAP_API_KEY_HERE": return None
    try:
        return requests.get(f"http://api.openweathermap.org/data/2.5/weather?q={city},LK&appid={api_key}&units=metric").json()
    except Exception: return None

# --- UI HELPER FUNCTIONS ---
def styled_metric(label, value):
    st.markdown(f"""
    <div class="metric-container">
        <p class="metric-label">{label}</p>
        <p class="metric-value">{value}</p>
    </div>
    """, unsafe_allow_html=True)

def create_itinerary_map(df):
    df['coords'] = df['Night Stay'].map(LOCATION_COORDINATES)
    df.dropna(subset=['coords'], inplace=True)
    if df.empty: return None

    path_data = [{'path': df['coords'].tolist(), 'name': 'Trip Route', 'color': [255, 69, 0]}]
    view_state = pdk.ViewState(latitude=df['coords'].iloc[0][1], longitude=df['coords'].iloc[0][0], zoom=6.5, pitch=50)

    layer_points = pdk.Layer(
        'ScatterplotLayer',
        data=df[['Day', 'Night Stay', 'coords']],
        get_position='coords',
        get_color='[200, 30, 0, 160]',
        get_radius=8000,
        pickable=True
    )

    layer_path = pdk.Layer("PathLayer", data=path_data, pickable=True, width_scale=20, width_min_pixels=2, get_path="path", get_color="color", get_width=5)

    return pdk.Deck(map_style=pdk.map_styles.CARTO_DARK, initial_view_state=view_state, layers=[layer_points, layer_path], tooltip={"html": "<b>Day {Day}:</b> {Night Stay}"})

# --- GLOBAL DATA LOADING ---
client = connect_to_gsheets()
if not client: st.stop()

itinerary_df = get_or_create_sheet_data(client, "Itinerary")
phrases_df = get_or_create_sheet_data(client, "Phrases")
tips_df = get_or_create_sheet_data(client, "Tips")
checklist_df = get_or_create_sheet_data(client, "Checklist")
rates_data = get_exchange_rates(st.secrets.get("api_keys", {}).get("exchangerate_api_key"))
rates = rates_data['rates']

# --- MAIN APP LAYOUT (SINGLE-PAGE WITH TABS) ---
st.markdown("<h1 style='text-align: center;'>Sri Lanka 2025</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>One Last Time!</h3>", unsafe_allow_html=True)

# --- REPLACEMENT FOR st.tabs ---
selected_tab = option_menu(
    menu_title=None,
    options=["Dashboard", "Daily Itinerary", "Travel Handbook"],
    icons=["grid-1x2-fill", "calendar-date", "book-half"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "transparent"},
        "icon": {"color": "white", "font-size": "18px"},
        "nav-link": {
            "font-size": "16px",
            "text-align": "center",
            "margin": "0px 5px",
            "--hover-color": "#3A3A3A",
            "border-radius": "8px",
        },
        "nav-link-selected": {"background-color": "#29B5E8"},
    }
)

# --- NEW LOGIC TO DISPLAY TAB CONTENT ---
if selected_tab == "Dashboard":
    st.markdown("<h3 style='text-align: center;'>Trip Countdown</h3>", unsafe_allow_html=True)
    trip_start_date = datetime(2025, 9, 20)
    delta = trip_start_date - datetime.now()
    if delta.days >= 0:
        st.markdown(f"<h2 style='text-align: center; color: #29B5E8;'><strong>{delta.days} days, {delta.seconds // 3600} hours</strong> to go!</h2>", unsafe_allow_html=True)
    else:
        st.balloons()
        st.markdown("<h2 style='text-align: center;'>The adventure has begun!</h2>", unsafe_allow_html=True)

    st.divider()
    m1, m2 = st.columns(2)
    with m1: styled_metric("Trip Duration", f"{len(itinerary_df)} Days")
    with m2: styled_metric("Travelers", "8 People")
    st.divider()
    w1, w2 = st.columns(2)
    with w1:
        with st.container():
            st.subheader("☀️ Weather Forecast")
            if not itinerary_df.empty and 'Night Stay' in itinerary_df.columns and 'Date' in itinerary_df.columns:
                all_cities = itinerary_df['Night Stay'].unique().tolist()
                itinerary_df['Date_dt'] = pd.to_datetime(itinerary_df['Date']).dt.date
                today_loc_row = itinerary_df[itinerary_df['Date_dt'] <= date.today()].tail(1)
                default_city = today_loc_row.iloc[0]['Night Stay'] if not today_loc_row.empty else all_cities[0]
                default_index = all_cities.index(default_city) if default_city in all_cities else 0
                selected_city = st.selectbox("Check weather for:", all_cities, index=default_index)
                weather_data = get_weather(selected_city, st.secrets.get("api_keys", {}).get("openweathermap_api_key"))
                if weather_data and weather_data.get('cod') == 200:
                    st.metric(label=f"in {selected_city}", value=f"{weather_data['main']['temp']} °C", delta=f"Feels like {weather_data['main']['feels_like']} °C")
                else: st.info(f"Weather for {selected_city} unavailable.")

    with w2:
        with st.container():
            st.subheader("💱 Quick Converter")
            from_curr = st.selectbox("From", FIXED_CURRENCIES, index=1)
            to_curr = st.selectbox("To", FIXED_CURRENCIES, index=0)
            amount = st.number_input("Amount", value=1000.0, format="%.2f", label_visibility="collapsed")
            if rates.get(from_curr) and rates.get(to_curr):
                conv_rate = rates[to_curr] / rates[from_curr]
                result = amount * conv_rate
                st.markdown(f"""
                <div style="background-color:#262730; border-radius:10px; padding: 10px; text-align:center;">
                    <p style="color:#fafafa; font-size:1.5rem; font-weight:bold; margin:0;">{result:,.2f} {to_curr}</p>
                </div>
                """, unsafe_allow_html=True)
    st.divider()
    st.subheader("Interactive Trip Route")
    if not itinerary_df.empty and 'Night Stay' in itinerary_df.columns:
        trip_map = create_itinerary_map(itinerary_df.copy())
        if trip_map: st.pydeck_chart(trip_map, use_container_width=True)
    st.divider()

if selected_tab == "Daily Itinerary":
    st.header("🗺️ Daily Itinerary")
    st.write("Tap on a day to see details and get directions.")
    if not itinerary_df.empty:
        itinerary_df['Formatted_Date'] = pd.to_datetime(itinerary_df['Date']).dt.strftime('%A, %d %b %Y')
        for index, row in itinerary_df.iterrows():
            with st.expander(f"**{row['Formatted_Date']}**: {row['Location(s)']} → **{row['Night Stay']}**"):
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**🚗 Travel:** {row['Travel Details']}")
                    if 'Attractions' in row and pd.notna(row['Attractions']): st.markdown(f"**🌟 Highlights:** {row['Attractions']}")
                with cols[1]:
                    destination = row['Night Stay']
                    if index == 0:
                        try: origin = row['Location(s)'].split('→')[0].strip()
                        except: origin = "Bandaranaike International Airport"
                    else: origin = itinerary_df.iloc[index-1]['Night Stay']
                    gmaps_url = f"https://www.google.com/maps/dir/{urllib.parse.quote_plus(origin+', Sri Lanka')}/{urllib.parse.quote_plus(destination+', Sri Lanka')}"
                    st.link_button(f"Directions 🗺️", gmaps_url, use_container_width=True)

if selected_tab == "Travel Handbook":
    st.header("📖 Travel Handbook")
    handbook_tabs = st.tabs(["🗣️ Essential Phrases", "💡 Travel Tips", "✅ Packing Checklist", "🚨 Emergency Info"])
    with handbook_tabs[0]:
        st.subheader("Essential Sinhala Phrases"); st.dataframe(phrases_df, hide_index=True, use_container_width=True)
    with handbook_tabs[1]:
        st.subheader("Top Travel Tips")
        if not tips_df.empty and 'Category' in tips_df.columns:
            for category in tips_df['Category'].unique():
                with st.expander(f"**{category}**"):
                    for _, row in tips_df[tips_df['Category'] == category].iterrows(): st.markdown(f"- {row['Tip']}")
    with handbook_tabs[2]:
        st.subheader("Our Packing Checklist")
        if not checklist_df.empty and 'Category' in checklist_df.columns:
            for category in checklist_df['Category'].unique():
                st.write(f"**{category}**")
                for _, row in checklist_df[checklist_df['Category'] == category].iterrows(): st.checkbox(row['Item'], key=f"pack_{row['Item']}")
    with handbook_tabs[3]:
        st.subheader("Emergency Contacts & Info")
        st.error("""- **National Emergency / Police:** `119`\n- **Ambulance / Fire & Rescue:** `110`\n- **Tourist Police (Colombo):** `011-2421052`\n\n**Important:** Keep digital/physical copies of your passport, visa, and flight details. Share your itinerary with family.""")