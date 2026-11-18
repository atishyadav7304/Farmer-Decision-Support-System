import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import re

st.set_page_config(page_title="Crop & IWR", layout="wide")
st.title("🌱 Agro-Climatic Profiling & Crop Selection")

# Ensure user has completed Page 1
if "location_meta" not in st.session_state or "eto_data" not in st.session_state:
    st.warning("⚠️ No location data found. Please run the Location & Forecast pipeline (Page 1) first.")
    st.stop()

meta = st.session_state["location_meta"]

@st.cache_data
def load_agro_regions():
    # Loads the GeoJSON file you just created in the root folder
    return gpd.read_file("AgroClimatic_Regions.geojson") 

# --- 1. SPATIAL INTERSECTION ---
st.subheader(f"Agro-Climatic Profile for {meta['village']}, {meta['district']}")

with st.spinner("Analyzing agro-climatic zones..."):
    gdf_zones = load_agro_regions()
    
    # Create a spatial point from Page 1 coordinates (Longitude first, then Latitude)
    village_point = Point(meta["longitude"], meta["latitude"]) 
    
    # Find which region polygon contains our village point
    matched_zone = gdf_zones[gdf_zones.geometry.contains(village_point)]

if matched_zone.empty:
    st.error("Coordinates fall outside the defined Agro-Climatic Regions in your dataset.")
    st.stop()

# Extract properties from the matched region
zone_data = matched_zone.iloc[0]
region_name = zone_data.get("regionname", "Unknown Region")
soil_types = zone_data.get("soil", "Data unavailable")
raw_crops = str(zone_data.get("majorcrops", "Custom Crop"))

# Clean up the crop string to create a dropdown list
# Replaces 'and' with commas, removes extra spaces, and splits into a clean list
clean_crops = [crop.strip().capitalize() for crop in re.split(r',|\band\b', raw_crops) if crop.strip()]
if not clean_crops:
    clean_crops = ["Custom Crop"]

# --- 2. DISPLAY PROFILE ---
col1, col2 = st.columns(2)
with col1:
    st.info(f"**📍 Zone:** {region_name}\n\n**🌍 Soil Profile:** {soil_types}")
with col2:
    st.success(f"**🌡️ Jan Temp:** {zone_data.get('avgtmp_jan', 'N/A')}\n\n**☀️ Jul Temp:** {zone_data.get('avgtmp_jul', 'N/A')}\n\n**🌧️ Annual Rain:** {zone_data.get('avgann_rf', 'N/A')}")

st.markdown("---")

# --- 3. CROP WATER REQUIREMENT (ETc) CALCULATION ---
st.subheader("Automated Crop Water Requirement (ETc)")

c_col1, c_col2 = st.columns([1, 2])

with c_col1:
    selected_crop = st.selectbox("Select Recommended Crop", clean_crops + ["Other/Custom"])
    
    # Standard FAO-56 Kc values inputs
    kc_ini = st.number_input("Kc Initial", value=0.40, format="%.2f")
    kc_mid = st.number_input("Kc Mid-Season", value=1.15, format="%.2f")
    kc_end = st.number_input("Kc End-Season", value=0.50, format="%.2f")

with c_col2:
    st.write("This module combines the 5-day forecasted $ET_o$ (from Page 1) with your selected Crop Coefficient ($K_c$) to calculate daily crop water demand.")
    
    if st.button("⚡ Calculate ETc & Net Irrigation (IWR)", type="primary"):
        # Load forecast dataframe (contains 'date', 'ETo', 'rain')
        df_forecast = st.session_state["eto_data"].copy()
        
        # Calculate ETc
        # For a 5-day forecast, we assume the crop is in its current stage. 
        # Using Kc Mid for a conservative (maximum) water demand estimate.
        df_forecast["Kc"] = kc_mid 
        df_forecast["ETc (mm/day)"] = df_forecast["ETo (mm/day)"] * df_forecast["Kc"]
        
        # Calculate Effective Rainfall (USDA SCS Daily Approximation)
        def calc_effective_rain(p_val):
            if p_val <= 0: return 0.0
            elif p_val <= 8.3: return p_val * 0.8
            else: return p_val * 0.6
            
        df_forecast["eff_rain"] = df_forecast["rain"].apply(calc_effective_rain)
        
        # Calculate Net Irrigation Water Requirement (IWR)
        df_forecast["IWR (mm)"] = df_forecast["ETc (mm/day)"] - df_forecast["eff_rain"]
        df_forecast["IWR (mm)"] = df_forecast["IWR (mm)"].clip(lower=0.0).round(2)
        
        # Save to session state for Page 3 (Pump Power)
        st.session_state["iwr_data"] = df_forecast
        
        st.success("ETc and Irrigation Water Requirement calculated!")
        
        # Format date for the line chart index
        df_forecast['date_str'] = pd.to_datetime(df_forecast['date']).dt.strftime('%Y-%m-%d')
        
        # Visualization
        st.line_chart(df_forecast.set_index("date_str")[["ETc (mm/day)", "eff_rain", "IWR (mm)"]], use_container_width=True)
        
        display_cols = ['date_str', 'ETc (mm/day)', 'rain', 'eff_rain', 'IWR (mm)']
        st.dataframe(df_forecast[display_cols].style.format({
            'ETc (mm/day)': '{:.2f}', 'rain': '{:.2f}', 'eff_rain': '{:.2f}', 'IWR (mm)': '{:.2f}'
        }), use_container_width=True, hide_index=True)