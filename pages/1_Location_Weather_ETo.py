import os
import glob
import streamlit as st
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import openmeteo_requests
import requests_cache
from retry_requests import retry
from datetime import datetime, timedelta
import math
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense

st.set_page_config(page_title="Location & Weather", layout="wide")
st.title("📍 Location, Forecast & Hargreaves-Samani ETo")

# --- 1. DYNAMIC SPATIAL DATA LOADING ---
INDIA_DIR = "India"

@st.cache_data
def get_available_states():
    """Reads .shp files directly inside the 'India' directory to populate the State dropdown."""
    if os.path.exists(INDIA_DIR):
        # Find all .shp files in the directory
        shp_files = glob.glob(os.path.join(INDIA_DIR, "*.shp"))
        # Extract the state name from the filename (e.g., "HARYANA.shp" -> "HARYANA")
        states = [os.path.splitext(os.path.basename(f))[0] for f in shp_files]
        return sorted(states)
    return []

@st.cache_data
def load_state_data(state_name):
    """Loads the specific .shp file for the selected state."""
    shp_path = os.path.join(INDIA_DIR, f"{state_name}.shp")
    if os.path.exists(shp_path):
        return gpd.read_file(shp_path)
    return gpd.GeoDataFrame()

# --- 2. CASCADING DROPDOWNS ---
st.subheader("1. Select Location")

available_states = get_available_states()

if not available_states:
    st.error(f"Could not find state folders in the '{INDIA_DIR}' directory. Please check your folder structure.")
    st.stop()

col1, col2, col3, col4 = st.columns(4)

with col1:
    country = st.selectbox("Country", ["India"])
    
with col2:
    selected_state = st.selectbox("State", available_states)

# Load only the selected state's shapefile into memory
gdf_state = load_state_data(selected_state)

if gdf_state.empty:
    st.error(f"No valid .shp file found in the {selected_state} folder.")
    st.stop()

with col3:
    # Auto-detect common District column names
    possible_dist_cols = ['DISTRICT', 'District', 'DIST_NAME', 'dtname', 'DT_NAME', 'NAME_2', 'Dist_name']
    dist_col = next((col for col in possible_dist_cols if col in gdf_state.columns), None)
    
    # Fail-safe: Let user pick if auto-detect fails
    if dist_col is None:
        dist_col = st.selectbox("Select District Column Manually", gdf_state.columns, key="manual_dist")
        
    districts = gdf_state[dist_col].dropna().unique()
    selected_district = st.selectbox("District", sorted(districts), key="select_dist")

with col4:
    # Filter state data to the selected district
    district_data = gdf_state[gdf_state[dist_col] == selected_district]

    # Auto-detect common Village column names
    possible_vill_cols = ['VILLAGE', 'Village', 'VILL_NAME', 'vilname', 'VILLNAME', 'NAME_3', 'NAME', 'Vill_name']
    vill_col = next((col for col in possible_vill_cols if col in district_data.columns), None)
    
    # Fail-safe: Let user pick if auto-detect fails
    if vill_col is None:
        vill_col = st.selectbox("Select Village Column Manually", district_data.columns, key="manual_vill")
        
    villages = district_data[vill_col].dropna().unique()
    selected_village = st.selectbox("Village", sorted(villages), key="select_vill")

# --- 3. EXTRACTION & CALCULATION PIPELINE ---
if st.button("Extract Coordinates & Fetch Data", type="primary", key="extract_btn"):
    
    # Locate the specific village geometry
    village_geom = district_data[district_data[vill_col] == selected_village]
        
    if not village_geom.empty:
        # Reproject to WGS84 (Lat/Lon) to ensure correct coordinate format
        if village_geom.crs and village_geom.crs != "EPSG:4326":
            village_geom = village_geom.to_crs("EPSG:4326")
            
        centroid = village_geom.geometry.centroid.iloc[0]
        lat, lon = centroid.y, centroid.x
        
        st.session_state["location_meta"] = {
            "country": "India", "state": selected_state, 
            "district": selected_district, "village": selected_village,
            "latitude": lat, "longitude": lon
        }
        st.success(f"Coordinates Extracted: {lat:.4f}°N, {lon:.4f}°E")
        
        # --- FETCH HISTORICAL WEATHER (Open-Meteo) ---
        with st.spinner("Fetching 20 years of historical weather data..."):
            cache_session = requests_cache.CachedSession('.cache', expire_after=-1)
            retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
            openmeteo = openmeteo_requests.Client(session=retry_session)
            
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=365*20) # 20 Years
            
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
                "timezone": "Asia/Kolkata"
            }
            response = openmeteo.weather_api(url, params=params)[0]
            daily = response.Daily()
            
            df_weather = pd.DataFrame({
                "date": pd.date_range(
                    start=pd.to_datetime(daily.Time(), unit="s"),
                    end=pd.to_datetime(daily.TimeEnd(), unit="s"),
                    freq=pd.Timedelta(seconds=daily.Interval()),
                    inclusive="left"
                ),
                "tmax": daily.Variables(0).ValuesAsNumpy(),
                "tmin": daily.Variables(1).ValuesAsNumpy(),
                "rain": daily.Variables(2).ValuesAsNumpy()
            }).dropna()
            
        # --- LSTM FORECASTING (Next 5 Days) ---
        with st.spinner("Training LSTM model for 5-day forecast..."):
            scaler = MinMaxScaler()
            scaled_data = scaler.fit_transform(df_weather[['tmax', 'tmin', 'rain']])
            
            seq_length = 30
            X, y = [], []
            for i in range(len(scaled_data) - seq_length):
                X.append(scaled_data[i:i+seq_length])
                y.append(scaled_data[i+seq_length])
            X, y = np.array(X), np.array(y)
            
            # Build LSTM Model
            model = Sequential([
                LSTM(50, activation='relu', input_shape=(seq_length, 3)),
                Dense(3)
            ])
            model.compile(optimizer='adam', loss='mse')
            # Train on the most recent 1000 days for UI responsiveness
            model.fit(X[-1000:], y[-1000:], epochs=5, verbose=0) 
            
            # Forecast 5 days
            last_seq = scaled_data[-seq_length:]
            forecasts = []
            for _ in range(5):
                pred = model.predict(last_seq.reshape(1, seq_length, 3), verbose=0)
                forecasts.append(pred[0])
                last_seq = np.vstack([last_seq[1:], pred])
                
            forecast_inv = scaler.inverse_transform(forecasts)
            dates = [end_date + timedelta(days=i+1) for i in range(5)]
            
            df_forecast = pd.DataFrame(forecast_inv, columns=['tmax', 'tmin', 'rain'])
            df_forecast['date'] = dates
            # Prevent negative rainfall forecasts
            df_forecast['rain'] = df_forecast['rain'].clip(lower=0.0) 
            
        # --- HARGREAVES-SAMANI ETo CALCULATION ---
        def calc_hargreaves_eto(row, lat_deg):
            lat_rad = math.radians(lat_deg)
            jday = row['date'].timetuple().tm_yday
            year = row['date'].year
            n_days = 366 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 365
            
            # Solar declination
            delta = 0.409 * math.sin((2 * math.pi * jday / n_days) - 1.39)
            # Sunset hour angle
            ws = math.acos(-math.tan(lat_rad) * math.tan(delta))
            # Inverse relative distance Earth-Sun
            dr = 1 + 0.033 * math.cos(2 * math.pi * jday / n_days)
            # Extraterrestrial radiation (Ra) in MJ/m2/day
            ra = (24 * 60 / math.pi) * 0.0820 * dr * (
                ws * math.sin(lat_rad) * math.sin(delta) + math.cos(lat_rad) * math.cos(delta) * math.sin(ws)
            )
            
            tmean = (row['tmax'] + row['tmin']) / 2
            t_diff = max(row['tmax'] - row['tmin'], 0)
            eto = 0.0023 * 0.408 * ra * (tmean + 17.8) * math.sqrt(t_diff)
            return eto

        df_forecast['ETo (mm/day)'] = df_forecast.apply(lambda r: calc_hargreaves_eto(r, lat), axis=1)
        st.session_state["eto_data"] = df_forecast
        
        # --- DISPLAY RESULTS ---
        st.markdown("---")
        st.write("##### 5-Day Forecast: Weather & ETo (Hargreaves-Samani)")
        
        display_df = df_forecast.copy()
        
        # FIX: Convert to pandas datetime before using the .dt accessor
        display_df['date'] = pd.to_datetime(display_df['date']).dt.strftime('%Y-%m-%d')
        
        st.dataframe(display_df.style.format({
            'tmax': '{:.1f}', 'tmin': '{:.1f}', 'rain': '{:.1f}', 'ETo (mm/day)': '{:.2f}'
        }), use_container_width=True)
        
        st.line_chart(df_forecast.set_index('date')['ETo (mm/day)'], use_container_width=True)