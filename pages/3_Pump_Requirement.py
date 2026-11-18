import streamlit as st
import pandas as pd
import math
from datetime import datetime, timedelta

st.set_page_config(page_title="Pump Requirement", layout="wide")
st.title("🚜 Automated Irrigation & Pump Sizing")

# Fetch Session Data
meta = st.session_state.get("location_meta")
df_iwr = st.session_state.get("iwr_data")

if not meta or df_iwr is None:
    st.warning("⚠️ No session data found. Please run the Location (Page 1) and Crop (Page 2) pipelines first.")
    st.stop()

# --- 1. FIELD STATUS & WATER BALANCE ---
st.subheader("1. Field Status & Water Balance")
col1, col2, col3 = st.columns(3)

with col1:
    area_ha = st.number_input("Cultivation Area (Hectares)", min_value=0.1, value=1.0, step=0.1)
with col2:
    last_irrigation = st.date_input("Date of Last Irrigation", value=datetime.now().date() - timedelta(days=5))
with col3:
    mad_mm = st.number_input("Allowable Depletion (mm)", min_value=1.0, value=25.0, help="Irrigate when soil water deficit reaches this threshold")

# --- 2. GROUNDWATER & PUMP PARAMS ---
st.subheader("2. Groundwater & Pumping Parameters")
p_col1, p_col2, p_col3 = st.columns(3)

with p_col1:
    st.write("**Fetching CGWB Groundwater Levels**")
    gwl_fetched = 12.5 # Simulated CGWB telemetry API fetch
    st.success(f"Current GWL for {meta['state']}: **{gwl_fetched} mbgl**")
    gwl = st.number_input("Design Groundwater Level (m)", min_value=1.0, value=float(gwl_fetched))

with p_col2:
    op_hours = st.number_input("Daily Operating Hours", min_value=1.0, max_value=24.0, value=8.0)
with p_col3:
    pump_eff = st.number_input("Pump Efficiency (%)", min_value=10.0, max_value=100.0, value=70.0)

# --- 3. CALCULATIONS & RECOMMENDATIONS ---
if st.button("⚡ Calculate Irrigation Schedule & Pump Size", type="primary"):
    today = datetime.now().date()
    days_since = (today - last_irrigation).days
    
    # Calculate average daily demand from the forecasted IWR
    avg_daily_iwr = df_iwr["IWR (mm)"].mean()
    
    if avg_daily_iwr <= 0:
        st.info("🌧️ **Rainfall exceeds crop demand.** No irrigation required at this time.")
        st.stop()
        
    # 1. Water Balance & Urgency Logic
    current_deficit_mm = days_since * avg_daily_iwr
    depletion_pct = (current_deficit_mm / mad_mm) * 100
    days_to_mad = mad_mm / avg_daily_iwr
    target_irr_date = last_irrigation + timedelta(days=math.floor(days_to_mad))
    
    is_urgent = target_irr_date <= today
    
    # Volume to apply: If urgent, we must recover the current deficit. If not, design for MAD.
    design_deficit_mm = max(current_deficit_mm, mad_mm)
    volume_m3 = (design_deficit_mm / 1000) * (area_ha * 10000)

    # 2. Irrigation System Recommendation based on GWL
    if gwl > 30:
        sys_rec = "💧 **Drip Irrigation** (Mandatory high efficiency due to deep water table)"
    elif gwl > 15:
        sys_rec = "🚿 **Sprinkler Irrigation** (Moderate efficiency required)"
    else:
        sys_rec = "🌊 **Surface/Furrow Irrigation** (Viable, but Drip/Sprinkler recommended for water conservation)"

    # 3. Pump Sizing (Hydraulic Math)
    flow_rate_m3_hr = volume_m3 / op_hours
    flow_rate_m3_s = flow_rate_m3_hr / 3600
    
    # Total Dynamic Head (TDH) = Groundwater depth + 10% assumed friction loss
    head_total = gwl * 1.10 
    
    power_kw = (1000 * 9.81 * flow_rate_m3_s * head_total) / (1000 * (pump_eff / 100))
    power_hp = power_kw / 0.7457
    
    standard_hps = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0]
    recommended_hp = next((hp for hp in standard_hps if hp >= power_hp), math.ceil(power_hp))

    st.session_state["pump_data"] = {
        "power_hp": recommended_hp,
        "power_kw": power_kw,
        "op_hours": op_hours
    }

    # --- 4. DISPLAY RESULTS ---
    st.markdown("---")
    
    # Alert Section
    if is_urgent:
        st.error(f"🚨 **URGENT IRRIGATION REQUIRED!**\n\n"
                 f"Your crop has exceeded the allowable depletion limit. The soil moisture deficit is currently at **{depletion_pct:.0f}%** of the allowable threshold.\n\n"
                 f"**Target Date Passed:** {target_irr_date.strftime('%d %b %Y')}\n\n"
                 f"Please irrigate immediately with **{current_deficit_mm:.1f} mm** of water (**{volume_m3:.1f} m³** total volume) to prevent severe crop stress.")
    else:
        st.success(f"✅ **Soil moisture is currently adequate.**\n\n"
                   f"Current depletion is at **{depletion_pct:.0f}%** of the allowable threshold.\n\n"
                   f"**Next Scheduled Irrigation:** {target_irr_date.strftime('%d %b %Y')}")

    # Metrics Section
    res_col1, res_col2 = st.columns(2)
    
    with res_col1:
        st.info("##### 📅 Schedule & System Profile")
        st.write(f"- **Days Since Last Irrigation:** {days_since} days")
        st.write(f"- **Average Daily Demand:** {avg_daily_iwr:.2f} mm/day")
        st.write(f"- **Application Volume Needed:** {volume_m3:.1f} m³")
        st.write(f"- **System Recommendation:** {sys_rec}")
        
    with res_col2:
        st.info("##### ⚙️ Pump Specifications")
        st.write(f"- **Total Dynamic Head (incl. friction):** {head_total:.1f} m")
        st.write(f"- **Required Flow Rate:** {flow_rate_m3_hr:.1f} m³/hr")
        st.write(f"- **Calculated Power:** {power_hp:.2f} HP ({power_kw:.2f} kW)")
        st.write(f"- **Recommended Commercial Pump:** **{recommended_hp} HP**")