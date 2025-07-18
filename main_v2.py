import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_option_menu import option_menu
import requests
from streamlit_lottie import st_lottie
from datetime import datetime, date
import urllib.parse
import pydeck as pdk

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sri Lanka Trip Planner",
    page_icon="🇱🇰",
    layout="wide",
)

# --- STYLING ---
st.markdown("""
<style>
    /* Main containers */
    .st-emotion-cache-18ni7ap, .st-emotion-cache-1d391kg { padding: 2rem 2rem 1rem; }
    /* Card-like containers for widgets */
    div[data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {
        border: 1px solid rgba(255, 255, 255, 0.2); background-color: #1E1E1E;
        border-radius: 10px; padding: 20px; box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
    }
    /* Custom metric box styling (Restored) */
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
    "Users": [["Name"], ["Traveler 1"], ["Traveler 2"]],
    "Expenses": [["Date", "Description", "Category", "Paid_By", "Original_Amount", "Original_Currency", "Amount_LKR", "Split_Between"]],
    "Tips": [
        ["Category", "Tip"], ["Money", "Always carry small change."], ["Health", "Drink only bottled water."],
        ["Culture", "Dress modestly for temples (cover shoulders/knees)."], ["General", "Buy a local SIM card at the airport."]
    ],
    "Phrases": [
        ["English", "Sinhala", "Pronunciation"], ["Hello", "Ayubowan", "Aayu-bo-wan"],
        ["Thank you", "Istuti", "Is-thu-thi"], ["How much?", "Kiyadha?", "Kee-yah-dha?"]
    ],
    "Checklist": [
        ["Category", "Item"], ["Documents", "Passport & Visa"], ["Electronics", "Universal Power Adapter"],
        ["Health", "Sunscreen"]
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

def append_to_sheet(client, sheet_name, data_row):
    try:
        worksheet = client.open_by_url(st.secrets["google_sheets"]["sheet_url"]).worksheet(sheet_name)
        worksheet.append_row(data_row, value_input_option='USER_ENTERED')
        get_or_create_sheet_data.clear(); return True
    except Exception as e:
        st.error(f"Failed to append data: {e}"); return False

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

def load_lottieurl(url: str):
    try:
        r = requests.get(url)
        return r.json() if r.status_code == 200 else None
    except Exception: return None

# --- UI HELPER FUNCTIONS ---
def styled_metric(label, value, help_text=""):
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
    layer_points = pdk.Layer('ScatterplotLayer', data=df, get_position='coords', get_color='[200, 30, 0, 160]', get_radius=8000, pickable=True)
    layer_path = pdk.Layer("PathLayer", data=path_data, pickable=True, width_scale=20, width_min_pixels=2, get_path="path", get_color="color", get_width=5)
    return pdk.Deck(map_style='mapbox://styles/mapbox/dark-v9', initial_view_state=view_state, layers=[layer_points, layer_path], tooltip={"html": "<b>Day {Day}:</b> {Night Stay}"}, api_keys={'mapbox': 'pk.eyJ1IjoidGhpbmtpbmctaW5zaWRlciIsImEiOiJjbDFncmQzbXAwZDJiM2lueGxscW53dGthIn0.a45p-f_wdtwnN3s_bY_1eA'})

# --- GLOBAL DATA LOADING ---
client = connect_to_gsheets()
if not client: st.stop()

itinerary_df = get_or_create_sheet_data(client, "Itinerary")
users_df = get_or_create_sheet_data(client, "Users")
expenses_df = get_or_create_sheet_data(client, "Expenses")
phrases_df = get_or_create_sheet_data(client, "Phrases")
tips_df = get_or_create_sheet_data(client, "Tips")
checklist_df = get_or_create_sheet_data(client, "Checklist")

travelers = users_df['Name'].tolist() if 'Name' in users_df.columns else []
rates_data = get_exchange_rates(st.secrets.get("api_keys", {}).get("exchangerate_api_key"))
rates = rates_data['rates']

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    sidebar_lottie = load_lottieurl("https://assets1.lottiefiles.com/packages/lf20_m9zragkd.json")
    if sidebar_lottie: st.lottie(sidebar_lottie, height=150, key="sidebar_lottie")
    st.title("Sri Lanka Trip")
    selected = option_menu(None, ["Dashboard", "Daily Itinerary", "Expense Tracker", "Travel Handbook"],
        icons=["bi-house-door-fill", "bi-calendar-week-fill", "bi-cash-coin", "bi-book-half"],
        styles={"nav-link-selected": {"background-color": "#02ab21"}})

# --- DASHBOARD PAGE ---
if selected == "Dashboard":
    st.header(f"Dashboard | Our Adventure 🇱🇰")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        main_lottie = load_lottieurl("https://assets9.lottiefiles.com/packages/lf20_g8d3ch3c.json")
        if main_lottie: st.lottie(main_lottie, height=200, key="main_lottie")
    with col2:
        st.subheader("Trip Countdown")
        trip_start_date = datetime(2025, 9, 20)
        delta = trip_start_date - datetime.now()
        if delta.days >= 0: st.markdown(f"## **{delta.days} days, {delta.seconds // 3600} hours** to go!")
        else: st.balloons(); st.markdown("## The adventure has begun!")
    
    st.divider()
    # RESTORED: Styled metric boxes for summary
    m1, m2, m3 = st.columns(3)
    with m1: styled_metric("Trip Duration", f"{len(itinerary_df)} Days")
    with m2: styled_metric("Travelers", f"{len(travelers)} People")
    with m3:
        total_spent = pd.to_numeric(expenses_df['Amount_LKR'], errors='coerce').sum() if 'Amount_LKR' in expenses_df else 0
        styled_metric("Total Spent", f"Rs {total_spent:,.0f}")
    st.divider()

    main_col, widget_col = st.columns([2, 1])
    with main_col:
        st.subheader("Interactive Trip Route")
        if not itinerary_df.empty and 'Night Stay' in itinerary_df.columns:
            trip_map = create_itinerary_map(itinerary_df.copy())
            if trip_map: st.pydeck_chart(trip_map, use_container_width=True)
    with widget_col:
        with st.container(): # Weather Widget
            st.subheader("☀️ Weather Forecast")
            if not itinerary_df.empty and 'Night Stay' in itinerary_df.columns:
                all_cities = itinerary_df['Night Stay'].unique().tolist()
                # Determine default city for today
                itinerary_df['Date_dt'] = pd.to_datetime(itinerary_df['Date']).dt.date
                today_loc_row = itinerary_df[itinerary_df['Date_dt'] <= date.today()].tail(1)
                default_city = today_loc_row.iloc[0]['Night Stay'] if not today_loc_row.empty else all_cities[0]
                default_index = all_cities.index(default_city) if default_city in all_cities else 0
                
                # Dropdown with default and option to change
                selected_city = st.selectbox("Check weather for:", all_cities, index=default_index)
                
                weather_data = get_weather(selected_city, st.secrets.get("api_keys", {}).get("openweathermap_api_key"))
                if weather_data and weather_data.get('cod') == 200:
                    st.metric(label=f"in {selected_city}", value=f"{weather_data['main']['temp']} °C", delta=f"Feels like {weather_data['main']['feels_like']} °C")
                    st.write(f"_{weather_data['weather'][0]['description'].title()}_ with _{weather_data['main']['humidity']}% humidity._")
                else: st.info(f"Weather for {selected_city} unavailable.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(): # Currency Converter Widget
            st.subheader("💱 Quick Converter")
            cols = st.columns(2)
            from_curr = cols[0].selectbox("From", FIXED_CURRENCIES, index=1)
            to_curr = cols[1].selectbox("To", FIXED_CURRENCIES, index=0)
            amount = st.number_input("Amount", value=1000.0, format="%.2f", label_visibility="collapsed")
            if rates.get(from_curr) and rates.get(to_curr):
                conv_rate = rates[to_curr] / rates[from_curr]
                result = amount * conv_rate
                # REFINED: Currency output in a styled box
                st.markdown(f"""
                <div style="background-color:#262730; border-radius:10px; padding: 10px; text-align:center;">
                    <p style="color:#fafafa; font-size:1.5rem; font-weight:bold; margin:0;">{result:,.2f} {to_curr}</p>
                </div>
                """, unsafe_allow_html=True)

# --- ITINERARY PAGE ---
if selected == "Daily Itinerary":
    st.header("🗺️ Daily Itinerary")
    if not itinerary_df.empty:
        itinerary_df['Date'] = pd.to_datetime(itinerary_df['Date']).dt.strftime('%A, %d %b %Y')
        for index, row in itinerary_df.iterrows():
            with st.expander(f"**{row['Date']}**: {row['Location(s)']} → **{row['Night Stay']}**"):
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**🚗 Travel:** {row['Travel Details']}")
                    if 'Attractions' in row and pd.notna(row['Attractions']): st.markdown(f"**🌟 Highlights:** {row['Attractions']}")
                with cols[1]:
                    # UPGRADED: A-to-B Google Maps Directions Link
                    destination = row['Night Stay']
                    if index == 0: # First day
                        try:
                            origin = row['Location(s)'].split('→')[0].strip()
                        except:
                            origin = "Bandaranaike International Airport" # Fallback
                    else: # Subsequent days
                        origin = itinerary_df.iloc[index-1]['Night Stay']
                    
                    gmaps_url = f"https://www.google.com/maps/dir/{urllib.parse.quote_plus(origin+', Sri Lanka')}/{urllib.parse.quote_plus(destination+', Sri Lanka')}"
                    st.link_button(f"Get Directions 🗺️", gmaps_url, use_container_width=True)

# --- EXPENSE TRACKER PAGE ---
if selected == "Expense Tracker":
    st.header("💰 Expense Tracker")
    if not travelers:
        st.warning("Please add travelers in 'Manage Travelers' to begin.")
    else:
        tab1, tab2, tab3 = st.tabs(["📊 Balances", "➕ Add Expense", "👥 Manage Travelers"])
        with tab1:
            if not expenses_df.empty and 'Amount_LKR' in expenses_df.columns:
                balances = {t: 0 for t in travelers}
                expenses_df['Amount_LKR'] = pd.to_numeric(expenses_df['Amount_LKR'], errors='coerce').fillna(0)
                for _, exp in expenses_df.iterrows():
                    split_list = [s.strip() for s in str(exp['Split_Between']).split(',') if s.strip() in travelers]
                    if not split_list: continue
                    share = exp['Amount_LKR'] / len(split_list)
                    if exp['Paid_By'] in balances: balances[exp['Paid_By']] += exp['Amount_LKR']
                    for p in split_list:
                        if p in balances: balances[p] -= share
                st.subheader("Net Balances")
                cols = st.columns(len(travelers))
                for i, t in enumerate(travelers):
                    with cols[i]:
                        st.metric(label=t, value=f"Rs {balances.get(t, 0):,.2f}", delta_color="inverse" if balances.get(t, 0) > 0 else "off")
                st.subheader("How to Settle Up")
                creditors = {p: b for p, b in balances.items() if b > 0.01}
                debtors = {p: b for p, b in balances.items() if b < -0.01}
                settlements = []
                while creditors and debtors:
                    c_name, c_val = max(creditors.items(), key=lambda x: x[1])
                    d_name, d_val = min(debtors.items(), key=lambda x: x[1])
                    amount = min(c_val, -d_val)
                    settlements.append(f"**{d_name}** pays **{c_name}** → **Rs {amount:,.2f}**")
                    creditors[c_name] -= amount; debtors[d_name] += amount
                    if abs(creditors[c_name]) < 0.01: del creditors[c_name]
                    if abs(debtors[d_name]) < 0.01: del debtors[d_name]
                for s in settlements: st.info(s)
                if not settlements: st.success("🎉 Everyone is settled up!")
            with st.expander("View All Transactions"):
                st.dataframe(expenses_df, use_container_width=True)
        with tab2:
            st.subheader("Log a New Expense")
            with st.form("expense_form", clear_on_submit=True):
                c1,c2 = st.columns(2); description = c1.text_input("Description"); category = c2.selectbox("Category", ["Food & Drinks", "Transport", "Accommodation", "Activities", "Shopping", "Other"])
                c1,c2,c3 = st.columns(3); amount = c1.number_input("Amount", min_value=0.01, format="%.2f"); currency = c2.selectbox("Currency", FIXED_CURRENCIES, index=0); paid_by = c3.selectbox("Paid by", travelers)
                split_between = st.multiselect("Split Between", travelers, default=travelers)
                if st.form_submit_button("Add Expense", use_container_width=True):
                    if not description or not split_between: st.warning("Please fill all fields.")
                    else:
                        lkr_amount = (amount / rates[currency]) * rates['LKR']
                        new_row = [date.today().strftime("%Y-%m-%d"), description, category, paid_by, amount, currency, lkr_amount, ",".join(split_between)]
                        if append_to_sheet(client, "Expenses", new_row): st.success("Expense added!"); st.rerun()
        with tab3:
            st.subheader("Manage Travelers")
            with st.form("add_user_form"):
                new_user = st.text_input("New Traveler's Name")
                if st.form_submit_button("Add Traveler"):
                    if new_user and new_user not in travelers: append_to_sheet(client, "Users", [new_user]); st.rerun()
                    else: st.warning("Name cannot be empty or already exist.")

# --- HANDBOOK PAGE ---
if selected == "Travel Handbook":
    st.header("📖 Travel Handbook")
    tab1, tab2, tab3, tab4 = st.tabs(["💡 Travel Tips", "🗣️ Essential Phrases", "✅ Packing Checklist", "🚨 Emergency Info"])
    with tab1:
        st.subheader("Top Travel Tips")
        if not tips_df.empty and 'Category' in tips_df.columns:
            for category in tips_df['Category'].unique():
                with st.expander(f"**{category}**"):
                    for _, row in tips_df[tips_df['Category'] == category].iterrows(): st.markdown(f"- {row['Tip']}")
    with tab2:
        st.subheader("Essential Sinhala Phrases"); st.dataframe(phrases_df, hide_index=True, use_container_width=True)
    with tab3:
        st.subheader("Our Packing Checklist")
        if not checklist_df.empty and 'Category' in checklist_df.columns:
            for category in checklist_df['Category'].unique():
                st.write(f"**{category}**")
                for _, row in checklist_df[checklist_df['Category'] == category].iterrows(): st.checkbox(row['Item'], key=f"pack_{row['Item']}")
    with tab4:
        st.subheader("Emergency Contacts & Info")
        st.error("""- **National Emergency / Police:** `119`\n- **Ambulance / Fire & Rescue:** `110`\n- **Tourist Police (Colombo):** `011-2421052`\n\n**Important:** Keep digital/physical copies of your passport, visa, and flight details. Share your itinerary with family.""")