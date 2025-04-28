from skyfield.api import load, Topos
from skyfield import almanac
from skyfield.positionlib import position_of_radec
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
from pytz import timezone
import gradio as gr
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import io
import urllib.request

# Load ephemeris data and timescale
eph = load('de441.bsp')
earth, moon, sun = eph['earth'], eph['moon'], eph['sun']
ts = load.timescale()

def get_moon_age_and_new_moon(time, utc_offset):
    """Calculate Moon Age and Time of New Moon in local time."""
    # Find the previous and next new moons
    t0 = ts.utc(time.utc_datetime() - timedelta(days=30))
    t1 = ts.utc(time.utc_datetime() + timedelta(days=30))
    phases = almanac.moon_phases(eph)
    times, events = almanac.find_discrete(t0, t1, phases)

    # Filter for new moons (event == 0) and convert to UTC datetime for comparison
    new_moons = [(t, t.utc_datetime()) for t, e in zip(times, events) if e == 0]
    current_time = time.utc_datetime()

    # Find the most recent new moon
    previous_new_moon = max((t for t, dt in new_moons if dt <= current_time),
                          key=lambda t: t.utc_datetime())

    # Find the next new moon
    next_new_moon = min((t for t, dt in new_moons if dt > current_time),
                       key=lambda t: t.utc_datetime())

    # Calculate Moon Age (time since last new moon)
    moon_age_days = (time.tt - previous_new_moon.tt)

    # Convert new moon times to local time
    previous_new_moon_local = previous_new_moon.utc_datetime() + timedelta(hours=utc_offset)
    next_new_moon_local = next_new_moon.utc_datetime() + timedelta(hours=utc_offset)

    return moon_age_days, previous_new_moon_local, next_new_moon_local

def compute_moon_sun_data(observer, time):
    """Computes Moon and Sun data at the specified time."""
    moon_astrometric = observer.at(time).observe(moon).apparent()
    sun_astrometric = observer.at(time).observe(sun).apparent()
    moon_alt, moon_az, _ = moon_astrometric.altaz()
    sun_alt, sun_az, _ = sun_astrometric.altaz()

    # Topocentric Elongation Calculation
    topocentric_elongation = moon_astrometric.separation_from(sun_astrometric).degrees

    # Geocentric Elongation Calculation
    moon_geocentric = earth.at(time).observe(moon)
    sun_geocentric = earth.at(time).observe(sun)
    geocentric_elongation = moon_geocentric.separation_from(sun_geocentric).degrees

    azimuth_diff = moon_az.degrees - sun_az.degrees
    moon_ra, moon_dec, _ = moon_astrometric.radec()
    sun_ra, sun_dec, _ = sun_astrometric.radec()

    # Calculate Lama Hilal (duration of crescent moon visibility)
    # Assuming 15 degrees per hour for the Earth's rotation
    lama_hilal = moon_alt.degrees / 15  # moon_alt is already in degrees

    # Calculate Cahaya (Moon's illumination percentage)
    # Use Skyfield's illuminated function
    cahaya = almanac.fraction_illuminated(eph, 'moon', time) * 100

    # Convert Cahaya to Usbu'
    cahaya_usbu = cahaya / 12.5  # Divide by 12.5 to get Usbu' value


    # --- Moon Lag Time Calculation ---
    # Get the Moon's right ascension and declination at the current time
    moon_ra, moon_dec, _ = moon_astrometric.radec()  

    # Calculate the Moon's position 24 hours earlier
    time_24h_ago = time - timedelta(hours=24)
    moon_astrometric_24h_ago = observer.at(time_24h_ago).observe(moon).apparent()
    moon_ra_24h_ago, moon_dec_24h_ago, _ = moon_astrometric_24h_ago.radec()

    # Calculate the difference in right ascension (in hours)
    ra_diff_hours = (moon_ra.hours - moon_ra_24h_ago.hours) * 24  

    # Moon lag time is the RA difference (positive value indicates lag)
    moon_lag_time = ra_diff_hours  


    return (moon_alt.degrees, sun_alt.degrees, topocentric_elongation, geocentric_elongation,
            azimuth_diff, moon_ra, moon_dec, sun_ra, sun_dec, moon_az.degrees, sun_az.degrees, lama_hilal, cahaya, cahaya_usbu, moon_lag_time)

def check_irnu_criteria(moon_alt, geocentric_elongation):
    if moon_alt > 3 and geocentric_elongation > 6.4:
        return ("✅ MEMENUHI KRITERIA IRNU\n"
                "✅ Meets IRNU Criteria\n"
                "✅ 符合 IRNU 标准\n"
                "✅ يفي بمعايير IRNU")
    else:
        return ("❌ TIDAK MEMENUHI KRITERIA IRNU\n"
                "❌ Does not meet IRNU Criteria\n"
                "❌ 不符合 IRNU 标准\n"
                "❌ لا يفي بمعايير IRNU")

def get_cardinal_direction(azimuth):
    """Converts azimuth degrees to a cardinal direction with icons."""
    directions = {
        "U": "⬆️ Utara",
        "UTL": "↗️ Utara-Timur Laut",
        "TL": "↗️ Timur Laut",
        "TTL": "↗️ Timur-Timur Laut",
        "T": "➡️ Timur",
        "TTG": "↘️ Timur-Tenggara",
        "TG": "↘️ Tenggara",
        "STG": "↘️ Selatan-Tenggara",
        "S": "⬇️ Selatan",
        "SBD": "↙️ Selatan-Barat Daya",
        "BD": "↙️ Barat Daya",
        "BBD": "↙️ Barat-Barat Daya",
        "B": "⬅️ Barat",
        "BBL": "↖️ Barat-Barat Laut",
        "BL": "↖️ Barat Laut",
        "UBL": "↖️ Utara-Barat Laut"
    }
    index = int((azimuth + 11.25) / 22.5) % 16
    return list(directions.values())[index]

def create_visualization(moon_alt, sun_alt, moon_azimuth, sun_az, geocentric_elongation, year, month, day, hour, minute, day29, time_option):
    """Creates the visualization plot with background image."""
    try:
        # Load background image
        with urllib.request.urlopen('https://images.unsplash.com/photo-1535914728398-fcc06686536c?q=80&w=2954&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D') as url:
            bg_img = Image.open(url)
            bg_img = np.array(bg_img)

        fig, ax = plt.subplots(figsize=(12, 6))

        # Dynamically adjust background extent (Further Enhanced)
        bg_extent = [
            min(moon_azimuth, sun_az) - 15,
            max(moon_azimuth, sun_az) + 15,
            min(0, moon_alt, sun_alt) - 7,
            max(0, moon_alt, sun_alt) + 7
        ]


        # Plot background
        ax.imshow(bg_img, extent=bg_extent, aspect='auto', alpha=0.7)

        # Plot Moon position
        ax.plot(moon_azimuth, moon_alt, 'o', color='yellow', markersize=12, label='Bulan')
        # ax.annotate('Bulan', (moon_azimuth, moon_alt),
        #            textcoords="offset points", xytext=(10, 10),
        #            ha='center', color='yellow', fontsize=12, weight='bold')

        # Plot Sun position
        ax.plot(sun_az, sun_alt, 'o', color='red', markersize=14, label='Matahari')  # Removed .degrees from sun_az
        # ax.annotate('Matahari', (sun_az, sun_alt),  # Removed .degrees from sun_az
        #            textcoords="offset points", xytext=(10, 10),
        #            ha='center', color='red', fontsize=12, weight='bold')

        # Horizon Line
        ax.axhline(0, color='red', linestyle='-', linewidth=2)


        # --- Geocentric Elongation Lines ---
        if day29 == "Yes":  # Check if day29_input is "Yes"
            # Line connecting Sun to Moon (existing)
            ax.plot([sun_az, moon_azimuth], [sun_alt, moon_alt], '--',
                    color='white', linewidth=1.5, label="Sudut Elongasi")
            ax.text((sun_az + moon_azimuth) / 2, (sun_alt + moon_alt) / 2 + 1,
                    f"{geocentric_elongation:.2f}°", color='white',
                    ha='right', va='center', fontsize=10)

            # Line connecting Earth to Moon (new)
            # Calculate the endpoint coordinates
            earth_line_end_x = moon_azimuth  # Earth azimuth = Moon azimuth
            earth_line_end_y = 0  # Earth altitude = 0 (horizon)

            # Draw the earth line
            ax.plot([moon_azimuth, earth_line_end_x], [moon_alt, earth_line_end_y], '--',
                    color='white', linewidth=1.5)
            ax.text(moon_azimuth, moon_alt / 2 + 1, " ", color='lightblue', ha='center', va='center', fontsize=10)  # Placeholder for degree label

            # Add helping lines with annotations
            ax.axhline(3, color='orange', linestyle='--', label='Ketinggian Minimal Imkan')



        # Set plot limits to match background extent
        ax.set_xlim(bg_extent[0], bg_extent[1])
        ax.set_ylim(bg_extent[2], bg_extent[3])

        # Labels and styling
        ax.set_xlabel('Azimuth (°)', fontsize=14, weight='bold', color='white')
        ax.set_ylabel('Ketinggian/Altitude (°)', fontsize=14, weight='bold', color='white')

        # Set the plot title based on time_option
        if time_option.lower() == "current":
            title = f'Moon and Sun Position (Current Time)'
        elif time_option.lower() == "sunset":
            title = f'Hilal saat Ghurub (Sunset)'
            # title = f'Hilal saat Ghurub/'{time_label} {time_display.strftime('%Y-%m-%d %H:%M')}
        else: # specific or any other case
            title = f'Moon and Sun Position ({year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d})'

        ax.set_title(title, fontsize=16, weight='bold', color='white')


        # Customize grid and legend
        ax.grid(True, linestyle='--', alpha=0.4, color='white')
        ax.legend(facecolor='black', edgecolor='white', labelcolor='white')

        # Style the axis labels
        ax.tick_params(colors='white')
        for spine in ax.spines.values():
            spine.set_color('white')

        # Save plot to buffer with transparent background
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=300,
                   facecolor='black', edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        print(f"Visualization error: {str(e)}")


def moon_sun_report(location_option, city, manual_lat, manual_lon,
                    time_option, year, month, day, hour, minute, day29):
    """Computes the Moon & Sun report using the chosen location and time."""
    try:
        # Initialize geolocator and timezone finder
        geolocator = Nominatim(user_agent="Ephemiris Moon-Sun Calculator")
        tf = TimezoneFinder()

        # Determine location based on option
        if location_option == "City":
            location = geolocator.geocode(city)
            if not location:
                return "Location not found. Please check your city name.", None
            latitude = location.latitude
            longitude = location.longitude
        else:  # Manual input
            if manual_lat is None or manual_lon is None:
                return "Please provide both latitude and longitude for manual input.", None
            latitude = manual_lat
            longitude = manual_lon

        observer_location = Topos(latitude_degrees=latitude, longitude_degrees=longitude)
        observer = earth + observer_location

        # Get timezone information
        timezone_str = tf.timezone_at(lng=longitude, lat=latitude)
        if timezone_str:
            local_tz = timezone(timezone_str)
            sample_dt = datetime.now()
            utc_offset = local_tz.utcoffset(sample_dt).total_seconds() / 3600
        else:
            timezone_str = "Unknown"
            utc_offset = 8  # default if not found
        tz_info = f"{timezone_str} (UTC+{utc_offset:.0f})"

        # Determine the time based on time option
        if time_option.lower() == "sunset":
            t0 = ts.utc(year, month, day)
            t1 = ts.utc(year, month, day + 1)
            f = almanac.sunrise_sunset(eph, observer_location)
            t, y = almanac.find_discrete(t0, t1, f)
            if len(t[y == 0]) == 0:
                return "Sunset not found for the given date at this location.", None
            time_obj = t[y == 0][0]  # sunset time
            time_label = "(sunset)"
            time_display = time_obj.utc_datetime() + timedelta(hours=utc_offset)
            sunset_time = t[y == 0][0] # Store sunset time here         
        elif time_option.lower() == "specific":
            user_time = datetime(year, month, day, hour, minute)
            utc_time = user_time - timedelta(hours=utc_offset)
            time_obj = ts.utc(utc_time.year, utc_time.month, utc_time.day, utc_time.hour, utc_time.minute)
            time_label = "(Local Time)"
            time_display = user_time
        else:  # current
            time_obj = ts.now()
            time_label = "(Current Time)"
            time_display = time_obj.utc_datetime() + timedelta(hours=utc_offset)

        # Compute Moon and Sun positions
        (moon_alt, sun_alt, topocentric_elongation, geocentric_elongation,
         azimuth_diff, moon_ra, moon_dec, sun_ra, sun_dec, moon_azimuth, sun_azimuth, lama_hilal, cahaya, cahaya_usbu, moon_lag_time) = compute_moon_sun_data(observer, time_obj)

        # Generate visualization
        plot_buffer = create_visualization(moon_alt, sun_alt, moon_azimuth, sun_azimuth,
                                         geocentric_elongation, year, month, day,
                                         hour, minute, day29, time_option)

        cardinal_direction = get_cardinal_direction(moon_azimuth)

        # Calculate Moon Age and New Moon Time
        moon_age_days, previous_new_moon_local, next_new_moon_local = get_moon_age_and_new_moon(time_obj, utc_offset)
        moon_age_hours = moon_age_days * 24
        moon_age_days_int = int(moon_age_hours // 24)
        moon_age_hours_rem = moon_age_hours % 24

                # --- Moon Lag Time Calculation (from sunset) ---
        if time_option.lower() == "sunset": 
            # Calculate Moon position at sunset
            moon_astrometric_sunset = observer.at(sunset_time).observe(moon).apparent()
            moon_ra_sunset, _, _ = moon_astrometric_sunset.radec()

            # Calculate Moon position 24 hours before sunset
            time_24h_before_sunset = sunset_time - timedelta(hours=24)
            moon_astrometric_24h_before = observer.at(time_24h_before_sunset).observe(moon).apparent()
            moon_ra_24h_before, _, _ = moon_astrometric_24h_before.radec()

            # Calculate the difference in right ascension (in hours)
            ra_diff_hours = (moon_ra_sunset.hours - moon_ra_24h_before.hours) * 24

            # Moon lag time is the RA difference (positive value indicates lag)
            moon_lag_time = ra_diff_hours 


        # Build the report string
        report = "----- Laporan Posisi Bulan dan Matahari -----\n"
        report += f"Tanggal dan Waktu: {time_display.strftime('%Y-%m-%d %H:%M')} {time_label}\n"
        if location_option == "City":
            report += f"Lokasi Pengamat: Kota: {city}\n"
        else:
            report += f"Lokasi Pengamat: Manual: (Lintang: {latitude:.4f}, Bujur: {longitude:.4f})\n"
        report += f"Zona Waktu: {tz_info}\n\n"
        report += f"🌙 Umur Bulan: {moon_age_days_int} hari {moon_age_hours_rem:.2f} jam (sejak bulan baru terakhir)\n"
        report += f"🌑 Bulan Baru Sebelumnya: {previous_new_moon_local.strftime('%Y-%m-%d %H:%M')} Waktu Setempat\n"
        report += f"🌑 Bulan Baru Berikutnya: {next_new_moon_local.strftime('%Y-%m-%d %H:%M')} Waktu Setempat\n\n"
        report += f"🌙 Ketinggian Bulan: {moon_alt:.2f}°\n"
        if time_option.lower() == "sunset": # Add condition to display Moon Lag Time only for sunset
          report += f"🌙 Moon Lag Time: {moon_lag_time:.2f} hours\n" # Add this line

        # report += f"🌙 Lama Hilal (Visibility Duration): {lama_hilal:.2f} hours\n"
        report += f"🌙 Cahaya: {cahaya:.2f}% ({cahaya_usbu:.2f} Usbu')\n"
        report += f"☀ Azimuth Matahari: {sun_azimuth:.2f}°\n" 
        report += f"☀ Ketinggian Matahari: {sun_alt:.2f}°\n"
        report += f"🔭 Elongasi Topocentric Bulan-Matahari: {topocentric_elongation:.2f}°\n"
        report += f"🔭 Elongasi Geosentris Bulan-Matahari: {geocentric_elongation:.2f}°\n"
        report += f"🧭 Azimuth Bulan: {moon_azimuth:.2f}° ({cardinal_direction})\n"
        report += f"🧭 Perbedaan Azimuth Bulan dan Matahari: {azimuth_diff:.2f}°\n\n"
        report += f"Asensio Rekta Bulan: {moon_ra.hms()}\n"
        report += f"Deklinasi Bulan: {moon_dec.dms()}\n"
        report += f"Asensio Rekta Matahari: {sun_ra.hms()}\n"
        report += f"Deklinasi Matahari: {sun_dec.dms()}\n\n"

        if day29 == "Yes":
            report += "----------------------------------------\n"
            report += "Note:\n1. IRNU criteria are primarily applicable on the 29th day of the Hijri calendar.\n2. These criteria serve as a reference only.\n3. Using these criteria on days other than the 29th is not recommended.\n4. Local sighting and other factors are crucial for determining the start of a new lunar month.\n\n"
            report += check_irnu_criteria(moon_alt, geocentric_elongation)

        if plot_buffer is None:
            return report, None

        return report, Image.open(plot_buffer)

    except Exception as e:
        return f"An error occurred: {str(e)}", None

def update_time_fields(time_option):
    """Update visibility of time fields based on the selected time option."""
    if time_option == "sunset":
        return gr.update(visible=True), gr.update(visible=True), gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
    elif time_option == "specific":
        return gr.update(visible=True), gr.update(visible=True), gr.update(visible=True), gr.update(visible=True), gr.update(visible=True)
    else:  # current
        return gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)

def update_location_fields(location_option):
    """Update visibility of location input fields based on the selected location option."""
    if location_option == "City":
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
    else:  # Manual
        return gr.update(visible=False), gr.update(visible=True), gr.update(visible=True)

# Create the Gradio interface
with gr.Blocks() as demo:
    gr.Markdown("# Moon and Sun Position Calculator | Supervised by LFNU Taiwan")
    gr.Markdown("Enter a location and time option to compute the Moon and Sun positions along with IRNU criteria and timezone information.")

    with gr.Row():
        location_option_input = gr.Radio(
            choices=["City", "Manual"],
            label="Location Option",
            value="City"
        )

    with gr.Row():
        city_input = gr.Textbox(label="City", placeholder="Enter a city name")
        lat_input = gr.Number(label="Latitude", value=25.0494, visible=False)
        lon_input = gr.Number(label="Longitude", value=121.5198, visible=False)


    with gr.Row():
        with gr.Column():
            time_option_input = gr.Radio(
                choices=["current", "sunset", "specific"],
                label="Time Option",
                value="current"
            )
        with gr.Column():
            day29_input = gr.Radio(
                choices=["Yes", "No"],
                label="Is it day 29 in the Hijri calendar, and are you calculating the new month?",
                value="No"
            )

    with gr.Row():
        year_input = gr.Number(label="Year", value=datetime.now().year, visible=False)
        month_input = gr.Number(label="Month", value=datetime.now().month, visible=False)
        day_input = gr.Number(label="Day", value=datetime.now().day, visible=False)

    with gr.Row():
        hour_input = gr.Number(label="Hour (24-hour format)", value=datetime.now().hour, visible=False)
        minute_input = gr.Number(label="Minute", value=datetime.now().minute, visible=False)

    with gr.Row():
        submit_btn = gr.Button("Calculate")

    with gr.Row():
        with gr.Column():
          output_text = gr.Textbox(label="Celestial data courtesy of NASA JPL DE441.bsp ephemeris.", lines=20)
        with gr.Column():
          output_plot = gr.Image(label="Visualization")

    # Connect all the event handlers
    location_option_input.change(
        fn=update_location_fields,
        inputs=location_option_input,
        outputs=[city_input, lat_input, lon_input]
    )

    time_option_input.change(
        fn=update_time_fields,
        inputs=time_option_input,
        outputs=[year_input, month_input, day_input, hour_input, minute_input]
    )

    submit_btn.click(
        fn=moon_sun_report,
        inputs=[
            location_option_input, city_input, lat_input, lon_input,
            time_option_input, year_input, month_input, day_input,
            hour_input, minute_input, day29_input
        ],
        outputs=[output_text, output_plot]
    )

    gr.Markdown("<center>Copyright © 2025 @ainulyaqinmhd | All Rights Reserved.</center>")

demo.launch()