import streamlit as st

st.set_page_config(
    page_title="AgroHydrology Suite",
    page_icon="🌾",
    layout="wide"
)

# Shared Session State Initialization
if "location_meta" not in st.session_state:
    st.session_state["location_meta"] = {}
if "eto_data" not in st.session_state:
    st.session_state["eto_data"] = None
if "etc_data" not in st.session_state:
    st.session_state["etc_data"] = None
if "iwr_data" not in st.session_state:
    st.session_state["iwr_data"] = None
if "pump_data" not in st.session_state:
    st.session_state["pump_data"] = {}

st.title("🌾 Agricultural Water Management Dashboard")
st.markdown("### Integrated Geospatial Decision Support System")
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Welcome to the Dashboard")
    st.write("""
    This platform provides an automated processing pipeline for agro-meteorological forecasting, 
    crop water dynamics, and irrigation pump sizing.
    
    #### Pipeline Architecture
    1. **Location & Weather**: Select an Indian village to automatically extract coordinates, fetch 20-year historical Open-Meteo data, run a 5-day LSTM forecast, and calculate Hargreaves-Samani $ET_o$.
    2. **Crop & Irrigation (IWR)**: Identify the agro-climatic zone, select suitable crops, calculate daily Crop Water Requirements ($ET_c$), and compute Net Irrigation Water Requirements.
    3. **Pump Requirement**: Fetch CGWB groundwater levels and size the required irrigation pump (HP) based on peak demand.
    4. **Solar Panel Sizing**: Calculate the photovoltaic array area required to run the automated pump system.
    """)

with col2:
    st.info("#### Quick Navigation")
    st.markdown("""
    * 📍 **Page 1**: Location, Forecast & ETo
    * 🌱 **Page 2**: Crop Selection & IWR
    * 🚜 **Page 3**: Pump Requirement
    * ☀️ **Page 4**: Solar Panel Sizing
    """)
    
    st.metric(label="System Status", value="API Ready", delta="Live")