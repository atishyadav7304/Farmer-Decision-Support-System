import streamlit as st
import numpy as np
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import datetime, timedelta
import math

st.set_page_config(page_title="Solar Panel Sizing", layout="wide")
st.title("☀️ Automated Solar PV Array Sizing")

meta = st.session_state.get("location_meta")
pump = st.session_state.get("pump_data")

if not meta or not pump:
    st.warning("⚠️ Missing session data. Please run the previous pages to extract coordinates and calculate pump size.")
    st.stop()

st.subheader("1. Photovoltaic Array Design Parameters")
col1, col2, col3 = st.columns(3)

with col1:
    st.info("**Pump Specifications**")
    st.write(f"- **Power Load:** {pump['power_hp']} HP ({pump['power_kw']:.2f} kW)")
    st.write(f"- **Daily Runtime:** {pump['op_hours']} hours")
with col2:
    panel_eff = st.number_input("Solar Panel Efficiency (%)", value=20.0, max_value=40.0)
with col3:
    sys_loss = st.number_input("System Performance Ratio (%)", value=75.0, help="Accounts for losses from dust, temperature, and inverter inefficiency.")

if st.button("⚡ Fetch 10-Year Solar History & Size PV Array", type="primary"):
    with st.spinner(f"Fetching 10 years of historical solar radiation data for {meta['village']}, {meta['state']}..."):
        lat, lon = meta["latitude"], meta["longitude"]
        
        # Setup the Open-Meteo API client with cache and retry
        cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365*10) # 10 Years
        
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "daily": ["shortwave_radiation_sum"],
            "timezone": "Asia/Kolkata"
        }
        
        try:
            response = openmeteo.weather_api(url, params=params)[0]
            daily = response.Daily()
            rad_values = daily.Variables(0).ValuesAsNumpy()
            
            # Clean data: remove NaNs and zeros
            rad_values = rad_values[~np.isnan(rad_values)]
            rad_values = rad_values[rad_values > 0]
            
            # Convert MJ/m2 to standard Solar Insolation (kWh/m2/day)
            # 1 kWh = 3.6 MJ
            avg_insolation = np.mean(rad_values) / 3.6
            
            # Use the 10th percentile for a conservative, worst-case design scenario
            min_insolation = np.percentile(rad_values, 10) / 3.6 
            
        except Exception as e:
            st.error(f"Failed to fetch solar data: {e}")
            st.stop()
            
    # Computations
    daily_energy_req_kwh = pump['power_kw'] * pump['op_hours']
    
    # E_usable = Insolation * Panel_Efficiency * System_Efficiency
    usable_energy_per_m2 = min_insolation * (panel_eff / 100) * (sys_loss / 100)
    
    required_area_m2 = daily_energy_req_kwh / usable_energy_per_m2
    system_kwp = required_area_m2 * (panel_eff / 100)
    
    # Assuming standard commercial solar panels (approx 2m x 1m = 2m² per panel)
    num_panels = math.ceil(required_area_m2 / 2.0)

    # --- DISPLAY RESULTS ---
    st.markdown("---")
    res1, res2 = st.columns(2)
    
    with res1:
        st.write("##### 🌍 Local Solar Profile (10-Year History)")
        st.metric("Average Daily Insolation", f"{avg_insolation:.2f} kWh/m²/day")
        st.metric("Conservative Design Insolation (10th Pct)", f"{min_insolation:.2f} kWh/m²/day")
        
    with res2:
        st.success("##### ☀️ Recommended PV Installation")
        st.write(f"- **Daily Energy Demand:** {daily_energy_req_kwh:.2f} kWh/day")
        st.write(f"- **Total System Capacity:** **{system_kwp:.2f} kWp**")
        st.write(f"- **Required Panel Area:** **{required_area_m2:.1f} m²**")
        st.write(f"- **Estimated Physical Array:** ~{num_panels} standard commercial panels")