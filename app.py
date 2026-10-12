
import sqlite3
from datetime import datetime, timedelta

import folium
import streamlit as st
from streamlit_folium import st_folium

DB_NAME = "queueless.db"

st.set_page_config(
    page_title="QueueLess | Campus Queue Tracker",
    page_icon="⏱️",
    layout="wide",
)


# ---------------- DATABASE ----------------

def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                latitude REAL,
                longitude REAL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location_id INTEGER NOT NULL,
                wait_minutes INTEGER NOT NULL,
                reported_at TEXT NOT NULL,
                FOREIGN KEY(location_id) REFERENCES locations(id)
            )
        """)


def get_locations():
    with get_connection() as conn:
        return conn.execute("""
            SELECT id, name, category, latitude, longitude
            FROM locations
            ORDER BY name
        """).fetchall()


def get_wait(location_id):
    cutoff = (
        datetime.now() - timedelta(hours=2)
    ).isoformat()

    with get_connection() as conn:
        row = conn.execute("""
            SELECT AVG(wait_minutes), COUNT(*)
            FROM reports
            WHERE location_id = ? AND reported_at >= ?
        """, (location_id, cutoff)).fetchone()

    if row and row[1]:
        return round(row[0]), row[1]

    return None, 0


# ---------------- QUEUE STATUS ----------------

def get_queue_status(wait):
    if wait is None:
        return "⚪ No recent reports"
    elif wait <= 5:
        return "🟢 Low queue"
    elif wait <= 15:
        return "🟡 Moderate queue"
    else:
        return "🔴 Busy queue"


def get_marker_color(wait):
    if wait is None:
        return "gray"
    elif wait <= 5:
        return "green"
    elif wait <= 15:
        return "orange"
    else:
        return "red"


init_db()


# ---------------- PAGE HEADER ----------------

st.title("⏱️ QueueLess")
st.subheader("Less waiting. More campus life.")

st.write(
    "Check reported queues around campus and help other "
    "students by sharing what you're seeing."
)

with st.sidebar:
    st.header("About QueueLess")
    st.write("A student-powered campus queue tracker.")
    st.caption(
        "Queue statuses are based on student reports, "
        "not live sensors."
    )
    st.caption("Reports older than two hours are excluded.")


# ---------------- TABS ----------------

map_tab, report_tab, manage_tab = st.tabs([
    "🗺️ Campus map",
    "📣 Report a queue",
    "📍 Manage locations",
])


# ---------------- CAMPUS MAP ----------------

with map_tab:
    st.header("Campus queue overview")
    
    locations = get_locations()
    total_locations = len(locations)
    active_reports = 0
    waits = []

    for loc in locations:
        wait, count = get_wait(loc[0])
        active_reports += count
        if wait is not None:
            waits.append(wait)

    avg_wait = round(sum(waits) / len(waits)) if waits else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("📍 Campus Locations", total_locations)
    col2.metric("📣 Recent Reports", active_reports)
    col3.metric("⏱️ Average Wait", f"{avg_wait} min" if waits else "No data")


    st.caption(
        "Only locations with coordinates appear as map pins. "
        "Please verify coordinates before adding them."
    )

    locations = get_locations()

    mapped = [
        loc for loc in locations
        if loc[3] is not None and loc[4] is not None
    ]

    if mapped:
        center_lat = sum(loc[3] for loc in mapped) / len(mapped)
        center_lon = sum(loc[4] for loc in mapped) / len(mapped)
        zoom = 16
    else:
        # Approximate fallback centre, not a verified facility location.
        center_lat, center_lon = 17.5000, 78.4000
        zoom = 12

    campus_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
    )

    for loc in mapped:
        location_id, name, category, lat, lon = loc
        wait, report_count = get_wait(location_id)

        wait_text = (
            f"{wait} minutes"
            if wait is not None
            else "No recent reports"
        )

        status = get_queue_status(wait)

        popup_text = (
            f"<b>{name}</b><br>"
            f"Category: {category}<br>"
            f"Estimated wait: {wait_text}<br>"
            f"Status: {status}<br>"
            f"Reports in last 2h: {report_count}"
        )

        folium.Marker(
            location=[lat, lon],
            tooltip=f"{name} — {status}",
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(
                color=get_marker_color(wait),
                icon="info-sign",
            ),
        ).add_to(campus_map)

    st_folium(
        campus_map,
        width=None,
        height=480,
        key="campus_map",
    )

    st.subheader("Current reported waits")

    if locations:
        rows = []

        for loc in locations:
            wait, count = get_wait(loc[0])

            rows.append({
                "Location": loc[1],
                "Type": loc[2],
                "Estimated wait": (
                    f"{wait} min"
                    if wait is not None
                    else "No recent reports"
                ),
                "Queue status": get_queue_status(wait),
                "Reports (last 2h)": count,
            })

        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Add your first campus location in Manage locations."
        )


# ---------------- REPORT A QUEUE ----------------

with report_tab:
    st.header("Report a queue")

    locations = get_locations()

    if not locations:
        st.warning(
            "Add a location in Manage locations before reporting a queue."
        )
    else:
        with st.form("report_form"):
            selected = st.selectbox(
                "Where are you waiting?",
                locations,
                format_func=lambda loc: f"{loc[1]} ({loc[2]})",
            )

            wait_minutes = st.number_input(
                "Your estimated wait (minutes)",
                min_value=0,
                max_value=240,
                value=5,
                step=1,
            )

            report_submitted = st.form_submit_button("Submit report")

        if report_submitted:
            with get_connection() as conn:
                conn.execute("""
                    INSERT INTO reports
                    (location_id, wait_minutes, reported_at)
                    VALUES (?, ?, ?)
                """, (
                    selected[0],
                    int(wait_minutes),
                    datetime.now().isoformat(),
                ))

            st.success("Thanks! Your queue report has been saved.")
            st.rerun()


# ---------------- MANAGE LOCATIONS ----------------

with manage_tab:
    st.header("Manage campus locations")

    st.write(
        "Add a campus facility. Coordinates are optional, "
        "but required for a map pin."
    )

    # This is intentionally not inside st.form:
    # checkbox changes must rerun the app to show coordinate inputs.
    name = st.text_input(
        "Location name",
        placeholder="e.g. Campus cafeteria",
        key="location_name",
    )

    category = st.selectbox(
        "Category",
        [
            "Food",
            "Administration",
            "Library",
            "Transport",
            "Student services",
            "Other",
        ],
        key="location_category",
    )

    add_coordinates = st.checkbox(
        "I have verified coordinates for this location",
        key="add_coordinates",
    )

    latitude = None
    longitude = None

    if add_coordinates:
        st.caption(
            "Replace these example values with the verified coordinates "
            "for the actual facility."
        )

        col1, col2 = st.columns(2)

        with col1:
            latitude = st.number_input(
                "Latitude",
                min_value=-90.0,
                max_value=90.0,
                value=17.5000,
                format="%.6f",
                key="location_latitude",
            )

        with col2:
            longitude = st.number_input(
                "Longitude",
                min_value=-180.0,
                max_value=180.0,
                value=78.4000,
                format="%.6f",
                key="location_longitude",
            )

    if st.button("Add location", key="add_location_button"):
        clean_name = name.strip()

        if not clean_name:
            st.error("Please enter a location name.")
        else:
            try:
                with get_connection() as conn:
                    conn.execute("""
                        INSERT INTO locations
                        (name, category, latitude, longitude)
                        VALUES (?, ?, ?, ?)
                    """, (
                        clean_name,
                        category,
                        latitude,
                        longitude,
                    ))

                st.success(f"Added {clean_name}!")
                st.rerun()

            except sqlite3.IntegrityError:
                st.error(
                    "That location already exists. "
                    "Choose a different name."
                )

    st.divider()
    st.subheader("Saved locations")

    locations = get_locations()

    
    if locations:
        for loc in locations:
            location_id, name, category, lat, lon = loc

            if lat is not None and lon is not None:
                coords = f"{lat:.6f}, {lon:.6f}"
            else:
                coords = "Coordinates not added"

            col1, col2 = st.columns([4, 1])

            with col1:
                st.write(f"**{name}** — {category} · {coords}")

            with col2:
                if st.button("Delete", key=f"delete_{location_id}"):
                    with get_connection() as conn:
                        conn.execute(
                            "DELETE FROM reports WHERE location_id = ?",
                            (location_id,),
                        )
                        conn.execute(
                            "DELETE FROM locations WHERE id = ?",
                            (location_id,),
                        )

                    st.success(f"Deleted {name}.")
                    st.rerun()
    else:
        st.caption("No locations added yet.")

